"""Watchlist statistics built with pandas."""

import pandas as pd

from tracker.models import WatchlistEntry

STATUS_LABELS = dict(WatchlistEntry.Status.choices)


def build_stats(user):
    rows = list(
        WatchlistEntry.objects.filter(user=user).values(
            "id", "status", "rating", "episodes_watched", "anime__genres__name"
        )
    )
    if not rows:
        return None

    # One row per (entry, genre) because of the ManyToMany join
    df = pd.DataFrame(rows).rename(columns={"anime__genres__name": "genre"})
    entries = df.drop_duplicates("id")  # one row per watchlist entry

    total = len(entries)
    status_counts = entries["status"].value_counts()

    # Completion rate: completed / shows you've actually started or decided on.
    # "Plan to Watch" is excluded because you haven't begun those yet.
    started = entries[entries["status"] != WatchlistEntry.Status.PLAN_TO_WATCH]
    completed = int(status_counts.get(WatchlistEntry.Status.COMPLETED, 0))
    completion_rate = round(completed / len(started) * 100, 1) if len(started) else 0.0

    rated = entries["rating"].dropna()
    avg_rating = round(float(rated.mean()), 2) if not rated.empty else None

    genre_df = df.dropna(subset=["genre"])
    genre_counts = genre_df.groupby("genre")["id"].nunique().sort_values(ascending=False)
    genre_ratings = (
        genre_df.drop_duplicates(["id", "genre"])
        .dropna(subset=["rating"])
        .groupby("genre")["rating"]
        .mean()
        .round(1)
    )

    top_count = int(genre_counts.iloc[0]) if not genre_counts.empty else 1
    genres = [
        {
            "name": name,
            "count": int(count),
            "percent": round(count / top_count * 100),
            "avg_rating": genre_ratings.get(name),
        }
        for name, count in genre_counts.head(10).items()
    ]

    statuses = [
        {
            "key": key,
            "label": label,
            "count": int(status_counts.get(key, 0)),
            "percent": round(status_counts.get(key, 0) / total * 100),
        }
        for key, label in STATUS_LABELS.items()
    ]

    return {
        "total": total,
        "completed": completed,
        "started": len(started),
        "completion_rate": completion_rate,
        "avg_rating": avg_rating,
        "episodes_watched": int(entries["episodes_watched"].sum()),
        "statuses": statuses,
        "genres": genres,
    }
