"""Tiny Gemini API client (free tier from Google AI Studio).

The free tier has small per-minute and per-day limits *per model*. So:
- a per-minute limit -> wait the time Google asks for, then retry
- a per-day limit    -> switch to the next model in the list
- every model used up -> stop calling Gemini for the rest of the run (no endless retries)
"""
from __future__ import annotations

import json
import os
import re
import time

import requests

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODELS = ["gemini-flash-latest", "gemini-flash-lite-latest", "gemini-2.5-flash",
                  "gemini-2.5-flash-lite", "gemini-2.0-flash"]
MIN_GAP = float(os.getenv("GEMINI_MIN_GAP", "7"))  # seconds between calls

_models = [m.strip() for m in os.getenv("GEMINI_MODEL", "").split(",") if m.strip()] or list(DEFAULT_MODELS)
_last_call = 0.0
calls_made = 0
exhausted = False


class GeminiError(Exception):
    pass


class GeminiQuotaExhausted(GeminiError):
    pass


def _parse_json(text: str):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"[\[{].*[\]}]", text, re.S)
        if m:
            return json.loads(m.group(0))
        raise


def _retry_delay(body: str) -> float:
    m = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', body)
    return min(float(m.group(1)) + 2, 90) if m else 40


def ask_json(prompt: str, temperature: float = 0.3, max_tokens: int = 32768):
    """Send a prompt, return parsed JSON. Raises GeminiError / GeminiQuotaExhausted."""
    global _last_call, calls_made, exhausted
    if exhausted:
        raise GeminiQuotaExhausted("daily quota used up for all models")
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise GeminiError("GEMINI_API_KEY is not set")
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens,
                             "responseMimeType": "application/json"},
    }
    last_err, minute_waits = None, 0
    for _ in range(12):
        if not _models:
            exhausted = True
            raise GeminiQuotaExhausted("daily quota used up for all models")
        wait = MIN_GAP - (time.time() - _last_call)
        if wait > 0:
            time.sleep(wait)
        model = _models[0]
        _last_call = time.time()
        try:
            r = requests.post(API.format(model=model), params={"key": key}, json=body, timeout=180)
        except requests.RequestException as ex:
            last_err = ex
            time.sleep(10)
            continue
        calls_made += 1
        if r.status_code == 404:
            print(f"[gemini] {model} not available, next model", flush=True)
            _models.pop(0)
            continue
        if r.status_code == 429:
            per_minute = "PerMinute" in r.text and "PerDay" not in r.text
            if per_minute and minute_waits < 2:
                minute_waits += 1
                d = _retry_delay(r.text)
                print(f"[gemini] {model} per-minute limit, waiting {d:.0f}s", flush=True)
                time.sleep(d)
                continue
            print(f"[gemini] {model} daily limit reached, next model", flush=True)
            _models.pop(0)
            minute_waits = 0
            continue
        if r.status_code in (500, 502, 503, 504):
            last_err = GeminiError(f"{r.status_code}: {r.text[:200]}")
            time.sleep(15)
            continue
        if r.status_code != 200:
            raise GeminiError(f"{r.status_code}: {r.text[:300]}")
        data = r.json()
        try:
            text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
            return _parse_json(text)
        except (KeyError, IndexError, json.JSONDecodeError) as ex:
            last_err = GeminiError(f"bad response: {ex}; {str(data)[:300]}")
            continue
    raise GeminiError(f"gave up: {last_err}")
