"""Prompts for Gemini. All reader-facing text is Georgian."""
import json

from sources import COMMUNITY_TOPICS

STYLE = """Writing style for ALL Georgian text:
- Use ONLY the Georgian alphabet (ა-ჰ) for Georgian words, never letters from other scripts (no Hebrew, Armenian, Cyrillic).
- Natural, modern, simple Georgian, like a smart friend explaining it. Short sentences. No filler, no hype words.
- Keep product, model, company and feature names in English (Claude Code, GPT-6, Power BI, n8n).
- Be concrete: numbers, versions, prices, what exactly changed. Never invent facts that are not in the source.
- If the source does not say something, leave that field empty instead of guessing."""


def triage(cands, recent, profile):
    items = [{"id": c["id"], "section": c["section"], "source": c["source"],
              "title": c["title"][:200], "text": c["snippet"][:500],
              "score": c.get("score")} for c in cands]
    topics = ", ".join(COMMUNITY_TOPICS)
    return f"""You are the editor of "AI News", a personal AI news app for one reader.

READER PROFILE:
{profile}

The reader wants ONLY juicy, informative, high-signal items and hates noise.

Decide for every candidate below whether it goes into the app.

SECTION "news" (official announcements, changelogs, press):
KEEP only:
- New models or major model updates from popular players: OpenAI, Anthropic/Claude, Google/Gemini, Meta/Llama, xAI/Grok, Mistral, DeepSeek, Qwen, Microsoft.
- New features / product launches in popular AI products: ChatGPT, Claude apps, Gemini app, Claude Code, Codex, Gemini CLI, Cursor, GitHub Copilot, NotebookLM, Sora/Veo and similar.
- Tool releases (version changelogs) that add real features or meaningful changes. A release with only small bug fixes -> keep=false.
- AI features in Power BI, Excel, Power Automate, Teams, Google Sheets (the reader's daily tools).
DROP: rumors ("reportedly", "sources say", leaks), opinion pieces, policy/regulation, lawsuits, funding/IPO/finance news,
pure research papers, hiring, events, partnerships with no product, small or unknown companies, tutorials, marketing fluff.
Press items (TechCrunch, The Verge) are kept only if they report a confirmed official launch.

SECTION "community" (Reddit, Hacker News, Product Hunt, GitHub):
KEEP only posts where real people share something concrete and useful:
- What they BUILT or AUTOMATED with AI (with tools named), and the result.
- First-hand experience, reviews or strong practical tips about new AI tools, agents, workflows.
- New useful agents/tools people discovered that official sites don't talk about.
Prefer topics relevant to the reader: {topics}.
DROP: memes, complaints, generic questions, drama, news reposts, low-effort self-promotion, "which AI is best?" threads.

DUPLICATES: if a candidate is about the SAME event as one in RECENT ITEMS (or another candidate with higher value),
set duplicate_of to that item's id and keep=false.

For each candidate return:
- importance: 1-10 (10 = huge new frontier model from OpenAI/Anthropic/Google; 7 = notable feature; 5 = minor)
- keep: true only if importance >= 6 and it passes the rules above
- big: true ONLY for really major launches worth an instant phone alert (new flagship/frontier model, huge product launch). Very rare.
- category: "models" (models, model-related products) | "tools" (Claude Code, Codex, Cursor, CLIs, Power BI, apps features) | "community"
- topic: for community only, one of: {topics}; otherwise ""

RECENT ITEMS (already in the app):
{json.dumps(recent, ensure_ascii=False)}

CANDIDATES:
{json.dumps(items, ensure_ascii=False)}

Return JSON: {{"results": [{{"id": "...", "keep": true, "importance": 8, "big": false, "category": "models", "topic": "", "duplicate_of": null}}]}}
Include every candidate id exactly once."""


