from django.contrib import admin

from tracker.models import Anime, Genre, WatchlistEntry


@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    list_display = ("name", "mal_id")
    search_fields = ("name",)


@admin.register(Anime)
class AnimeAdmin(admin.ModelAdmin):
    list_display = ("title", "episodes", "score", "year", "airing_status", "fetched_at")
    search_fields = ("title", "title_english")
    list_filter = ("airing_status", "genres")
    filter_horizontal = ("genres",)


@admin.register(WatchlistEntry)
class WatchlistEntryAdmin(admin.ModelAdmin):
    list_display = ("user", "anime", "status", "episodes_watched", "rating", "updated_at")
    list_filter = ("status", "user")
    search_fields = ("anime__title", "user__username")
    autocomplete_fields = ("anime",)
