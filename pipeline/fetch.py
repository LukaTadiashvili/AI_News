"""Collectors: turn every source into a list of candidate dicts.

A candidate is:
  {id, url, title, snippet, source, section, company, product, press,
   published (ISO or None), score (int or None)}
Every collector fails softly: a broken site never stops the run.
"""
from __future__ import annotations

import hashlib
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

from sources import AI_WORDS, COMMUNITY, OFFICIAL, SUBREDDITS, YOUTUBE_CHANNELS

UA = "Mozilla/5.0 (compatible; AI-News-Digest/1.0; personal news reader)"
TIMEOUT = 25
SKIP_RELEASE = re.compile(r"(alpha|beta|\brc\b|-rc|nightly|preview|canary|dev\d)", re.I)
_AI_RE = re.compile(r"(?<![a-z])(" + "|".join(re.escape(w) for w in AI_WORDS) + r")(?![a-z])", re.I)


def log(*a):
    print("[fetch]", *a, flush=True)


def make_id(url: str) -> str:
    u = url.split("#")[0].rstrip("/")
    return hashlib.sha1(u.encode()).hexdigest()[:12]


def mentions_ai(text: str) -> bool:
    return bool(_AI_RE.search(text or ""))


def clean_text(html: str, limit: int = 4000) -> str:
    if not html:
        return ""
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text)[:limit]


def get(url: str, **kw) -> requests.Response:
    headers = {"User-Agent": UA, **kw.pop("headers", {})}
    r = requests.get(url, headers=headers, timeout=TIMEOUT, **kw)
    r.raise_for_status()
    return r


def _entry_date(e) -> str | None:
    t = e.get("published_parsed") or e.get("updated_parsed")
    if not t:
        return None
    return datetime(*t[:6], tzinfo=timezone.utc).isoformat()


def _cand(src, url, title, snippet="", published=None, score=None, section="news", **extra):
    c = {
        "id": make_id(url), "url": url, "title": (title or "").strip(), "snippet": snippet or "",
        "source": src.get("name", ""), "section": section, "company": src.get("company"),
        "product": src.get("product"), "press": bool(src.get("press")),
        "published": published, "score": score,
    }
    c.update(extra)
    return c


# ---------------------------------------------------------------- official
def fetch_rss(src, section="news", limit=15):
    feed = feedparser.parse(get(src["url"]).content)
    out = []
    for e in feed.entries[:limit]:
        link = e.get("link")
        if not link:
            continue
        body = ""
        if e.get("content"):
            body = e.content[0].get("value", "")
        body = body or e.get("summary", "")
        out.append(_cand(src, link, e.get("title", ""), clean_text(body, 3000), _entry_date(e), section=section))
    return out


def fetch_releases(src, limit=8):
    feed = feedparser.parse(get(src["url"]).content)
    out = []
    for e in feed.entries[:limit]:
        title = e.get("title", "")
        if SKIP_RELEASE.search(title):
            continue
        body = e.content[0].get("value", "") if e.get("content") else e.get("summary", "")
        ver = re.sub(r"^[^0-9]*", "", title).strip() or title
        out.append(_cand(src, e.get("link"), f"{src['product']} {ver}", clean_text(body, 5000),
                         _entry_date(e), version=ver))
    return out


def fetch_html(src, limit=12):
    html = get(src["url"]).text
    soup = BeautifulSoup(html, "html.parser")
    base = src["url"]
    host = urlparse(base).netloc
    seen, out = set(), []
    for a in soup.find_all("a", href=True):
        href = urljoin(base, a["href"]).split("?")[0].split("#")[0]
        p = urlparse(href)
        if p.netloc != host or not p.path.startswith(src["prefix"]):
            continue
        slug = p.path[len(src["prefix"]):].strip("/")
        if not slug or href in seen:
            continue
        text = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        if len(text) < 20:  # category links like "Product", "Policy"
            continue
        seen.add(href)
        out.append(_cand(src, href, text[:160], text[:600]))
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------- community
def fetch_hn(src, since_hours=24):
    since = int(time.time()) - since_hours * 3600
    base = "https://hn.algolia.com/api/v1/search"
    out = []
    for tags, min_points in (("story", 150), ("show_hn", 40)):
        params = {"tags": tags, "hitsPerPage": 60,
                  "numericFilters": f"created_at_i>{since},points>{min_points}"}
        for h in get(base, params=params).json().get("hits", []):
            title = h.get("title") or ""
            text = clean_text(h.get("story_text") or "", 1500)
            if not mentions_ai(title + " " + text):
                continue
            hn_url = f"https://news.ycombinator.com/item?id={h['objectID']}"
            out.append(_cand(src, hn_url, title, text, h.get("created_at"), h.get("points"),
                             section="community", link=h.get("url") or hn_url,
                             source=("Hacker News · Show HN" if tags == "show_hn" else "Hacker News")))
    return out


_reddit_token = None


def _reddit_auth():
    global _reddit_token
    cid, secret = os.getenv("REDDIT_CLIENT_ID"), os.getenv("REDDIT_CLIENT_SECRET")
    if not (cid and secret):
        return None
    if _reddit_token is None:
        r = requests.post("https://www.reddit.com/api/v1/access_token",
                          auth=(cid, secret), data={"grant_type": "client_credentials"},
                          headers={"User-Agent": UA}, timeout=TIMEOUT)
        r.raise_for_status()
        _reddit_token = r.json()["access_token"]
    return _reddit_token


