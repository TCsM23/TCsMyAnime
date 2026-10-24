from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Genre(models.Model):
    """A genre from MyAnimeList. Its own table so names aren't duplicated per anime."""

    mal_id = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Anime(models.Model):
    """Local cache of an anime fetched from Jikan.

    We save shows here once and read from our own DB afterwards,
    so page views never hit the API (that's how we respect the rate limit).
    """

    mal_id = models.PositiveIntegerField(unique=True)
    title = models.CharField(max_length=255)
    title_english = models.CharField(max_length=255, blank=True)
    episodes = models.PositiveIntegerField(null=True, blank=True)  # null = unknown / still airing
    image_url = models.URLField(blank=True)
    synopsis = models.TextField(blank=True)
    score = models.FloatField(null=True, blank=True)  # MAL community score
    airing_status = models.CharField(max_length=50, blank=True)
    year = models.PositiveIntegerField(null=True, blank=True)
    season = models.CharField(max_length=10, blank=True)  # winter / spring / summer / fall
    media_type = models.CharField(max_length=20, blank=True)  # TV, Movie, OVA, ...
    studios = models.CharField(max_length=255, blank=True)  # comma-separated names
    rank = models.PositiveIntegerField(null=True, blank=True)  # MAL rank
    members = models.PositiveIntegerField(null=True, blank=True)  # MAL member count
    trailer_url = models.URLField(blank=True)
    genres = models.ManyToManyField(Genre, related_name="anime", blank=True)
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]
        verbose_name_plural = "anime"

    def __str__(self):
        return self.title

    @property
    def display_title(self):
        return self.title_english or self.title

    @property
    def is_airing(self):
        return self.airing_status == "Currently Airing"

    @property
    def season_label(self):
        if self.season and self.year:
            return f"{self.season.title()} {self.year}"
        return str(self.year or "")


class WatchlistEntry(models.Model):
    """The join between a user and an anime, plus that user's own data.

    Progress lives here, not on Anime, because two users can watch
    the same show at different points.
    """

    class Status(models.TextChoices):
        WATCHING = "watching", "Watching"
        COMPLETED = "completed", "Completed"
        ON_HOLD = "on_hold", "On Hold"
        DROPPED = "dropped", "Dropped"
        PLAN_TO_WATCH = "plan_to_watch", "Plan to Watch"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="watchlist"
    )
    anime = models.ForeignKey(Anime, on_delete=models.CASCADE, related_name="entries")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLAN_TO_WATCH)
    rating = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="Your score, 1-10",
    )
    episodes_watched = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name_plural = "watchlist entries"
        constraints = [
            # One entry per user per show
            models.UniqueConstraint(fields=["user", "anime"], name="unique_user_anime"),
        ]

    def __str__(self):
        return f"{self.user} - {self.anime} ({self.get_status_display()})"

    def clean(self):
        total = self.anime.episodes if self.anime_id else None
        if total is not None and self.episodes_watched > total:
            raise ValidationError(
                {"episodes_watched": f"This show only has {total} episodes."}
            )

    def save(self, *args, **kwargs):
        total = self.anime.episodes
        if total and self.episodes_watched >= total:
            # Finishing the last episode marks the show as completed
            self.episodes_watched = total
            self.status = self.Status.COMPLETED
        elif self.status == self.Status.PLAN_TO_WATCH and self.episodes_watched > 0:
            self.status = self.Status.WATCHING
        super().save(*args, **kwargs)

    @property
    def progress_percent(self):
        if not self.anime.episodes:
            return None
        return round(self.episodes_watched / self.anime.episodes * 100)
