from django.urls import path

from tracker import views

urlpatterns = [
    # your list
    path("", views.watchlist, name="watchlist"),
    path("signup/", views.signup, name="signup"),
    path("add/<int:mal_id>/", views.add_to_watchlist, name="add_to_watchlist"),
    path("entry/<int:pk>/", views.entry_edit, name="entry_edit"),
    path("entry/<int:pk>/plus-one/", views.entry_increment, name="entry_increment"),
    path("entry/<int:pk>/delete/", views.entry_delete, name="entry_delete"),
    path("stats/", views.stats, name="stats"),
    # discovery (public)
    path("anime/<int:mal_id>/", views.anime_detail, name="anime_detail"),
    path("search/", views.search, name="search"),
    path("browse/", views.browse, name="browse"),
    path("top/", views.top_anime, name="top"),
    path("seasonal/", views.seasonal, name="seasonal"),
    path("seasonal/<int:year>/<str:season>/", views.seasonal, name="seasonal_for"),
]
