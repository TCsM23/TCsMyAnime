"""Re-fetch shows that are still airing, so episode counts and scores stay current.

    python manage.py refresh_airing

Run it daily or weekly (PythonAnywhere "Tasks", Windows Task Scheduler, or cron).
Only airing shows change, so this is a few hundred calls at most, not the whole catalog.
"""

from django.core.management.base import BaseCommand

from tracker.models import Anime
from tracker.services import anime_api as api


class Command(BaseCommand):
    help = "Refresh anime whose status is 'Currently Airing' (or not yet aired)."

    def add_arguments(self, parser):
        parser.add_argument("--tracked-only", action="store_true",
                            help="Only refresh shows that are on at least one user's list.")

    def handle(self, *args, tracked_only, **options):
        qs = Anime.objects.filter(airing_status__in=["Currently Airing", "Not yet aired"])
        if tracked_only:
            qs = qs.filter(entries__isnull=False).distinct()
        total = qs.count()
        updated = 0
        for i, anime in enumerate(qs.iterator(), start=1):
            try:
                api.refresh_anime(anime.mal_id)
                updated += 1
            except api.AnimeAPIError as exc:
                self.stderr.write(f"[{i}/{total}] {anime}: {exc}")
                continue
            self.stdout.write(f"[{i}/{total}] {anime}")
        self.stdout.write(self.style.SUCCESS(f"Refreshed {updated} of {total} shows."))
