"""Client for the AniList GraphQL API (https://anilist.gitbook.io/anilist-apiv2-docs).

Every request is a POST to one URL with a GraphQL query. We still key shows by their
MyAnimeList ID (AniList's `idMal`), so URLs and saved data match the Jikan version.
"""

import hashlib
import logging
import re
import time
from datetime import date
from html import unescape

import requests
from django.conf import settings
from django.db import transaction
from django.utils.html import strip_tags

from tracker.models import Anime
from tracker.services.common import (
    SEASONS, TOP_FILTERS, UNREACHABLE, AnimeAPIError, Throttle, cached_list, genre_by_name,
)

log = logging.getLogger(__name__)

_throttle = Throttle()
_session = requests.Session()
_session.headers.update({"User-Agent": "AnimeTracker student project (Django)", "Accept": "application/json"})

# The fields we ask AniList for, on every query
MEDIA_FIELDS = """
  id idMal
  title { romaji english }
  episodes format status season seasonYear startDate { year }
  averageScore meanScore popularity genres
  coverImage { extraLarge large }
  description(asHtml: false)
  studios(isMain: true) { nodes { name } }
  trailer { id site }
  rankings { rank type allTime }
"""

PAGE_QUERY = """
query ($page: Int, $perPage: Int, $search: String, $sort: [MediaSort],
       $status: MediaStatus, $season: MediaSeason, $seasonYear: Int) {
  Page(page: $page, perPage: $perPage) {
    pageInfo { hasNextPage lastPage }
    media(type: ANIME, isAdult: false, search: $search, sort: $sort,
          status: $status, season: $season, seasonYear: $seasonYear) { %s }
  }
}
""" % MEDIA_FIELDS

ONE_QUERY = """
query ($idMal: Int) {
  Media(idMal: $idMal, type: ANIME) { %s }
}
""" % MEDIA_FIELDS

# AniList codes -> the wording the rest of the app (and the Jikan version) uses
STATUS = {
    "FINISHED": "Finished Airing", "RELEASING": "Currently Airing",
    "NOT_YET_RELEASED": "Not yet aired", "CANCELLED": "Cancelled", "HIATUS": "On Hiatus",
}
FORMAT = {
    "TV": "TV", "TV_SHORT": "TV Short", "MOVIE": "Movie", "SPECIAL": "Special",
    "OVA": "OVA", "ONA": "ONA", "MUSIC": "Music",
}
TOP_ARGS = {
    "": {"sort": ["SCORE_DESC"]},
    "airing": {"sort": ["SCORE_DESC"], "status": "RELEASING"},
    "upcoming": {"sort": ["POPULARITY_DESC"], "status": "NOT_YET_RELEASED"},
    "bypopularity": {"sort": ["POPULARITY_DESC"]},
}


def _post(query, variables):
    """Send one GraphQL query, with throttling and retry on 429/5xx."""
    for attempt in range(settings.ANILIST_MAX_RETRIES + 1):
        _throttle.wait(settings.ANILIST_MIN_INTERVAL)
        try:
            resp = _session.post(settings.ANILIST_URL, json={"query": query, "variables": variables},
                                 timeout=(5, 20))
        except requests.ConnectionError as exc:
            log.warning("AniList unreachable: %s", exc)  # blocked or offline: fail fast
            raise AnimeAPIError(UNREACHABLE) from exc
        except requests.RequestException as exc:
            if attempt == settings.ANILIST_MAX_RETRIES:
                log.warning("AniList request failed: %s", exc)
                raise AnimeAPIError(UNREACHABLE) from exc
            time.sleep(2**attempt)
            continue

        if resp.status_code == 429:
            # AniList says how long to wait in the Retry-After header
            time.sleep(int(resp.headers.get("Retry-After", 2**attempt)))
            continue
        if resp.status_code >= 500:
            time.sleep(2**attempt)
            continue

        body = resp.json()
        if resp.status_code == 404 or (body.get("errors") and any(
            e.get("status") == 404 for e in body["errors"]
        )):
            raise AnimeAPIError("Anime not found.")
        if body.get("errors"):
            log.warning("AniList errors: %s", body["errors"])
            raise AnimeAPIError("The anime database returned an error.")
        return body["data"]
    raise AnimeAPIError("The anime database is rate-limiting us right now. Try again in a minute.")


