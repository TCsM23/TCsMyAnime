from tracker.services import anime_api as api


def anime_api(request):
    """Lets templates show which data source is active (footer credit)."""
    return {"anime_source": api.source_name()}
