"""Offline test of the whole pipeline: fake sources, fake Gemini, captured notifications.

Run:  python -m pytest tests  (or)  python tests/test_pipeline.py
"""
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import fetch  # noqa: E402
import gemini  # noqa: E402
import main  # noqa: E402
import notify  # noqa: E402

TZ = main.TZ


def fake_official():
    return [
        fetch._cand({"name": "OpenAI", "company": "OpenAI"}, "https://openai.com/news/gpt-6", "Introducing GPT-6",
                    "GPT-6 is our new flagship model", "2026-11-19T08:00:00+00:00"),
        fetch._cand({"name": "Claude Code", "company": "Anthropic", "product": "Claude Code"},
                    "https://github.com/anthropics/claude-code/releases/tag/v2.4.0", "Claude Code 2.4.0",
                    "Added background agents", "2026-11-19T07:00:00+00:00", version="2.4.0"),
        fetch._cand({"name": "TechCrunch AI", "press": True}, "https://techcrunch.com/x", "Startup raises $50M",
                    "funding", "2026-11-19T06:00:00+00:00"),
        fetch._cand({"name": "OpenAI"}, "https://openai.com/news/old", "Old post", "", "2026-10-01T00:00:00+00:00"),
    ]


def fake_community():
    return [fetch._cand({"name": "Reddit · r/PowerBI"}, "https://reddit.com/r/PowerBI/1", "I automated DAX with Claude",
                        "long post " * 50, "2026-11-19T05:00:00+00:00", 1200, section="community")]


def fake_ask(prompt, temperature=0.3, max_tokens=8192):
    if "Decide for every candidate" in prompt:
        ids = {c["title"]: c["id"] for c in fake_official() + fake_community()}
        return {"results": [
            {"id": ids["Introducing GPT-6"], "keep": True, "importance": 10, "big": True, "category": "models"},
            {"id": ids["Claude Code 2.4.0"], "keep": True, "importance": 8, "big": False, "category": "tools"},
            {"id": ids["Startup raises $50M"], "keep": False, "importance": 3},
            {"id": ids["I automated DAX with Claude"], "keep": True, "importance": 7, "category": "community",
             "topic": "analytics"},
        ]}
    import re
    items = re.findall(r"=== ITEM id=(\w+)\nSOURCE: [^\n]*\nTITLE: ([^\n]*)", prompt)
    if "weekly recap" in prompt:
        return {"title_ka": "კვირა", "intro_ka": "შესავალი", "top": []}
    cards = []
    for iid, title in items:
        if "Community tab" in prompt:
            cards.append({"id": iid, "title_ka": "DAX ავტომატიზაცია Claude-ით", "topic": "analytics", "built_ka": "ააწყო",
                          "tools": ["Claude", "Power BI"], "use_ka": "შენთვის", "why_ka": "რატომ", "tldr_ka": "მოკლედ",
                          "details_ka": ["a"], "steps_ka": ["1", "2"], "term": {"word": "DAX", "def_ka": "ფორმულების ენა"}})
            continue
        gpt = title == "Introducing GPT-6"
        cards.append({"id": iid, "title_ka": "GPT-6 გამოვიდა" if gpt else "Claude Code 2.4", "company": "OpenAI",
                      "bullets": ["ა", "ბ", "გ"], "why_ka": "მნიშვნელოვანია", "use_ka": "გამოიყენე", "tldr_ka": "ორი წინადადება",
                      "whats_new": [{"icon": "⚡", "label": "x", "text": "y"}], "details_ka": ["p1", "p2"],
                      "numbers": [{"label": "ფასი", "value": "$1"}], "todo_ka": "",
                      "term": {"word": "ტოკენი", "def_ka": "ტექსტის ნაწილი"}, "read_seconds": 45,
                      "model_info": {"name": "GPT-6", "company": "OpenAI", "context": "1M"} if gpt else None})
    return {"cards": cards}


def test_full_run():
    tmp = Path(tempfile.mkdtemp())
    main.DATA, main.STATE_FILE = tmp / "data", tmp / "state.json"
    main.fetch.collect_official, main.fetch.collect_community = fake_official, fake_community
    main.fetch.article_text = lambda c: c["snippet"]
    gemini.ask_json = fake_ask
    main.gemini.ask_json = fake_ask
    sent = []
    notify.send = lambda title, msg, **kw: sent.append(title) or True
    main.notify.send = notify.send
    os.environ["GEMINI_API_KEY"] = "test"
    os.environ["APP_URL"] = "https://example.github.io/AI_News/"

    # Run 1 = bootstrap at 10:00: no instant alerts, before digest time.
    main.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    main.run(now=datetime(2026, 11, 19, 10, 0, tzinfo=TZ))
    items = json.loads((main.DATA / "items.json").read_text())
    titles = [i["title_ka"] for i in items]
    assert "GPT-6 გამოვიდა" in titles and "Claude Code 2.4" in titles
    assert "DAX ავტომატიზაცია Claude-ით" in titles
    assert len(items) == 3, titles  # funding + old post dropped
    assert sent == [], sent
    board = json.loads((main.DATA / "leaderboard.json").read_text())
    assert board[0]["name"] == "GPT-6"
    gloss = json.loads((main.DATA / "glossary.json").read_text())
    assert "DAX" in gloss

    # Run 2 at 02:00 next night with a new big item -> queued (quiet hours).
    state = json.loads(main.STATE_FILE.read_text())
    state["seen"].pop(items[[i["title_ka"] for i in items].index("GPT-6 გამოვიდა")]["id"])
    main.save(main.STATE_FILE, state)
    main.save(main.DATA / "items.json", [i for i in items if i["title_ka"] != "GPT-6 გამოვიდა"])
    main.run(now=datetime(2026, 11, 20, 2, 0, tzinfo=TZ))
    assert sent == [], sent
    assert len(json.loads(main.STATE_FILE.read_text())["pending_big"]) == 1

    # Run 3 at 09:10 -> the queued big alert goes out.
    main.run(now=datetime(2026, 11, 20, 9, 10, tzinfo=TZ))
    assert sent == ["🔴 GPT-6 გამოვიდა"], sent

    # Run 4 at 13:05 -> daily digest, once.
    main.run(now=datetime(2026, 11, 20, 13, 5, tzinfo=TZ))
    main.run(now=datetime(2026, 11, 20, 13, 35, tzinfo=TZ))
    digests = [t for t in sent if t.startswith("📰")]
    assert len(digests) == 1, sent
    # Quota used up: nothing crashes, items wait in the queue, files still saved.
    def no_quota(*a, **k):
        raise gemini.GeminiQuotaExhausted("used up")
    main.gemini.ask_json = no_quota
    state = json.loads(main.STATE_FILE.read_text())
    state["pending_summaries"] = [{"cand": fake_community()[0] | {"id": "zz1"}, "decision": {"keep": True, "importance": 9}}]
    main.save(main.STATE_FILE, state)
    main.run(now=datetime(2026, 11, 20, 20, 5, tzinfo=TZ))
    assert len(json.loads(main.STATE_FILE.read_text())["pending_summaries"]) == 1
    print("OK", sent)


if __name__ == "__main__":
    test_full_run()
