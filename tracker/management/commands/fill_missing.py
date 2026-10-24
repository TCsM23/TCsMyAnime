"""Fetch full details (poster, synopsis, studios, score) for anime saved without them.

    python manage.py fill_missing
"""

from django.core.management.base import BaseCommand
from django.db.models import Q

from tracker.models import Anime
from tracker.services import anime_api as api


class Command(BaseCommand):
    help = "Re-fetch anime that are missing a poster image or synopsis."

    def handle(self, *args, **options):
        qs = Anime.objects.filter(Q(image_url="") | Q(synopsis=""))
        total, done = qs.count(), 0
        for anime in qs.iterator():
            try:
                api.refresh_anime(anime.mal_id)
                done += 1
                self.stdout.write(f"[{done}/{total}] {anime}")
            except api.AnimeAPIError as exc:
                self.stderr.write(self.style.ERROR(f"Stopped at {anime}: {exc}"))
                break
        self.stdout.write(self.style.SUCCESS(f"Filled {done} of {total}."))
