"""AI News pipeline: collect -> filter -> summarize (Georgian) -> save -> notify.

Run every ~30 min by GitHub Actions. Safe to run as often as you like:
already-seen items are skipped and notifications are sent once.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import fetch
import gemini
import notify
import prompts

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.getenv("AI_NEWS_DATA", ROOT / "site" / "data"))
STATE_FILE = Path(os.getenv("AI_NEWS_STATE", ROOT / "state" / "state.json"))
PROFILE_FILE = ROOT / "config" / "profile.md"
TZ = ZoneInfo("Asia/Tbilisi")

QUIET_START, QUIET_END = 0, 9      # no instant alerts 00:00-09:00 Tbilisi
DIGEST_HOUR = 13                   # daily digest at 13:00 Tbilisi
WEEKLY_DAY, WEEKLY_HOUR = 6, 20    # Sunday 20:00 Tbilisi
COMMUNITY_EVERY = timedelta(hours=3)
MAX_AGE = timedelta(days=5)        # ignore older posts from feeds
KEEP_ITEMS = timedelta(days=120)
MAX_SUMMARIES = {"news": 12, "community": 8}
TRIAGE_BATCH = 40


def log(*a):
    print("[main]", *a, flush=True)


# ---------------------------------------------------------------- storage
def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def app_url(fragment=""):
    base = os.getenv("APP_URL", "").rstrip("/")
    return f"{base}/#{fragment}" if base else None


def profile_text():
    return os.getenv("USER_PROFILE") or PROFILE_FILE.read_text(encoding="utf-8")


# ---------------------------------------------------------------- helpers
def s(x, limit=600):
    return str(x).strip()[:limit] if isinstance(x, (str, int, float)) and str(x).strip() else ""


def lst(x, n=6):
    return [v for v in x if v not in (None, "", {}, [])][:n] if isinstance(x, list) else []


def parse_dt(v):
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def domain(url):
    return urlparse(url).netloc.removeprefix("www.")


# ---------------------------------------------------------------- build items
def build_item(cand, tri, card, now):
    url = cand.get("link") or cand["url"]
    item = {
        "id": cand["id"], "section": cand["section"],
        "category": "community" if cand["section"] == "community" else (tri.get("category") if tri.get("category") in ("models", "tools") else "models"),
        "topic": s(card.get("topic") or tri.get("topic"), 30) if cand["section"] == "community" else "",
        "importance": int(tri.get("importance") or 6),
        "big": bool(tri.get("big")) and cand["section"] == "news",
        "url": url, "discussion": cand["url"] if cand.get("link") and cand["link"] != cand["url"] else "",
        "source": cand["source"], "domain": domain(url),
        "company": s(card.get("company")) or cand.get("company") or "",
        "product": s(card.get("product")) or cand.get("product") or "",
        "version": s(card.get("version")) or cand.get("version") or "",
        "published": cand.get("published") or now.isoformat(),
        "added": now.isoformat(),
        "score": cand.get("score"),
        "title_ka": s(card.get("title_ka"), 160) or cand["title"],
        "title_en": cand["title"][:200],
        "why_ka": s(card.get("why_ka")), "use_ka": s(card.get("use_ka")),
        "tldr_ka": s(card.get("tldr_ka"), 900),
        "details_ka": [s(p, 1500) for p in lst(card.get("details_ka"), 3)],
        "term": card.get("term") if isinstance(card.get("term"), dict) and card["term"].get("word") else None,
        "read_seconds": int(card.get("read_seconds") or 40) if str(card.get("read_seconds", "")).isdigit() else 40,
    }
    if cand["section"] == "news":
        item.update({
            "bullets": [s(b, 200) for b in lst(card.get("bullets"), 3)],
            "whats_new": [w for w in lst(card.get("whats_new"), 5) if isinstance(w, dict)],
            "numbers": [n for n in lst(card.get("numbers"), 4) if isinstance(n, dict) and n.get("value")],
            "todo_ka": s(card.get("todo_ka"), 300),
        })
    else:
        item.update({
            "built_ka": s(card.get("built_ka"), 500),
            "tools": [s(t, 40) for t in lst(card.get("tools"), 6)],
            "quote_ka": s(card.get("quote_ka"), 400),
            "steps_ka": [s(t, 300) for t in lst(card.get("steps_ka"), 4)],
        })
    return item


def upsert_model(board, info, item):
    if not isinstance(info, dict) or not info.get("name"):
        return
    key = info["name"].strip().lower()
    row = {"name": s(info.get("name"), 60), "company": s(info.get("company"), 40) or item["company"],
           "context": s(info.get("context"), 30), "price_in": s(info.get("price_in"), 40),
           "price_out": s(info.get("price_out"), 40), "best_for_ka": s(info.get("best_for_ka"), 200),
           "access_ka": s(info.get("access_ka"), 200), "released": item["added"][:10], "item": item["id"]}
    board[:] = [r for r in board if r["name"].strip().lower() != key]
    board.insert(0, row)
    del board[30:]


# ---------------------------------------------------------------- notifications
def is_quiet(now):
    return QUIET_START <= now.hour < QUIET_END


def alert_big(item):
    bullets = "\n".join("• " + b for b in item.get("bullets", [])[:3])
    msg = (item.get("why_ka") or "") + ("\n" + bullets if bullets else "")
    notify.send("🔴 " + item["title_ka"], msg.strip() or item["title_ka"],
                click=app_url(f"item-{item['id']}") or item["url"], priority=5, tags=["rotating_light"])


def daily_digest(items, state, now):
    today = now.date().isoformat()
    if now.hour < DIGEST_HOUR or state.get("last_digest_date") == today:
        return
    since = parse_dt(state.get("last_digest_at")) or now - timedelta(days=1)
    fresh = [i for i in items if (parse_dt(i["added"]) or now) > since]
    state["last_digest_date"], state["last_digest_at"] = today, now.isoformat()
    if not fresh:
        log("digest: nothing new")
        return
    news = sorted([i for i in fresh if i["section"] == "news"], key=lambda i: -i["importance"])
    comm = sorted([i for i in fresh if i["section"] == "community"], key=lambda i: -i["importance"])
    lines = ["• " + i["title_ka"] for i in news[:6]]
    if comm:
        lines.append(f"👥 საზოგადოებიდან: {len(comm)} იდეა" + (f", მაგ. {comm[0]['title_ka']}" if comm else ""))
    notify.send(f"📰 დღეს AI-ში: {len(news)} სიახლე" if news else "👥 დღის იდეები AI-დან",
                "\n".join(lines), click=app_url("today"), priority=3, tags=["newspaper"])


def weekly_recap(items, weekly, state, now):
    week = f"{now.isocalendar().year}-W{now.isocalendar().week:02d}"
    if now.weekday() != WEEKLY_DAY or now.hour < WEEKLY_HOUR or state.get("last_weekly") == week:
        return
    week_items = [i for i in items if (parse_dt(i["added"]) or now) > now - timedelta(days=7)]
    state["last_weekly"] = week
    if len(week_items) < 3:
        return
    try:
        res = gemini.ask_json(prompts.weekly(week_items), temperature=0.4)
    except gemini.GeminiError as ex:
        log("weekly failed:", ex)
        state["last_weekly"] = None
        return
    by_id = {i["id"]: i for i in week_items}
    top = [{"id": t["id"], "line_ka": s(t.get("line_ka"), 300)} for t in lst(res.get("top"), 5)
           if isinstance(t, dict) and t.get("id") in by_id]
    entry = {"week": week, "date": now.date().isoformat(), "title_ka": s(res.get("title_ka"), 120),
             "intro_ka": s(res.get("intro_ka"), 600), "top": top, "count": len(week_items)}
    weekly[:] = [w for w in weekly if w["week"] != week]
    weekly.insert(0, entry)
    del weekly[26:]
    msg = "\n".join(f"{n}. {by_id[t['id']]['title_ka']}" for n, t in enumerate(top, 1))
    notify.send("🗓 კვირის შეჯამება: " + (entry["title_ka"] or week), msg, click=app_url(f"week-{week}"),
                priority=3, tags=["calendar"])


# ---------------------------------------------------------------- main flow
def run(dry_run=False, now=None):
    now = now or datetime.now(TZ)
    state = load(STATE_FILE, {})
    state.setdefault("seen", {})
    state.setdefault("pending_big", [])
    items = load(DATA / "items.json", [])
    board = load(DATA / "leaderboard.json", [])
    weekly = load(DATA / "weekly.json", [])
    glossary = load(DATA / "glossary.json", {})
    bootstrap = not state.get("bootstrapped")

    # 1. collect
    cands = fetch.collect_official()
    last_comm = parse_dt(state.get("last_community_fetch"))
    if bootstrap or not last_comm or now - last_comm >= COMMUNITY_EVERY:
        cands += fetch.collect_community()
        state["last_community_fetch"] = now.isoformat()

    uniq, per_src = {}, {}
    for c in cands:
        if not c.get("url") or not c.get("title") or c["id"] in state["seen"] or c["id"] in uniq:
            continue
        pub = parse_dt(c.get("published"))
        if pub and now - pub > MAX_AGE:
            state["seen"][c["id"]] = now.isoformat()
            continue
        if bootstrap and c["section"] == "news":  # first run: only the newest few per source
            per_src[c["source"]] = per_src.get(c["source"], 0) + 1
            if per_src[c["source"]] > 3:
                state["seen"][c["id"]] = now.isoformat()
                continue
        uniq[c["id"]] = c
    cands = list(uniq.values())
    comm = sorted([c for c in cands if c["section"] == "community"], key=lambda c: -(c.get("score") or 0))[:80]
    cands = [c for c in cands if c["section"] == "news"] + comm
    log(f"{len(cands)} new candidates ({len(comm)} community)")

    if dry_run:
        for c in cands:
            print(f"  [{c['section']}] {c['source']}: {c['title'][:100]}")
        return
    if not os.getenv("GEMINI_API_KEY"):
        log("GEMINI_API_KEY missing: skipping summaries")
        cands = []

    # 2. triage
    profile = profile_text()
    recent = [{"id": i["id"], "title": i.get("title_en") or i["title_ka"]} for i in items[:60]]
    decisions = {}
    for k in range(0, len(cands), TRIAGE_BATCH):
        batch = cands[k:k + TRIAGE_BATCH]
        try:
            res = gemini.ask_json(prompts.triage(batch, recent, profile), temperature=0.1)
        except gemini.GeminiError as ex:
            log("triage failed:", ex)
            break
        rows = res.get("results", res) if isinstance(res, dict) else res
        for r in rows if isinstance(rows, list) else []:
            if isinstance(r, dict) and r.get("id") in uniq:
                decisions[r["id"]] = r
        for c in batch:
            state["seen"][c["id"]] = now.isoformat()

    # 3. summarize what passed
    existing = {i["id"]: i for i in items}
    kept = [c for c in cands if decisions.get(c["id"], {}).get("keep")]
    kept.sort(key=lambda c: -int(decisions[c["id"]].get("importance") or 0))
    done = {"news": 0, "community": 0}
    new_items = []
    for c in kept:
        d = decisions[c["id"]]
        dup = d.get("duplicate_of")
        if dup in existing:
            also = existing[dup].setdefault("also", [])
            if c["url"] not in [a["url"] for a in also]:
                also.append({"source": c["source"], "url": c.get("link") or c["url"]})
            continue
        if done[c["section"]] >= MAX_SUMMARIES[c["section"]]:
            continue
        text = fetch.article_text(c)
        try:
            p = prompts.summarize_news if c["section"] == "news" else prompts.summarize_community
            card = gemini.ask_json(p(c, text, profile), temperature=0.3)
        except gemini.GeminiError as ex:
            log("summary failed:", c["title"][:60], ex)
            state["seen"].pop(c["id"], None)  # retry next run
            continue
        if not isinstance(card, dict):
            continue
        item = build_item(c, d, card, now)
        new_items.append(item)
        existing[item["id"]] = item
        done[c["section"]] += 1
        if item["term"]:
            glossary[item["term"]["word"]] = s(item["term"].get("def_ka"), 300)
        if item["section"] == "news":
            upsert_model(board, card.get("model_info"), item)
        log(f"+ [{item['category']}] {item['importance']} {item['title_ka']}")

    items = new_items + items
    items.sort(key=lambda i: i["added"], reverse=True)

    # 4. notifications
    if not bootstrap:
        for item in new_items:
            if item["big"]:
                if is_quiet(now):
                    state["pending_big"].append(item["id"])
                else:
                    alert_big(item)
        if not is_quiet(now) and state["pending_big"]:
            for iid in state["pending_big"]:
                if iid in existing:
                    alert_big(existing[iid])
            state["pending_big"] = []
    daily_digest(items, state, now)
    weekly_recap(items, weekly, state, now)

    # 5. prune + save
    cutoff = now - KEEP_ITEMS
    items = [i for i in items if (parse_dt(i["added"]) or now) > cutoff]
    seen_cut = now - timedelta(days=45)
    state["seen"] = {k: v for k, v in state["seen"].items() if (parse_dt(v) or now) > seen_cut}
    state["bootstrapped"] = True

    save(DATA / "items.json", items)
    save(DATA / "leaderboard.json", board)
    save(DATA / "weekly.json", weekly)
    save(DATA / "glossary.json", dict(sorted(glossary.items())))
    save(DATA / "meta.json", {"updated": now.isoformat(), "items": len(items), "new_this_run": len(new_items),
                              "gemini_calls": gemini.calls_made})
    save(STATE_FILE, state)
    log(f"done: {len(new_items)} new, {len(items)} total, {gemini.calls_made} Gemini calls")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="only collect and print candidates")
    args = ap.parse_args()
    sys.exit(run(dry_run=args.dry_run))
