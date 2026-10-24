from django.contrib.staticfiles import finders

from tracker.services import anime_api as api


def anime_api(request):
    """Lets templates show which data source is active (footer credit)."""
    return {"anime_source": api.source_name()}


def optional_fonts(request):
    """Gagalin is licensed separately, so it only loads if you've added the file to static/fonts."""
    for name, fmt in (("Gagalin-Regular.woff2", "woff2"), ("Gagalin-Regular.otf", "opentype"),
                      ("Gagalin-Regular.ttf", "truetype")):
        if finders.find(f"fonts/{name}"):
            return {"gagalin_font": {"path": f"fonts/{name}", "format": fmt}}
    return {}
