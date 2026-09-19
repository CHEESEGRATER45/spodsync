"""Minimal client for the lrclib.net lyrics API.

lrclib.net is a free, open lyrics database. Docs: https://lrclib.net/docs
"""

from __future__ import annotations

import time

import requests

API_BASE = "https://lrclib.net/api"
USER_AGENT = "spodsync/0.1.0 (https://github.com/)"

TIMEOUT = 15
# Retry on 503 (lrclib.net gets overloaded under bursty traffic — a full
# playlist sync can trip this after 100+ requests in a couple minutes).
# Short, capped backoff: not worth waiting long on any single track.
RETRY_STATUS_CODES = {503}
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2.0


class LrcLibError(Exception):
    """Raised when the lrclib API can't be reached or returns something unusable."""


def _headers() -> dict:
    return {"User-Agent": USER_AGENT}


def _get_with_retry(url: str, params: dict) -> requests.Response:
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, headers=_headers(), timeout=TIMEOUT)
        except requests.RequestException as exc:
            last_exc = exc
        else:
            if resp.status_code not in RETRY_STATUS_CODES:
                return resp
            last_exc = LrcLibError(f"lrclib.net returned HTTP {resp.status_code}")

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))

    assert last_exc is not None
    if isinstance(last_exc, requests.RequestException):
        raise LrcLibError(f"Network error contacting lrclib.net: {last_exc}") from last_exc
    raise last_exc


def get_synced_lyrics(
    track_name: str,
    artist_name: str,
    album_name: str | None = None,
    duration: float | None = None,
) -> str | None:
    """Look up synced lyrics for a track.

    Tries the exact-match `/get` endpoint first (fastest, most accurate when
    duration is known), then falls back to `/search` for a fuzzy match.
    Returns the .lrc-formatted synced lyrics string, or None if no synced
    lyrics could be found.
    """
    synced = _try_get_endpoint(track_name, artist_name, album_name, duration)
    if synced:
        return synced

    return _try_search_endpoint(track_name, artist_name)


def _try_get_endpoint(
    track_name: str,
    artist_name: str,
    album_name: str | None,
    duration: float | None,
) -> str | None:
    if not duration:
        # The /get endpoint requires a duration for an exact match.
        return None

    params = {
        "track_name": track_name,
        "artist_name": artist_name,
        "duration": round(duration),
    }
    if album_name:
        params["album_name"] = album_name

    try:
        resp = _get_with_retry(f"{API_BASE}/get", params)
    except LrcLibError:
        raise
    except requests.RequestException as exc:
        raise LrcLibError(f"Network error contacting lrclib.net: {exc}") from exc

    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        raise LrcLibError(f"lrclib.net returned HTTP {resp.status_code}")

    data = resp.json()
    return data.get("syncedLyrics") or None


def _try_search_endpoint(track_name: str, artist_name: str) -> str | None:
    params = {"track_name": track_name, "artist_name": artist_name}

    try:
        resp = _get_with_retry(f"{API_BASE}/search", params)
    except LrcLibError:
        raise
    except requests.RequestException as exc:
        raise LrcLibError(f"Network error contacting lrclib.net: {exc}") from exc

    if resp.status_code != 200:
        raise LrcLibError(f"lrclib.net returned HTTP {resp.status_code}")

    results = resp.json()
    if not results:
        return None

    # Prefer the first result that actually has synced lyrics.
    for result in results:
        synced = result.get("syncedLyrics")
        if synced:
            return synced

    return None
