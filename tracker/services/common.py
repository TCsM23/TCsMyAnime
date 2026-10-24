"""Pieces shared by every anime data source (AniList, Jikan)."""

import time

from django.core.cache import cache

from tracker.models import Anime, Genre

UNREACHABLE = "Couldn't reach the anime database right now. Check your internet and try again."

SEASONS = ["winter", "spring", "summer", "fall"]
TOP_FILTERS = {"": "All", "airing": "Top Airing", "upcoming": "Top Upcoming", "bypopularity": "Most Popular"}

# Genre IDs follow MyAnimeList's numbering, so AniList and Jikan data share the same Genre rows.
GENRE_IDS = {
    "Action": 1, "Adventure": 2, "Comedy": 4, "Mystery": 7, "Drama": 8, "Ecchi": 9,
    "Fantasy": 10, "Horror": 14, "Mecha": 18, "Music": 19, "Romance": 22, "Sci-Fi": 24,
    "Sports": 30, "Slice of Life": 36, "Supernatural": 37, "Psychological": 40,
    "Thriller": 41, "Suspense": 41, "Mahou Shoujo": 66,
}


class AnimeAPIError(Exception):
    """Raised when the anime data source can't be reached or keeps failing."""


class Throttle:
    """Keeps calls at least `interval` seconds apart."""

    def __init__(self):
        self.last = 0.0

    def wait(self, interval):
        delay = interval - (time.monotonic() - self.last)
        if delay > 0:
            time.sleep(delay)
        self.last = time.monotonic()


def genre_by_name(name, mal_id=None):
    """Find or create a Genre, matching by name first so both sources share rows."""
    genre = Genre.objects.filter(name=name).first()
    if genre:
        return genre
    gid = mal_id or GENRE_IDS.get(name)
    if gid is None or Genre.objects.filter(mal_id=gid).exists():
        # Unknown to our map: give it a free ID above MAL's range
        gid = max(1000, (Genre.objects.order_by("-mal_id").values_list("mal_id", flat=True).first() or 0) + 1)
    return Genre.objects.create(mal_id=gid, name=name)


def unique(ids):
    seen = set()
    return [i for i in ids if not (i in seen or seen.add(i))]


def cached_list(key, fetch, ttl):
    """Run `fetch()` -> (saved Anime list, has_next) once, then serve the IDs from cache.

    Every result is saved to our DB, so detail pages for these shows need no extra API call.
    """
    cached = cache.get(key)
    if cached is None:
        animes, has_next = fetch()
        cached = {"ids": unique(a.mal_id for a in animes), "has_next": has_next}
        cache.set(key, cached, ttl)
    by_id = Anime.objects.in_bulk(cached["ids"], field_name="mal_id")
    return [by_id[i] for i in cached["ids"] if i in by_id], cached["has_next"]
