"""Create a demo user with a sample watchlist, without calling the API.

Usage: python manage.py seed_demo
Login: demo / demo-pass-123
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from tracker.models import Anime, Genre, WatchlistEntry
from tracker.services import anime_api as api

GENRES = {1: "Action", 2: "Adventure", 4: "Comedy", 8: "Drama", 10: "Fantasy", 22: "Romance", 24: "Sci-Fi", 36: "Slice of Life"}

# Extra catalog fields per show: (type, season, studios, MAL score)
EXTRA = {
    52991: ("TV", "fall", "Madhouse", 9.3), 1: ("TV", "spring", "Sunrise", 8.75),
    5114: ("TV", "spring", "Bones", 9.1), 9253: ("TV", "spring", "White Fox", 9.07),
    16498: ("TV", "spring", "Wit Studio", 8.55), 32281: ("Movie", "summer", "CoMix Wave Films", 8.83),
    50265: ("TV", "spring", "Wit Studio, CloverWorks", 8.5), 37521: ("TV", "summer", "Wit Studio", 8.75),
}

# (mal_id, title, english title, episodes, year, genre ids, status, watched, rating)
SAMPLE = [
    (52991, "Sousou no Frieren", "Frieren: Beyond Journey's End", 28, 2023, [2, 8, 10], "completed", 28, 10),
    (1, "Cowboy Bebop", "Cowboy Bebop", 26, 1998, [1, 24], "completed", 26, 9),
    (5114, "Fullmetal Alchemist: Brotherhood", "Fullmetal Alchemist: Brotherhood", 64, 2009, [1, 2, 8, 10], "watching", 37, None),
    (9253, "Steins;Gate", "Steins;Gate", 24, 2011, [8, 24], "on_hold", 10, None),
    (16498, "Shingeki no Kyojin", "Attack on Titan", 25, 2013, [1, 8], "dropped", 6, 6),
    (32281, "Kimi no Na wa.", "Your Name.", 1, 2016, [8, 22], "completed", 1, 9),
    (50265, "Spy x Family", "Spy x Family", 12, 2022, [1, 4], "plan_to_watch", 0, None),
    (37521, "Vinland Saga", "Vinland Saga", 24, 2019, [1, 2, 8], "plan_to_watch", 0, None),
]


class Command(BaseCommand):
    help = "Seed a demo user and sample watchlist (works offline)."

    def handle(self, *args, **options):
        User = get_user_model()
        user, created = User.objects.get_or_create(username="demo")
        if created:
            user.set_password("demo-pass-123")
            user.save()

        genres = {gid: Genre.objects.get_or_create(mal_id=gid, defaults={"name": n})[0] for gid, n in GENRES.items()}

        for mal_id, title, eng, eps, year, gids, status, watched, rating in SAMPLE:
            anime, _ = Anime.objects.update_or_create(
                mal_id=mal_id,
                defaults={
                    "title": title, "title_english": eng, "episodes": eps, "year": year,
                    "media_type": EXTRA[mal_id][0], "season": EXTRA[mal_id][1],
                    "studios": EXTRA[mal_id][2], "score": EXTRA[mal_id][3],
                    "airing_status": "Finished Airing",
                },
            )
            anime.genres.set([genres[g] for g in gids])
            WatchlistEntry.objects.update_or_create(
                user=user, anime=anime,
                defaults={"status": status, "episodes_watched": watched, "rating": rating},
            )

        # Try to pull real posters, synopses and scores; keep the offline data if the API is unreachable
        self.stdout.write("Fetching posters and details...")
        filled = 0
        for mal_id, *_ in SAMPLE:
            try:
                api.refresh_anime(mal_id)
                filled += 1
            except api.AnimeAPIError as exc:
                self.stderr.write(f"  Skipped details for {mal_id}: {exc}")
                break
        self.stdout.write(self.style.SUCCESS(
            f"Seeded ({filled}/{len(SAMPLE)} with full details). Log in as demo / demo-pass-123"
        ))
