from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.urls import reverse

from tracker.models import Anime, Genre, WatchlistEntry
from tracker.services import anime_api as api
from tracker.stats import build_stats

User = get_user_model()

FAKE_JIKAN_ANIME = {
    "data": {
        "mal_id": 52991,
        "title": "Sousou no Frieren",
        "title_english": "Frieren: Beyond Journey's End",
        "episodes": 28,
        "images": {"jpg": {"image_url": "https://example.com/f.jpg"}},
        "synopsis": "An elf mage...",
        "score": 9.3,
        "status": "Finished Airing",
        "year": 2023,
        "genres": [{"mal_id": 2, "name": "Adventure"}, {"mal_id": 10, "name": "Fantasy"}],
    }
}


class ModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="pw-12345-abc")
        self.anime = Anime.objects.create(mal_id=1, title="Cowboy Bebop", episodes=26)

    def test_unique_user_anime(self):
        WatchlistEntry.objects.create(user=self.user, anime=self.anime)
        with self.assertRaises(IntegrityError):
            WatchlistEntry.objects.create(user=self.user, anime=self.anime)

    def test_cannot_exceed_episode_count(self):
        entry = WatchlistEntry(user=self.user, anime=self.anime, episodes_watched=30)
        with self.assertRaises(ValidationError):
            entry.full_clean()

    def test_last_episode_marks_completed(self):
        entry = WatchlistEntry.objects.create(user=self.user, anime=self.anime, episodes_watched=26)
        self.assertEqual(entry.status, WatchlistEntry.Status.COMPLETED)

    def test_first_episode_moves_plan_to_watching(self):
        entry = WatchlistEntry.objects.create(user=self.user, anime=self.anime, episodes_watched=1)
        self.assertEqual(entry.status, WatchlistEntry.Status.WATCHING)


@override_settings(ANIME_API="jikan")
class JikanServiceTests(TestCase):
    @patch("tracker.services.jikan._get", return_value=FAKE_JIKAN_ANIME)
    def test_fetches_once_then_uses_db(self, mock_get):
        a1 = api.get_or_fetch_anime(52991)
        a2 = api.get_or_fetch_anime(52991)
        self.assertEqual(a1.pk, a2.pk)
        self.assertEqual(mock_get.call_count, 1)  # second call came from our DB
        self.assertEqual(a1.genres.count(), 2)
        self.assertEqual(Genre.objects.count(), 2)


