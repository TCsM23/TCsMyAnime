from datetime import date
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Avg, Count, F, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from tracker.forms import SignUpForm, WatchlistEntryForm
from tracker.models import Anime, Genre, WatchlistEntry
from tracker.services import anime_api as api
from tracker.stats import build_stats


def _page_number(request):
    try:
        return max(1, int(request.GET.get("page", 1)))
    except ValueError:
        return 1


def _owned_ids(user):
    """MAL IDs on this user's list, so cards can show 'On your list'."""
    if not user.is_authenticated:
        return set()
    return set(WatchlistEntry.objects.filter(user=user).values_list("anime__mal_id", flat=True))


def _safe_next(request, fallback):
    nxt = request.POST.get("next") or request.META.get("HTTP_REFERER")
    return nxt or fallback


# ---------- accounts ----------

def signup(request):
    if request.user.is_authenticated:
        return redirect("watchlist")
    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, f"Welcome, {user.username}! Find a show to start your list.")
        return redirect("seasonal")
    return render(request, "registration/signup.html", {"form": form})


# ---------- discovery (public) ----------

def search(request):
    query = request.GET.get("q", "").strip()
    page = _page_number(request)
    results, has_next, error = [], False, None
    if query:
        try:
            results, has_next = api.search(query, page=page)
        except api.AnimeAPIError as exc:
            error = str(exc)
    return render(request, "tracker/search.html", {
        "query": query, "results": results, "error": error,
        "page": page, "has_next": has_next, "owned": _owned_ids(request.user),
        "base": urlencode({"q": query}),
    })


def top_anime(request):
    filter_ = request.GET.get("filter", "")
    if filter_ not in api.TOP_FILTERS:
        filter_ = ""
    page = _page_number(request)
    results, has_next, error = [], False, None
    try:
        results, has_next = api.top(page=page, filter_=filter_)
    except api.AnimeAPIError as exc:
        error = str(exc)
    return render(request, "tracker/top.html", {
        "results": results, "error": error, "page": page, "has_next": has_next,
        "filters": api.TOP_FILTERS.items(), "active": filter_,
        "rank_offset": (page - 1) * 25, "owned": _owned_ids(request.user),
        "base": urlencode({"filter": filter_}) if filter_ else "",
    })


def seasonal(request, year=None, season=None):
    if season and season not in api.SEASONS:
        raise Http404("Unknown season")
    page = _page_number(request)
    results, has_next, error = [], False, None
    try:
        results, has_next = api.seasonal(year, season, page=page)
    except api.AnimeAPIError as exc:
        error = str(exc)

    # Work out which season we're showing, and its neighbours for prev/next links
    today = date.today()
    cur_year = year or today.year
    cur_season = season or api.SEASONS[(today.month - 1) // 3]
    idx = api.SEASONS.index(cur_season)
    prev_s = (cur_year - 1, "fall") if idx == 0 else (cur_year, api.SEASONS[idx - 1])
    next_s = (cur_year + 1, "winter") if idx == 3 else (cur_year, api.SEASONS[idx + 1])

    return render(request, "tracker/seasonal.html", {
        "results": results, "error": error, "page": page, "has_next": has_next,
        "label": f"{cur_season.title()} {cur_year}", "prev_s": prev_s, "next_s": next_s, "base": "",
        "owned": _owned_ids(request.user),
    })


BROWSE_SORTS = {
    "-score": "Score",
    "-members": "Popularity",
    "-year": "Newest",
    "title": "Title A–Z",
}


def browse(request):
    """Browse the anime stored in OUR database (grows as people search, or via import_catalog)."""
    qs = Anime.objects.all()
    q = request.GET.get("q", "").strip()
    genre = request.GET.get("genre", "")
    media_type = request.GET.get("type", "")
    year = request.GET.get("year", "")
    sort = request.GET.get("sort", "-score")

    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(title_english__icontains=q))
    if genre.isdigit():
        qs = qs.filter(genres__mal_id=int(genre))
    if media_type:
        qs = qs.filter(media_type=media_type)
    if year.isdigit():
        qs = qs.filter(year=int(year))
    if sort not in BROWSE_SORTS:
        sort = "-score"
    field = sort.lstrip("-")
    # Nulls last so unscored / unknown-year shows don't crowd the top
    key = F(field).desc(nulls_last=True) if sort.startswith("-") else F(field).asc()
    qs = qs.order_by(key, "title").distinct()

    page_obj = Paginator(qs, 24).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)

    return render(request, "tracker/browse.html", {
        "page_obj": page_obj,
        "total": Anime.objects.count(),
        "genres": Genre.objects.all(),
        "types": Anime.objects.exclude(media_type="").values_list("media_type", flat=True).distinct().order_by("media_type"),
        "years": Anime.objects.exclude(year=None).values_list("year", flat=True).distinct().order_by("-year"),
        "sorts": BROWSE_SORTS.items(),
        "f": {"q": q, "genre": genre, "type": media_type, "year": year, "sort": sort},
        "querystring": params.urlencode(),
        "owned": _owned_ids(request.user),
    })