def _clean_description(text):
    text = re.sub(r"<br\s*/?>", "\n", text or "")
    return unescape(strip_tags(text)).strip()


@transaction.atomic
def save_anime_from_api(m):
    """Upsert one AniList Media into the DB. Returns None for shows with no MyAnimeList ID."""
    if not m.get("idMal"):
        return None
    score = m.get("averageScore") or m.get("meanScore")
    rank = next((r["rank"] for r in m.get("rankings") or [] if r["type"] == "RATED" and r["allTime"]), None)
    trailer = m.get("trailer") or {}
    anime, _ = Anime.objects.update_or_create(
        mal_id=m["idMal"],
        defaults={
            "title": m["title"].get("romaji") or "Untitled",
            "title_english": m["title"].get("english") or "",
            "episodes": m.get("episodes"),
            "image_url": (m.get("coverImage") or {}).get("extraLarge") or (m.get("coverImage") or {}).get("large") or "",
            "synopsis": _clean_description(m.get("description")),
            "score": round(score / 10, 2) if score else None,  # AniList scores are out of 100
            "airing_status": STATUS.get(m.get("status"), ""),
            "year": m.get("seasonYear") or (m.get("startDate") or {}).get("year"),
            "season": (m.get("season") or "").lower(),
            "media_type": FORMAT.get(m.get("format"), m.get("format") or ""),
            "studios": ", ".join(n["name"] for n in (m.get("studios") or {}).get("nodes", [])),
            "rank": rank,
            "members": m.get("popularity"),
            "trailer_url": f"https://www.youtube.com/watch?v={trailer['id']}" if trailer.get("site") == "youtube" else "",
        },
    )
    anime.genres.set([genre_by_name(g) for g in m.get("genres") or []])
    return anime


def _page(page, per_page=25, **filters):
    variables = {"page": page, "perPage": per_page, **{k: v for k, v in filters.items() if v is not None}}
    data = _post(PAGE_QUERY, variables)["Page"]
    animes = [a for a in (save_anime_from_api(m) for m in data["media"]) if a]
    return animes, bool(data["pageInfo"]["hasNextPage"]), data["pageInfo"].get("lastPage")


def search(query, page=1, limit=24):
    query = query.strip()
    if not query:
        return [], False
    qhash = hashlib.md5(query.lower().encode()).hexdigest()
    fetch = lambda: _page(page, limit, search=query, sort=["SEARCH_MATCH"])[:2]
    return cached_list(f"anilist-search:{qhash}:{page}:{limit}", fetch, 60 * 10)


def top(page=1, filter_=""):
    args = TOP_ARGS.get(filter_, TOP_ARGS[""])
    return cached_list(f"anilist-top:{filter_}:{page}", lambda: _page(page, **args)[:2], 60 * 60 * 6)


def seasonal(year=None, season=None, page=1):
    if not (year and season in SEASONS):
        today = date.today()
        year, season = today.year, SEASONS[(today.month - 1) // 3]
    fetch = lambda: _page(page, season=season.upper(), seasonYear=year, sort=["POPULARITY_DESC"])[:2]
    return cached_list(f"anilist-season:{year}:{season}:{page}", fetch, 60 * 60 * 6)


def catalog_page(page):
    """One page (50 shows) of the full catalog for import_catalog."""
    animes, has_next, last = _page(page, per_page=50, sort=["ID"])
    return len(animes), has_next, last or "?"


def refresh_anime(mal_id):
    anime = save_anime_from_api(_post(ONE_QUERY, {"idMal": mal_id})["Media"])
    if anime is None:
        raise AnimeAPIError("Anime not found.")
    return anime