def _reddit_posts(subs, limit=60):
    """Top posts of the day across several subreddits in ONE request (multireddit),
    so Reddit doesn't rate-limit us for 35 separate calls."""
    path = "+".join(subs)
    token = _reddit_auth()
    if token:
        data = get(f"https://oauth.reddit.com/r/{path}/top", params={"t": "day", "limit": limit},
                   headers={"Authorization": f"bearer {token}"}).json()
        for ch in data.get("data", {}).get("children", []):
            p = ch["data"]
            if p.get("stickied") or p.get("over_18"):
                continue
            yield {"sub": p.get("subreddit", ""), "title": p.get("title", ""),
                   "body": (p.get("selftext") or "")[:3000], "url": "https://www.reddit.com" + p.get("permalink", ""),
                   "published": datetime.fromtimestamp(p.get("created_utc", time.time()), timezone.utc).isoformat(),
                   "score": p.get("score"), "comments": p.get("num_comments")}
    else:
        feed = feedparser.parse(get(f"https://www.reddit.com/r/{path}/top/.rss",
                                    params={"t": "day", "limit": limit}).content)
        for e in feed.entries:
            sub = (e.get("tags") or [{}])[0].get("term", "") if e.get("tags") else ""
            body = clean_text(e.content[0].get("value", "") if e.get("content") else "", 3000)
            yield {"sub": sub, "title": e.get("title", ""), "body": body, "url": e.get("link"),
                   "published": _entry_date(e), "score": None, "comments": None}


def fetch_reddit(per_sub=4):
    ai_subs = [s for s, o in SUBREDDITS.items() if o.get("ai_only")]
    other_subs = [s for s, o in SUBREDDITS.items() if not o.get("ai_only")]
    out = []
    for n, (subs, need_ai) in enumerate(((ai_subs, False), (other_subs, True))):
        if n:
            time.sleep(4)
        try:
            count = {}
            for p in _reddit_posts(subs):
                if need_ai and not mentions_ai(p["title"] + " " + p["body"]):
                    continue
                if count.get(p["sub"], 0) >= per_sub or not p["url"]:
                    continue
                count[p["sub"]] = count.get(p["sub"], 0) + 1
                src = {"name": f"Reddit · r/{p['sub']}" if p["sub"] else "Reddit"}
                out.append(_cand(src, p["url"], p["title"], p["body"], p["published"], p["score"],
                                 section="community", comments=p["comments"]))
        except Exception as ex:  # noqa: BLE001
            log(f"reddit ({'work' if need_ai else 'AI'} subs) failed: {ex}")
    log(f"reddit: {len(out)} posts")
    return out


def fetch_producthunt(src, limit=30):
    feed = feedparser.parse(get(src["url"]).content)
    out = []
    for e in feed.entries[:limit]:
        title = e.get("title", "")
        body = clean_text(e.get("summary", ""), 800)
        if mentions_ai(title + " " + body):
            out.append(_cand(src, e.get("link"), title, body, _entry_date(e), section="community"))
    return out


def fetch_github_trending(src, limit=25):
    soup = BeautifulSoup(get(src["url"]).text, "html.parser")
    out = []
    for row in soup.select("article.Box-row")[:limit]:
        a = row.select_one("h2 a")
        if not a:
            continue
        repo = re.sub(r"\s+", "", a.get_text())
        desc_el = row.select_one("p")
        desc = desc_el.get_text(" ", strip=True) if desc_el else ""
        stars_el = row.find(string=re.compile(r"stars? today"))
        stars = int(re.sub(r"\D", "", stars_el)) if stars_el and re.search(r"\d", stars_el) else None
        if mentions_ai(repo + " " + desc):
            out.append(_cand(src, "https://github.com" + a["href"], repo, desc, None, stars, section="community"))
    return out


def fetch_youtube():
    out = []
    for ch in YOUTUBE_CHANNELS:
        try:
            src = {"name": "YouTube"}
            out += fetch_rss({**src, "url": f"https://www.youtube.com/feeds/videos.xml?channel_id={ch}"},
                             section="community", limit=3)
        except Exception as ex:  # noqa: BLE001
            log(f"youtube {ch} failed: {ex}")
    return out


# ---------------------------------------------------------------- entry points
OFFICIAL_FETCHERS = {"rss": fetch_rss, "releases": fetch_releases, "html": fetch_html}
COMMUNITY_FETCHERS = {"hn": fetch_hn, "producthunt": fetch_producthunt, "github_trending": fetch_github_trending}


def collect_official():
    out = []
    for src in OFFICIAL:
        try:
            got = OFFICIAL_FETCHERS[src["kind"]](src)
            log(f"{src['name']}: {len(got)}")
            out += got
        except Exception as ex:  # noqa: BLE001
            log(f"{src['name']} failed: {ex}")
    return out


def collect_community():
    out = []
    for src in COMMUNITY:
        try:
            got = COMMUNITY_FETCHERS[src["kind"]](src)
            log(f"{src['name']}: {len(got)}")
            out += got
        except Exception as ex:  # noqa: BLE001
            log(f"{src['name']} failed: {ex}")
    out += fetch_reddit()
    out += fetch_youtube()
    return out


def article_text(cand) -> str:
    """Full text for summarizing. Falls back to the snippet."""
    if cand.get("kind_hint") == "release" or cand.get("version"):
        return cand.get("snippet", "")
    if cand["section"] == "community" and len(cand.get("snippet", "")) > 300:
        return cand["snippet"]
    url = cand.get("link") or cand["url"]
    try:
        soup = BeautifulSoup(get(url).text, "html.parser")
        for t in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
            t.decompose()
        root = soup.find("article") or soup.find("main") or soup.body or soup
        paras = [p.get_text(" ", strip=True) for p in root.find_all(["p", "li", "h2", "h3"])]
        text = re.sub(r"\s+", " ", " ".join(x for x in paras if len(x) > 30))
        if len(text) > 200:
            return text[:9000]
    except Exception as ex:  # noqa: BLE001
        log(f"article fetch failed {url}: {ex}")
    return cand.get("snippet", "")
