"""Copy the anime catalog into the local database (from AniList or Jikan, per settings.ANIME_API).

    python manage.py import_catalog --pages 5          # try a few pages first
    python manage.py import_catalog                    # everything
    python manage.py import_catalog --start 341        # resume after an interruption

The API client throttles itself, so this is slow on purpose (AniList: 50 shows/page, ~1 page/sec).
"""

from django.core.management.base import BaseCommand

from tracker.services import anime_api as api


class Command(BaseCommand):
    help = "Import anime into the local database, page by page."

    def add_arguments(self, parser):
        parser.add_argument("--start", type=int, default=1, help="Page to start from (for resuming).")
        parser.add_argument("--pages", type=int, default=0, help="How many pages to import (0 = all).")

    def handle(self, *args, start, pages, **options):
        self.stdout.write(f"Importing from {api.source_name()}...")
        page, done, saved = start, 0, 0
        while True:
            try:
                count, has_next, last = api.catalog_page(page)
            except api.AnimeAPIError as exc:
                self.stderr.write(self.style.ERROR(f"Stopped on page {page}: {exc}"))
                self.stderr.write(f"Resume with: python manage.py import_catalog --start {page}")
                return
            saved += count
            done += 1
            self.stdout.write(f"Page {page}/{last}: {count} saved ({saved} total)")
            if not has_next or (pages and done >= pages):
                break
            page += 1
        self.stdout.write(self.style.SUCCESS(f"Done. Imported {saved} anime."))
