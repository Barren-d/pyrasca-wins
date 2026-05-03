import os
import random
import time
from pathlib import Path

from curl_cffi import requests
from dotenv import load_dotenv

load_dotenv()

DEV_CACHE = os.getenv("DEV_CACHE", "false").lower() == "true"

# Rotate Chrome impersonation targets so each request has a slightly different
# TLS fingerprint. curl_cffi sets the matching User-Agent automatically.
_IMPERSONATE_TARGETS = ["chrome120", "chrome124", "chrome131", "chrome136"]

_RETRY_DELAYS = [15, 45, 120]  # seconds between retry attempts


class BlockedError(RuntimeError):
    """Raised when the server persistently returns 403/429 after all retries."""


def _new_session() -> requests.Session:
    s = requests.Session(impersonate=random.choice(_IMPERSONATE_TARGETS))
    s.headers.update({
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Referer": "https://www.juegosonce.es/",
    })
    return s


_session = _new_session()


def _cache_path(url: str) -> Path:
    slug = url.rstrip("/").split("/")[-1] or "index"
    return Path("data") / (slug + ".html")


def get(url: str, cache: bool = True) -> str:
    global _session

    path = _cache_path(url)
    use_cache = DEV_CACHE and cache
    if use_cache and path.exists():
        return path.read_text(encoding="utf-8")

    print(f"  [fetch] {url}")
    last_exc: Exception | None = None

    for attempt, delay in enumerate([0] + _RETRY_DELAYS):
        if delay:
            print(f"  [fetch] retrying in {delay}s (attempt {attempt + 1})")
            time.sleep(delay)
            _session = _new_session()  # fresh session, new impersonation target

        try:
            response = _session.get(
                url, timeout=30,
                headers={"Cache-Control": "no-cache", "Pragma": "no-cache"},
            )
            if response.status_code in (403, 429):
                print(f"  [fetch] {response.status_code} on attempt {attempt + 1}")
                last_exc = requests.HTTPError(response=response)
                continue
            response.raise_for_status()
        except requests.HTTPError as exc:
            last_exc = exc
            continue

        print(f"  [fetch] {len(response.text):,} bytes  server-date: {response.headers.get('date', '?')}")
        html = response.text

        if use_cache:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(html, encoding="utf-8")

        time.sleep(random.uniform(1.5, 4.5))
        return html

    raise BlockedError(f"Blocked after {len(_RETRY_DELAYS) + 1} attempts: {url}") from last_exc
