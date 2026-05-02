import os
import random
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

DEV_CACHE = os.getenv("DEV_CACHE", "false").lower() == "true"

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]

_session = requests.Session()
_session.headers.update(
    {
        "Accept-Language": "es-ES,es;q=0.9",
        "Referer": "https://www.juegosonce.es/",
    }
)


def _cache_path(url: str) -> Path:
    slug = url.rstrip("/").split("/")[-1] or "index"
    return Path("data") / (slug + ".html")


def get(url: str, cache: bool = True) -> str:
    path = _cache_path(url)
    use_cache = DEV_CACHE and cache
    if use_cache and path.exists():
        return path.read_text(encoding="utf-8")

    _session.headers["User-Agent"] = random.choice(_USER_AGENTS)
    print(f"  [fetch] {url}")
    response = _session.get(url, timeout=30, headers={"Cache-Control": "no-cache", "Pragma": "no-cache"})
    response.raise_for_status()
    print(f"  [fetch] {len(response.text):,} bytes  server-date: {response.headers.get('date', '?')}")
    html = response.text

    if use_cache:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")

    time.sleep(random.uniform(1.5, 4.5))
    return html
