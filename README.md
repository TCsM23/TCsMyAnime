# TCsMyAnime: Anime Tracker (Django)

**Live demo:** https://YOUR-SITE.onrender.com *(free hosting: the first load can take about a minute while the site wakes up)*

A watchlist app with user accounts, status, ratings, and episode progress. Anime data comes from [AniList](https://anilist.co) by default, or from [Jikan](https://docs.api.jikan.moe) (unofficial MyAnimeList API) if you set `ANIME_API=jikan`. A stats page uses pandas to break down genres and completion rate.

## Run it (Windows)

```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser      :: for /admin
python manage.py seed_demo            :: optional: demo / demo-pass-123
python manage.py runserver
```

Open http://127.0.0.1:8000. Browse **Seasonal**, **Top** or **Search**, sign up, and add shows to your list.

Optional, to fill **Browse** with the whole catalog (about 20–30 minutes, resumable):

```bat
python manage.py import_catalog --pages 5     :: try 125 shows first
python manage.py import_catalog               :: everything
python manage.py refresh_airing               :: run daily/weekly to update airing shows
python manage.py fill_missing                 :: fetch posters/synopses for shows saved without them
```
Run the tests with `python manage.py test tracker`.

## Design (mood board)

| | |
|---|---|
| Palette | `#050309` black · `#780000` dark red · `#c1121f` bright red · `#fdf0d5` vanilla · `#003049` dark blue · `#669bbc` light blue (tokens at the top of `static/css/style.css`) |
| Headings | Lilita One (self-hosted in `static/fonts/`) |
| Body | Gagalin. Not freely redistributable here, so drop `Gagalin-Regular.otf` into `static/fonts/` and it's picked up; until then Fredoka is used |
| Style | "Sticker" cards: 2px black outlines + hard offset shadows, rounded corners |
| Motion | Staggered card entrances, bars that grow in, pop-in messages, logo wiggle; all disabled with the OS "reduce motion" setting |
| Logo | `static/brand/` (SVG + PNG); regenerate with `static/brand/build_logo.py` |

## How it's organized

| File | What it does |
|---|---|
| `tracker/models.py` | `Genre`, `Anime` (local cache of API data), `WatchlistEntry` (user ↔ anime + progress) |
| `tracker/services/anime_api.py` | The switch the app imports; forwards to AniList or Jikan per `settings.ANIME_API` |
| `tracker/services/anilist.py` | AniList GraphQL client (default) |
| `tracker/services/jikan.py` | Jikan REST client (MyAnimeList data) |
| `tracker/services/common.py` | Shared throttle, caching, genre IDs and error type |
| `tracker/stats.py` | pandas stats: status breakdown, genre counts, completion rate |
| `tracker/views.py` | Seasonal, Top, Browse, Search, anime detail, watchlist CRUD, stats, signup |
| `tracker/forms.py` | Signup form and the watchlist `ModelForm` |
| `tracker/admin.py` | Admin config for all three models |
| `tracker/management/commands/seed_demo.py` | Offline demo data |
| `tracker/management/commands/import_catalog.py` | Bulk-copy the MAL catalog into the local DB |
| `tracker/management/commands/refresh_airing.py` | Re-fetch airing shows so episode counts stay current |
| `tracker/templates/tracker/_anime_card.html` | Shared card used by Search, Top, Seasonal, Browse |
| `tracker/tests.py` | 29 tests (constraints, auth scoping, both API sources, catalog pages, import, season picker, confirmations, stats math) |

## Pages

| URL | Who | What |
|---|---|---|
| `/seasonal/`, `/seasonal/2026/fall/` | Everyone | Shows by season with prev/next season links |
| `/top/` | Everyone | Top, Top Airing, Top Upcoming, Most Popular |
| `/search/` | Everyone | Search the full anime catalog, paginated |
| `/browse/` | Everyone | Filter saved anime by title, genre, type, year; sort by score, popularity, newest |
| `/anime/<mal_id>/` | Everyone | Details, MAL score and rank, this site's score, status breakdown, add/edit |
| `/` My List, `/stats/` | Logged in | Your watchlist and pandas stats |
| `/accounts/password_reset/` | Everyone | Password reset (email prints in the terminal during development) |

## Design decisions worth understanding

- **Two interchangeable sources.** Only `tracker/services/` talks to an API. Shows are keyed by their MyAnimeList ID in both, so switching sources keeps your data and URLs.
- **Fetch once, read from the DB.** AniList allows about 90 requests/min and Jikan 60/min. `get_or_fetch_anime()` only calls the API when a show isn't in our `Anime` table yet. Search results are cached for 10 minutes.
- **Progress lives on `WatchlistEntry`, not `Anime`.** Two users can be at different episodes of the same show.
- **`UniqueConstraint(user, anime)`** stops duplicate entries at the database level, not just in the form.
- **Every query filters by `request.user`.** Changing the ID in `/entry/5/` to someone else's entry returns 404 (there's a test for this).
- **`save()` auto-updates status.** Watching the last episode sets Completed; the first episode moves Plan to Watch → Watching.
- **Completion rate** = Completed ÷ every entry except Plan to Watch. You can argue for including Plan to Watch; it changes the number a lot.

## Database

Locally the app uses SQLite (`db.sqlite3`). Set `DATABASE_URL` and it uses PostgreSQL instead, with no code changes:

```powershell
$env:DATABASE_URL = "postgresql://user:password@host:5432/dbname"
python manage.py migrate
```

Tested on PostgreSQL 16. The database file is never committed (see `.gitignore`).

## Deploying to Render

## Deploying to Render (with Neon PostgreSQL)

The site runs as a Render **web service**; the database is a free **Neon** PostgreSQL (Render allows one free database per account, and Neon's free plan doesn't expire).

1. **Neon:** create a project (region: Singapore), click **Connect**, turn **Connection pooling off**, and copy the connection string.
2. **Render:** New → Web Service → pick this repo, then:

| Setting | Value |
|---|---|
| Region | Singapore (same as the database) |
| Build Command | `bash build.sh` |
| Start Command | `gunicorn config.wsgi:application` |
| Instance Type | Free |

3. **Environment variables** (set in Render, never committed):

| Key | Value |
|---|---|
| `DATABASE_URL` | Neon connection string |
| `DJANGO_SECRET_KEY` | Generate |
| `DJANGO_DEBUG` | `0` |
| `ANIME_API` | `anilist` |
| `PYTHON_VERSION` | `3.13.5` |
| `DJANGO_SUPERUSER_USERNAME` / `_EMAIL` / `_PASSWORD` | admin account, created on first deploy |

Each deploy runs `build.sh`: install → `collectstatic` → `migrate` → create admin if missing. gunicorn serves the site, WhiteNoise the static files. Every push to `main` redeploys.

**Free-plan notes:** the site sleeps after 15 minutes idle. There's no shell or cron, so run maintenance commands from your PC against Neon:

```powershell
$env:DATABASE_URL = "<Neon connection string>"
python manage.py import_catalog --pages 5   # or fill_missing / refresh_airing
Remove-Item Env:DATABASE_URL
```

`render.yaml` is an optional Blueprint version of the same setup (web service only).

## Ideas for next steps (community features)

- Public profile pages showing each user's list and stats
- Reviews with "helpful" votes, favorites, following users, an activity feed
- Recommendations ("people who liked X also liked Y") from watchlist overlap with pandas
- PostgreSQL + full-text search once the catalog and user count grow