NEWS_FIELDS = """{
  "id": "the item id, copied exactly",
  "title_ka": "headline that says what happened, max ~70 chars",
  "company": "company name in English, e.g. Anthropic",
  "product": "product name in English if it is about one product (e.g. 'Claude Code', 'ChatGPT', 'Gemini'), else ''",
  "version": "version number if this is a release, else ''",
  "bullets": ["3 very short bullets: what is new. For releases start each with ➕ (added), 🔧 (changed) or 🐛 (important fix)"],
  "why_ka": "one sentence: why it matters",
  "use_ka": "one concrete sentence: how THIS reader could use it in their retail data-analyst work (Excel, Power BI, Sheets, Power Automate, reports for branches, e-commerce, corporate sales) or in video editing. If there is really no use, say briefly who it is useful for.",
  "tldr_ka": "2 sentences: the whole story",
  "whats_new": [{"icon": "one emoji", "label": "short label like 'დაემატა:'", "text": "one sentence"}],
  "details_ka": ["2 short paragraphs with the most important details"],
  "numbers": [{"label": "Georgian label", "value": "short value like '2×', '$3 / 1M', '1M ტოკენი'"}],
  "todo_ka": "what the reader can do now to try it (e.g. 'ტერმინალში გაუშვი `claude update`'), or ''",
  "term": {"word": "one technical term from the text", "def_ka": "one-sentence simple Georgian explanation"},
  "read_seconds": 40,
  "model_info": null
}
3-5 items in whats_new, 0-4 items in numbers (only real numbers from the text).
If the item is a launch of a NEW AI MODEL, fill model_info:
{"name": "model name", "company": "...", "context": "e.g. 1M", "price_in": "$ per 1M input tokens or ''", "price_out": "$ per 1M output tokens or ''", "best_for_ka": "short Georgian: what it's best at", "access_ka": "short Georgian: where available"}"""


def _comm_fields():
    topics = ", ".join(COMMUNITY_TOPICS)
    return """{
  "id": "the item id, copied exactly",
  "title_ka": "what they built/did, max ~70 chars",
  "topic": "one of: %s",
  "built_ka": "1-2 sentences: what they built or did and the result",
  "tools": ["tools/models they used, in English"],
  "quote_ka": "the single most useful insight or tip from the post, translated (short), or ''",
  "why_ka": "one sentence: why it's interesting",
  "use_ka": "one concrete sentence: how THIS reader could apply the same idea in their retail data-analyst job or video editing",
  "tldr_ka": "2 sentences summary",
  "details_ka": ["1-2 short paragraphs: how it works"],
  "steps_ka": ["2-4 short steps to try the same thing"],
  "term": {"word": "one technical term", "def_ka": "one-sentence Georgian explanation"},
  "read_seconds": 40
}""" % topics


def summarize_batch(section, entries, profile):
    """entries: list of (cand, text). One Gemini call writes all cards."""
    blocks = []
    for c, text in entries:
        blocks.append(f"=== ITEM id={c['id']}\nSOURCE: {c['source']}\nTITLE: {c['title']}\nURL: {c['url']}\nTEXT:\n{text[:3500]}")
    if section == "news":
        intro = 'You write news cards for "AI News", a Georgian-language personal AI news app.'
        fields = NEWS_FIELDS
    else:
        intro = ('You write cards for the Community tab of "AI News", a Georgian-language personal AI news app. '
                 "It shows what real people build and do with AI, so the reader can steal ideas.")
        fields = _comm_fields()
    return f"""{intro}

READER PROFILE (use it for the "use_ka" field):
{profile}

{STYLE}

Write one card for EACH item below. Each card uses only facts from its own item.
Every card is a JSON object like this (all *_ka fields in Georgian):
{fields}

Return JSON: {{"cards": [card, card, ...]}} with exactly one card per item, in the same order.

{chr(10).join(blocks)}"""


def weekly(items):
    rows = [{"id": i["id"], "title": i["title_ka"], "why": i.get("why_ka", ""), "importance": i.get("importance"),
             "section": i["section"]} for i in items]
    return f"""You write the Sunday weekly recap for "AI News", a Georgian-language AI news app.

{STYLE}

THIS WEEK'S ITEMS:
{json.dumps(rows, ensure_ascii=False)}

Pick the 5 most important items (prefer official news, include at most 1-2 community items).
Return JSON:
{{"title_ka": "short catchy title for the week",
  "intro_ka": "2 sentences: the big picture of the week",
  "top": [{{"id": "item id", "line_ka": "one sentence why it was one of the week's top stories"}}]}}"""
