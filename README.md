# AI News

AI-ს მთავარი სიახლეები ქართულად, მოკლედ. A personal phone app (installable web app) that:

- collects AI news from official sources (OpenAI, Anthropic, Google, Meta, xAI, Mistral, Claude Code, Codex, Gemini CLI, Cursor, Power BI, Power Automate…)
- collects what people build with AI (Reddit, Hacker News, Product Hunt, GitHub Trending)
- filters out noise and summarizes everything in Georgian with Gemini (free tier)
- adds a "💼 შენთვის" line: how you could use it in your own work (see `config/profile.md`)
- sends phone notifications through **ntfy**: instant alerts for big launches, a daily digest at 13:00, a weekly recap on Sunday 20:00, quiet hours 00:00–09:00 (Tbilisi time)

Everything runs for free on GitHub Actions + GitHub Pages.

## Setup (one time, ~10 minutes)

1. **Gemini API key (free).** Go to <https://aistudio.google.com/apikey>, sign in, click **Create API key**, copy it.
2. **ntfy topic.** Invent a long random topic name, e.g. `ainews-k7q2m9x4p1`. Anyone who knows it can read your alerts, so keep it unguessable.
   In the ntfy app on iPhone: **+** → enter the topic → Subscribe.
3. **GitHub secrets.** In this repo: **Settings → Secrets and variables → Actions → New repository secret**:
   - `GEMINI_API_KEY` = your Gemini key
   - `NTFY_TOPIC` = your topic name
4. **GitHub Pages.** **Settings → Pages → Build and deployment → Source: GitHub Actions**.
5. **Start it.** **Actions → Update AI News → Run workflow**. After it finishes (2–5 min) the app is at
   `https://<your-github-username-lowercase>.github.io/AI_News/`.
6. **Install on iPhone.** Open that link in Safari → Share → **Add to Home Screen**.

From then on it updates every 30 minutes by itself.

### Optional

- `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` secrets: Reddit sometimes blocks GitHub's servers. If the Community tab stays empty of Reddit posts, create a free "script" app at <https://www.reddit.com/prefs/apps> and add these two secrets.
- `GEMINI_MODEL` variable (Settings → Variables): force a specific Gemini model. Default tries `gemini-flash-latest` first.
- `APP_URL` variable: if the app lives at a different address, so notification taps open the right page.
- YouTube channels: add channel IDs to `YOUTUBE_CHANNELS` in `pipeline/sources.py`.

## How it works

```
GitHub Actions (every 30 min)
  pipeline/fetch.py    -> collect from sources in pipeline/sources.py
  pipeline/prompts.py  -> Gemini: keep / drop, importance, duplicates
                       -> Gemini: Georgian card (bullets, why, for-you, details, numbers, term)
  pipeline/notify.py   -> ntfy alerts (instant / digest / weekly)
  site/data/*.json     -> committed, then site/ is deployed to GitHub Pages
site/                  -> the app (plain HTML/CSS/JS, no build step)
```

Change what you get: edit `config/profile.md` (your job and tools), `pipeline/sources.py` (sources, subreddits),
or the times at the top of `pipeline/main.py`.

## Develop

```
pip install -r requirements.txt
python tests/test_pipeline.py          # offline test with fake sources + fake Gemini
python pipeline/main.py --dry-run      # fetch real sources, print candidates (no Gemini)
cd site && python -m http.server       # open http://localhost:8000
```