@override_settings(ANIME_API="jikan")
class ViewTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="pw-12345-abc")
        self.bob = User.objects.create_user("bob", password="pw-12345-abc")
        self.anime = Anime.objects.create(mal_id=1, title="Cowboy Bebop", episodes=26)
        self.bob_entry = WatchlistEntry.objects.create(user=self.bob, anime=self.anime)

    def test_logged_out_home_goes_to_seasonal(self):
        resp = self.client.get(reverse("watchlist"))
        self.assertRedirects(resp, reverse("seasonal"), fetch_redirect_response=False)

    def test_stats_requires_login(self):
        resp = self.client.get(reverse("stats"))
        self.assertRedirects(resp, f"{reverse('login')}?next=/stats/")

    def test_cannot_edit_another_users_entry(self):
        self.client.login(username="alice", password="pw-12345-abc")
        resp = self.client.get(reverse("entry_edit", args=[self.bob_entry.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_signup_logs_in(self):
        resp = self.client.post(reverse("signup"), {
            "username": "carol", "password1": "Sup3r-Secret-99", "password2": "Sup3r-Secret-99",
        })
        self.assertRedirects(resp, reverse("seasonal"), fetch_redirect_response=False)

    @patch("tracker.services.jikan._get", return_value=FAKE_JIKAN_ANIME)
    def test_add_and_increment(self, _):
        self.client.login(username="alice", password="pw-12345-abc")
        self.client.post(reverse("add_to_watchlist", args=[52991]))
        entry = WatchlistEntry.objects.get(user=self.alice, anime__mal_id=52991)
        self.client.post(reverse("entry_increment", args=[entry.pk]))
        entry.refresh_from_db()
        self.assertEqual(entry.episodes_watched, 1)
        self.assertEqual(entry.status, WatchlistEntry.Status.WATCHING)

    def test_pages_render(self):
        self.client.login(username="bob", password="pw-12345-abc")
        for name in ("watchlist", "search", "stats", "browse", "password_reset"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)


class StatsTests(TestCase):
    def test_completion_rate_excludes_plan_to_watch(self):
        user = User.objects.create_user("dave", password="pw-12345-abc")
        action = Genre.objects.create(mal_id=1, name="Action")
        for i, (status, rating) in enumerate([("completed", 8), ("completed", 10), ("dropped", 4), ("plan_to_watch", None)]):
            a = Anime.objects.create(mal_id=100 + i, title=f"Show {i}", episodes=None)
            a.genres.add(action)
            WatchlistEntry.objects.create(user=user, anime=a, status=status, rating=rating)
        s = build_stats(user)
        self.assertEqual(s["total"], 4)
        self.assertEqual(s["completion_rate"], 66.7)  # 2 completed / 3 started
        self.assertEqual(s["avg_rating"], 7.33)
        self.assertEqual(s["genres"][0]["count"], 4)


def fake_list(*items, has_next=False):
    return {"data": list(items), "pagination": {"has_next_page": has_next, "last_visible_page": 1}}


FRIEREN = FAKE_JIKAN_ANIME["data"]
BEBOP = {**FRIEREN, "mal_id": 1, "title": "Cowboy Bebop", "title_english": "Cowboy Bebop",
         "episodes": 26, "year": 1998, "type": "TV", "genres": [{"mal_id": 1, "name": "Action"}]}


@override_settings(ANIME_API="jikan")
class CatalogTests(TestCase):
    def setUp(self):
        cache.clear()

    @patch("tracker.services.jikan._get", return_value=fake_list(FRIEREN, BEBOP, has_next=True))
    def test_top_page_saves_results_and_paginates(self, mock_get):
        resp = self.client.get(reverse("top"))
        self.assertContains(resp, "Cowboy Bebop")
        self.assertContains(resp, "Next")
        self.assertEqual(Anime.objects.count(), 2)  # list results are saved locally
        self.client.get(reverse("top"))
        self.assertEqual(mock_get.call_count, 1)  # second view served from cache

    @patch("tracker.services.jikan._get", return_value=fake_list(BEBOP))
    def test_search_is_public_and_encodes_query(self, _):
        resp = self.client.get(reverse("search"), {"q": "cowboy & bebop"})
        self.assertContains(resp, "Cowboy Bebop")
        self.assertContains(resp, "Log in to add")

    @patch("tracker.services.jikan._get", return_value=fake_list(FRIEREN))
    def test_seasonal_page(self, _):
        resp = self.client.get(reverse("seasonal_for", args=[2023, "fall"]))
        self.assertContains(resp, "Fall 2023")
        self.assertContains(resp, "Summer 2023")  # previous-season link
        self.assertEqual(self.client.get("/seasonal/2023/monsoon/").status_code, 404)

    @patch("tracker.services.jikan._get", return_value=FAKE_JIKAN_ANIME)
    def test_detail_page_shows_community_score(self, _):
        users = [User.objects.create_user(f"u{i}", password="pw-12345-abc") for i in range(2)]
        anime = api.get_or_fetch_anime(52991)
        WatchlistEntry.objects.create(user=users[0], anime=anime, rating=10)
        WatchlistEntry.objects.create(user=users[1], anime=anime, rating=8)
        resp = self.client.get(reverse("anime_detail", args=[52991]))
        self.assertContains(resp, "9.0")  # average of 10 and 8
        self.assertEqual(resp.context["community"]["members"], 2)

    def test_browse_filters_by_genre(self):
        action = Genre.objects.create(mal_id=1, name="Action")
        a = Anime.objects.create(mal_id=1, title="Cowboy Bebop", score=8.7)
        a.genres.add(action)
        Anime.objects.create(mal_id=2, title="Slow Life Show", score=7.0)
        resp = self.client.get(reverse("browse"), {"genre": "1"})
        self.assertContains(resp, "Cowboy Bebop")
        self.assertNotContains(resp, "Slow Life Show")

    @patch("tracker.services.jikan._get")
    def test_import_catalog_stops_at_last_page(self, mock_get):
        mock_get.side_effect = [fake_list(FRIEREN, has_next=True), fake_list(BEBOP, has_next=False)]
        call_command("import_catalog", stdout=StringIO())
        self.assertEqual(Anime.objects.count(), 2)
        self.assertEqual(mock_get.call_count, 2)

    @patch("tracker.services.jikan._get", return_value=FAKE_JIKAN_ANIME)
    def test_add_from_detail_with_status(self, _):
        User.objects.create_user("eve", password="pw-12345-abc")
        self.client.login(username="eve", password="pw-12345-abc")
        self.client.post(reverse("add_to_watchlist", args=[52991]), {"status": "watching", "next": "/anime/52991/"})
        self.assertEqual(WatchlistEntry.objects.get().status, "watching")


# ---------- AniList source (the default) ----------

ANILIST_FRIEREN = {
    "id": 154587, "idMal": 52991,
    "title": {"romaji": "Sousou no Frieren", "english": "Frieren: Beyond Journey's End"},
    "episodes": 28, "format": "TV", "status": "FINISHED", "season": "FALL", "seasonYear": 2023,
    "startDate": {"year": 2023}, "averageScore": 91, "meanScore": 91, "popularity": 400000,
    "genres": ["Adventure", "Drama", "Fantasy"],
    "coverImage": {"extraLarge": "https://img.example/frieren.jpg", "large": None},
    "description": "An elf mage...<br><br>Adapted from the manga &amp; more.",
    "studios": {"nodes": [{"name": "Madhouse"}]},
    "trailer": {"id": "abc123", "site": "youtube"},
    "rankings": [{"rank": 1, "type": "RATED", "allTime": True}],
}
NO_MAL_ID = {**ANILIST_FRIEREN, "id": 999, "idMal": None}


def anilist_page(*media, has_next=False):
    return {"Page": {"pageInfo": {"hasNextPage": has_next, "lastPage": 3}, "media": list(media)}}


class AniListTests(TestCase):
    def setUp(self):
        cache.clear()

    @patch("tracker.services.anilist._post", return_value={"Media": ANILIST_FRIEREN})
    def test_fetch_maps_fields(self, mock_post):
        a = api.get_or_fetch_anime(52991)
        self.assertEqual(a.score, 9.1)  # 91/100 -> 9.1
        self.assertEqual(a.airing_status, "Finished Airing")
        self.assertEqual(a.season_label, "Fall 2023")
        self.assertEqual(a.studios, "Madhouse")
        self.assertEqual(a.rank, 1)
        self.assertEqual(a.image_url, "https://img.example/frieren.jpg")
        self.assertEqual(a.synopsis, "An elf mage...\n\nAdapted from the manga & more.")
        self.assertTrue(a.trailer_url.endswith("abc123"))
        self.assertEqual(sorted(a.genres.values_list("mal_id", flat=True)), [2, 8, 10])  # MAL genre IDs
        api.get_or_fetch_anime(52991)
        self.assertEqual(mock_post.call_count, 1)  # second call came from our DB

    @patch("tracker.services.anilist._post", return_value=anilist_page(ANILIST_FRIEREN, NO_MAL_ID, has_next=True))
    def test_top_page_skips_shows_without_mal_id(self, _):
        resp = self.client.get(reverse("top"))
        self.assertContains(resp, "Frieren")
        self.assertContains(resp, "Next")
        self.assertContains(resp, "Anime data from AniList")
        self.assertEqual(Anime.objects.count(), 1)

    @patch("tracker.services.anilist._post", return_value=anilist_page(ANILIST_FRIEREN))
    def test_seasonal_sends_season_and_year(self, mock_post):
        self.client.get(reverse("seasonal_for", args=[2023, "fall"]))
        variables = mock_post.call_args.args[1]
        self.assertEqual((variables["season"], variables["seasonYear"]), ("FALL", 2023))

    @patch("tracker.services.anilist._post")
    def test_import_catalog(self, mock_post):
        mock_post.side_effect = [anilist_page(ANILIST_FRIEREN, has_next=True), anilist_page(NO_MAL_ID)]
        out = StringIO()
        call_command("import_catalog", stdout=out)
        self.assertIn("Importing from AniList", out.getvalue())
        self.assertEqual(Anime.objects.count(), 1)

    @patch("tracker.services.anilist._session.post")
    def test_blocked_network_fails_fast(self, mock_http):
        import requests
        mock_http.side_effect = requests.ConnectTimeout("timed out")
        resp = self.client.get(reverse("seasonal"))
        self.assertContains(resp, "Couldn&#x27;t reach the anime database")
        self.assertEqual(mock_http.call_count, 1)  # no retries on a blocked connection



class SeasonPickerAndConfirmTests(TestCase):
    def test_season_picker_redirects(self):
        resp = self.client.get(reverse("seasonal_go"), {"year": "2019", "season": "spring"})
        self.assertRedirects(resp, "/seasonal/2019/spring/", fetch_redirect_response=False)

    def test_season_picker_rejects_bad_input(self):
        for params in ({"year": "abc", "season": "fall"}, {"year": "2019", "season": "monsoon"}, {"year": "1800", "season": "fall"}):
            resp = self.client.get(reverse("seasonal_go"), params)
            self.assertRedirects(resp, reverse("seasonal"), fetch_redirect_response=False)

    @patch("tracker.services.anilist._post", return_value=anilist_page())
    def test_seasonal_page_has_picker_modal(self, _):
        resp = self.client.get(reverse("seasonal_for", args=[2023, "fall"]))
        self.assertContains(resp, 'id="season-picker"')
        self.assertContains(resp, '<option value="2023" selected>')

    def test_logout_and_remove_ask_for_confirmation(self):
        user = User.objects.create_user("zoe", password="pw-12345-abc")
        entry = WatchlistEntry.objects.create(user=user, anime=Anime.objects.create(mal_id=7, title="Show", episodes=12))
        self.client.login(username="zoe", password="pw-12345-abc")
        resp = self.client.get(reverse("entry_edit", args=[entry.pk]))
        self.assertContains(resp, 'data-confirm-title="Log out of TCsMyAnime?"')
        self.assertContains(resp, 'data-confirm-title="Remove from your list?"')
        self.assertContains(resp, 'data-confirm-if-dirty="#entry-edit-form"')
        # the confirmed form POSTs straight to delete
        self.client.post(reverse("entry_delete", args=[entry.pk]))
        self.assertFalse(WatchlistEntry.objects.filter(pk=entry.pk).exists())

    def test_last_episode_button_asks_first(self):
        user = User.objects.create_user("max", password="pw-12345-abc")
        WatchlistEntry.objects.create(user=user, anime=Anime.objects.create(mal_id=8, title="Short", episodes=3),
                                      episodes_watched=2, status="watching")
        self.client.login(username="max", password="pw-12345-abc")
        self.assertContains(self.client.get(reverse("watchlist")), 'data-confirm-title="Finish this show?"')