def anime_detail(request, mal_id):
    try:
        anime = api.get_or_fetch_anime(mal_id)
    except api.AnimeAPIError as exc:
        raise Http404(str(exc))

    # Shows saved without full details (demo seed, older rows): fill them in once
    if not anime.image_url or not anime.synopsis:
        try:
            anime = api.refresh_anime(mal_id)
        except api.AnimeAPIError:
            pass

    entries = anime.entries.all()
    community = entries.aggregate(avg=Avg("rating"), members=Count("id"))
    status_counts = dict(entries.values_list("status").annotate(n=Count("id")))
    members = community["members"] or 1
    community_statuses = [
        (key, label, status_counts.get(key, 0), round(status_counts.get(key, 0) / members * 100))
        for key, label in WatchlistEntry.Status.choices
    ]

    entry = None
    if request.user.is_authenticated:
        entry = entries.filter(user=request.user).first()

    return render(request, "tracker/anime_detail.html", {
        "anime": anime,
        "genres": anime.genres.all(),
        "entry": entry,
        "community": community,
        "community_statuses": community_statuses,
    })


# ---------- your list (login required) ----------

def watchlist(request):
    if not request.user.is_authenticated:
        return redirect("seasonal")  # logged-out visitors land on a public page
    entries = WatchlistEntry.objects.filter(user=request.user).select_related("anime")
    active = request.GET.get("status", "")
    if active in WatchlistEntry.Status.values:
        entries = entries.filter(status=active)
    counts = dict(
        WatchlistEntry.objects.filter(user=request.user).values_list("status").annotate(n=Count("id"))
    )
    statuses = [(key, label, counts.get(key, 0)) for key, label in WatchlistEntry.Status.choices]
    return render(request, "tracker/watchlist.html", {
        "entries": entries, "statuses": statuses, "active": active,
        "total": sum(counts.values()),
    })


@login_required
@require_POST
def add_to_watchlist(request, mal_id):
    try:
        anime = api.get_or_fetch_anime(mal_id)
    except api.AnimeAPIError as exc:
        messages.error(request, str(exc))
        return redirect(_safe_next(request, "search"))
    status = request.POST.get("status", WatchlistEntry.Status.PLAN_TO_WATCH)
    if status not in WatchlistEntry.Status.values:
        status = WatchlistEntry.Status.PLAN_TO_WATCH
    entry, created = WatchlistEntry.objects.get_or_create(
        user=request.user, anime=anime, defaults={"status": status}
    )
    if created:
        messages.success(request, f"Added {anime.display_title} as {entry.get_status_display()}.")
    else:
        messages.info(request, f"{anime.display_title} is already on your list.")
    return redirect(_safe_next(request, "watchlist"))


@login_required
def entry_edit(request, pk):
    entry = get_object_or_404(WatchlistEntry.objects.select_related("anime"), pk=pk, user=request.user)
    form = WatchlistEntryForm(request.POST or None, instance=entry)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Saved {entry.anime.display_title}.")
        return redirect(request.POST.get("next") or "watchlist")
    return render(request, "tracker/entry_form.html", {"form": form, "entry": entry})


@login_required
@require_POST
def entry_increment(request, pk):
    entry = get_object_or_404(WatchlistEntry.objects.select_related("anime"), pk=pk, user=request.user)
    total = entry.anime.episodes
    if total is None or entry.episodes_watched < total:
        entry.episodes_watched += 1
        entry.save()
        if entry.status == WatchlistEntry.Status.COMPLETED:
            messages.success(request, f"Finished {entry.anime.display_title}! Don't forget to rate it.")
    return redirect(_safe_next(request, "watchlist"))


@login_required
def entry_delete(request, pk):
    entry = get_object_or_404(WatchlistEntry.objects.select_related("anime"), pk=pk, user=request.user)
    if request.method == "POST":
        title = entry.anime.display_title
        entry.delete()
        messages.success(request, f"Removed {title} from your list.")
        return redirect("watchlist")
    return render(request, "tracker/entry_confirm_delete.html", {"entry": entry})


@login_required
def stats(request):
    return render(request, "tracker/stats.html", {"stats": build_stats(request.user)})
