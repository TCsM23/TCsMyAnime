"""The one module the rest of the app imports. It forwards to the source chosen in settings:

    ANIME_API = "anilist"   # default
    ANIME_API = "jikan"     # MyAnimeList via Jikan

Both sources expose the same functions, so views and commands don't care which one is active.
"""

from django.conf import settings

from tracker.models import Anime
from tracker.services.common import SEASONS, TOP_FILTERS, AnimeAPIError  # noqa: F401 (re-exported)


def _source():
    if getattr(settings, "ANIME_API", "anilist") == "jikan":
        from tracker.services import jikan as source
    else:
        from tracker.services import anilist as source
    return source


def source_name():
    return "Jikan (MyAnimeList)" if getattr(settings, "ANIME_API", "anilist") == "jikan" else "AniList"


def search(query, page=1):
    return _source().search(query, page=page)


def top(page=1, filter_=""):
    return _source().top(page=page, filter_=filter_)


def seasonal(year=None, season=None, page=1):
    return _source().seasonal(year, season, page=page)


def catalog_page(page):
    return _source().catalog_page(page)


def refresh_anime(mal_id):
    return _source().refresh_anime(mal_id)


def get_or_fetch_anime(mal_id):
    """Return the Anime from our DB, calling the API only if we don't have it yet."""
    anime = Anime.objects.filter(mal_id=mal_id).first()
    return anime or refresh_anime(mal_id)
