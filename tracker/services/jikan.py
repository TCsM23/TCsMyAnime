"""Client for the Jikan v4 API (unofficial MyAnimeList API).

Use it by setting ANIME_API = "jikan" in settings. Limits: 3 requests/sec, 60/min.
"""

import hashlib
import logging
import time

import requests
from django.conf import settings
from django.db import transaction

from tracker.models import Anime
from tracker.services.common import (
    SEASONS, TOP_FILTERS, UNREACHABLE, AnimeAPIError, Throttle, cached_list, genre_by_name,
)

log = logging.getLogger(__name__)
JikanError = AnimeAPIError  # old name, kept so existing imports still work

_throttle = Throttle()
_session = requests.Session()
_session.headers["User-Agent"] = "AnimeTracker student project (Django)"


def _get(path, params=None):
    url = f"{settings.JIKAN_BASE_URL}{path}"
    for attempt in range(settings.JIKAN_MAX_RETRIES + 1):
        _throttle.wait(settings.JIKAN_MIN_INTERVAL)
        try:
            resp = _session.get(url, params=params, timeout=(5, 15))
        except requests.ConnectionError as exc:
            log.warning("Jikan unreachable: %s", exc)  # blocked or offline: fail fast, no retries
            raise AnimeAPIError(UNREACHABLE) from exc
        except requests.RequestException as exc:
            if attempt == settings.JIKAN_MAX_RETRIES:
                log.warning("Jikan request failed: %s", exc)
                raise AnimeAPIError(UNREACHABLE) from exc
            time.sleep(2**attempt)
            continue

        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 404:
            raise AnimeAPIError("Anime not found on MyAnimeList.")
        if resp.status_code == 429 or resp.status_code >= 500:
            time.sleep(2**attempt)  # rate-limited or MAL is down: back off and retry
            continue
        raise AnimeAPIError(f"Jikan returned HTTP {resp.status_code}.")
    raise AnimeAPIError("The anime database is rate-limiting us right now. Try again in a minute.")


def _list(path, params):
    data = _get(path, params=params)
    animes = [save_anime_from_api(item) for item in data.get("data", [])]
    return animes, bool(data.get("pagination", {}).get("has_next_page"))


def search(query, page=1, limit=24):
    query = query.strip()
    if not query:
        return [], False
    params = {"q": query, "page": page, "limit": limit, "sfw": "true", "order_by": "members", "sort": "desc"}
    qhash = hashlib.md5(query.lower().encode()).hexdigest()  # safe cache key for any query text
    return cached_list(f"jikan-search:{qhash}:{page}:{limit}", lambda: _list("/anime", params), 60 * 10)


def top(page=1, filter_=""):
    params = {"page": page, "limit": 25}
    if filter_ in TOP_FILTERS and filter_:
        params["filter"] = filter_
    return cached_list(f"jikan-top:{filter_}:{page}", lambda: _list("/top/anime", params), 60 * 60 * 6)


def seasonal(year=None, season=None, page=1):
    """Current season if year/season are None, otherwise /seasons/{year}/{season}."""
    if year and season in SEASONS:
        path, key = f"/seasons/{year}/{season}", f"jikan-season:{year}:{season}:{page}"
    else:
        path, key = "/seasons/now", f"jikan-season:now:{page}"
    params = {"page": page, "limit": 25, "sfw": "true"}
    return cached_list(key, lambda: _list(path, params), 60 * 60 * 6)


def catalog_page(page):
    """One page of the full catalog for import_catalog. Returns (saved count, has_next, last page)."""
    data = _get("/anime", params={"page": page, "limit": 25, "order_by": "mal_id", "sort": "asc", "sfw": "true"})
    items = data.get("data", [])
    for item in items:
        save_anime_from_api(item)
    pag = data.get("pagination", {})
    return len(items), bool(pag.get("has_next_page")), pag.get("last_visible_page", "?")


@transaction.atomic
def save_anime_from_api(item):
    """Upsert one Jikan anime payload (plus its genres) into the DB."""
    images = item.get("images", {}).get("jpg", {})
    anime, _ = Anime.objects.update_or_create(
        mal_id=item["mal_id"],
        defaults={
            "title": item.get("title") or "Untitled",
            "title_english": item.get("title_english") or "",
            "episodes": item.get("episodes"),
            "image_url": images.get("large_image_url") or images.get("image_url") or "",
            "synopsis": item.get("synopsis") or "",
            "score": item.get("score"),
            "airing_status": item.get("status") or "",
            "year": item.get("year"),
            "season": item.get("season") or "",
            "media_type": item.get("type") or "",
            "studios": ", ".join(st["name"] for st in item.get("studios", [])),
            "rank": item.get("rank"),
            "members": item.get("members"),
            "trailer_url": (item.get("trailer") or {}).get("url") or "",
        },
    )
    anime.genres.set([genre_by_name(g["name"], g["mal_id"]) for g in item.get("genres", [])])
    return anime


def refresh_anime(mal_id):
    """Always re-fetch from the API (used for shows that are still airing)."""
    return save_anime_from_api(_get(f"/anime/{mal_id}")["data"])
