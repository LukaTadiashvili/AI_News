"""Where AI News collects from.

section:
  "news"      -> official announcements / changelogs (Today, Models, Tools tabs)
  "community" -> what people build and share (Community tab)

kind:
  rss        -> any RSS/Atom feed
  releases   -> GitHub releases Atom feed (version history for a tool)
  html       -> a news page; links whose path starts with `prefix` are taken
  hn         -> Hacker News (Algolia API)
  reddit     -> subreddit top posts of the day
  producthunt, github_trending
"""

OFFICIAL = [
    # --- Frontier labs ---
    {"name": "OpenAI", "kind": "rss", "url": "https://openai.com/news/rss.xml", "company": "OpenAI"},
    {"name": "Anthropic", "kind": "html", "url": "https://www.anthropic.com/news", "prefix": "/news/", "company": "Anthropic"},
    {"name": "Claude (blog)", "kind": "html", "url": "https://claude.com/blog", "prefix": "/blog/", "company": "Anthropic"},
    {"name": "Google AI", "kind": "rss", "url": "https://blog.google/technology/ai/rss/", "company": "Google"},
    {"name": "Google DeepMind", "kind": "rss", "url": "https://deepmind.google/blog/rss.xml", "company": "Google"},
    {"name": "Meta AI", "kind": "html", "url": "https://ai.meta.com/blog/", "prefix": "/blog/", "company": "Meta"},
    {"name": "xAI", "kind": "html", "url": "https://x.ai/news", "prefix": "/news/", "company": "xAI"},
    {"name": "Mistral", "kind": "html", "url": "https://mistral.ai/news", "prefix": "/news/", "company": "Mistral"},

    # --- Tools: version releases ---
    {"name": "Claude Code", "kind": "releases", "url": "https://github.com/anthropics/claude-code/releases.atom",
     "company": "Anthropic", "product": "Claude Code"},
    {"name": "Codex CLI", "kind": "releases", "url": "https://github.com/openai/codex/releases.atom",
     "company": "OpenAI", "product": "Codex"},
    {"name": "Gemini CLI", "kind": "releases", "url": "https://github.com/google-gemini/gemini-cli/releases.atom",
     "company": "Google", "product": "Gemini CLI"},
    {"name": "Cursor", "kind": "html", "url": "https://cursor.com/changelog", "prefix": "/changelog/",
     "company": "Cursor", "product": "Cursor"},

    # --- Tools you use at work ---
    {"name": "Power BI blog", "kind": "rss", "url": "https://powerbi.microsoft.com/en-us/blog/feed/",
     "company": "Microsoft", "product": "Power BI"},
    {"name": "Power Automate blog", "kind": "rss",
     "url": "https://www.microsoft.com/en-us/power-platform/blog/power-automate/feed/",
     "company": "Microsoft", "product": "Power Automate"},

    # --- Press: catches big launches from anyone (filter keeps only big, confirmed ones) ---
    {"name": "TechCrunch AI", "kind": "rss", "url": "https://techcrunch.com/category/artificial-intelligence/feed/", "press": True},
    {"name": "The Verge AI", "kind": "rss", "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "press": True},
]

COMMUNITY = [
    {"name": "Hacker News", "kind": "hn"},
    {"name": "Product Hunt", "kind": "producthunt", "url": "https://www.producthunt.com/feed"},
    {"name": "GitHub Trending", "kind": "github_trending", "url": "https://github.com/trending?since=daily"},
]

# Subreddits -> topic hint. `ai_only` subs are about AI already; for the others we
# keep only posts that mention AI tools.
SUBREDDITS = {
    # AI tools
    "ClaudeAI": {"ai_only": True}, "OpenAI": {"ai_only": True}, "ChatGPTPro": {"ai_only": True},
    "GeminiAI": {"ai_only": True}, "ClaudeCode": {"ai_only": True}, "AI_Agents": {"ai_only": True},
    # 1. Data & BI
    "dataanalysis": {}, "PowerBI": {}, "excel": {}, "datascience": {}, "BusinessIntelligence": {},
    # 2. Automation
    "n8n": {"ai_only": True}, "PowerAutomate": {}, "automation": {}, "nocode": {},
    # 3. Video
    "VideoEditing": {}, "premiere": {}, "davinciresolve": {}, "aivideo": {"ai_only": True},
    # 4. Retail & e-commerce
    "ecommerce": {}, "retail": {}, "shopify": {},
    # 5. Sales
    "sales": {}, "salesforce": {},
    # 6. Marketing
    "marketing": {}, "PPC": {}, "socialmedia": {},
    # 7. Customer service
    "CustomerSuccess": {}, "callcentres": {},
    # 8. Presentations & visuals
    "powerpoint": {},
    # 9. Building without coding
    "vibecoding": {"ai_only": True}, "SideProject": {},
    # 12. Business & startups
    "Entrepreneur": {}, "SaaS": {}, "startups": {},
}

# Optional: YouTube channel IDs (UC...) whose new videos go to the community feed.
# Find a channel's ID: open the channel -> About -> Share -> Copy channel ID.
YOUTUBE_CHANNELS: list[str] = []

COMMUNITY_TOPICS = {
    "analytics": "ანალიტიკა",
    "automation": "ავტომატიზაცია",
    "video": "ვიდეო",
    "retail": "რითეილი",
    "sales": "გაყიდვები",
    "marketing": "მარკეტინგი",
    "support": "მომსახურება",
    "visuals": "პრეზენტაცია",
    "nocode": "კოდის გარეშე",
    "agents": "აგენტები",
    "business": "ბიზნესი",
}

AI_WORDS = [
    "ai", "a.i.", "gpt", "chatgpt", "claude", "gemini", "llm", "copilot", "openai", "anthropic",
    "agent", "agents", "prompt", "automation with", "machine learning", "genai", "generative",
    "midjourney", "runway", "sora", "veo", "elevenlabs", "cursor", "n8n", "mcp", "codex", "deepseek",
]
