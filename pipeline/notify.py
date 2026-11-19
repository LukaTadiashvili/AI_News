"""Phone notifications through ntfy (https://ntfy.sh)."""
import os

import requests


def send(title: str, message: str, click: str | None = None, priority: int = 3, tags=None) -> bool:
    topic = os.getenv("NTFY_TOPIC")
    if not topic:
        print("[notify] NTFY_TOPIC not set, skipping:", title, flush=True)
        return False
    server = os.getenv("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    payload = {"topic": topic, "title": title, "message": message, "priority": priority}
    if click:
        payload["click"] = click
    if tags:
        payload["tags"] = tags
    headers = {}
    if os.getenv("NTFY_TOKEN"):
        headers["Authorization"] = f"Bearer {os.getenv('NTFY_TOKEN')}"
    try:
        # JSON publishing keeps Georgian text intact (HTTP headers can't carry it).
        r = requests.post(server, json=payload, headers=headers, timeout=20)
        r.raise_for_status()
        print("[notify] sent:", title, flush=True)
        return True
    except requests.RequestException as ex:
        print("[notify] failed:", ex, flush=True)
        return False
