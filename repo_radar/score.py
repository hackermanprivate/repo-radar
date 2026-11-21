"""Metrics that separate 'popular' from 'rising'.

All functions are pure and take an explicit ``now`` so the ranking can be tested
without freezing the clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


def parse_time(value: str) -> datetime:
    """Parse GitHub's ISO-8601 timestamps (``2026-11-21T04:08:31Z``)."""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def age_days(created_at: datetime, now: datetime) -> float:
    """Age in days, floored at one day so a repo created today cannot divide by zero."""
    return max((now - created_at).total_seconds() / 86400.0, 1.0)


def velocity(stars: int, age: float) -> float:
    """Average stars gained per day over the repo's whole life."""
    return stars / age


def recency(pushed_at: datetime, now: datetime, half_life_days: float = 30.0) -> float:
    """Decay factor in (0, 1]: 1.0 for a repo pushed minutes ago, 0.5 after 30 days."""
    idle = max((now - pushed_at).total_seconds() / 86400.0, 0.0)
    return 0.5 ** (idle / half_life_days)


def momentum(stars: int, created_at: datetime, pushed_at: datetime, now: datetime,
             half_life_days: float = 30.0) -> float:
    """Velocity weighted by how recently the project was actually worked on.

    A four-year-old repo with 40k stars earns a high raw velocity but a low
    momentum once it goes quiet; a two-month-old repo with 3k stars and a push
    yesterday earns a high one. That is the whole point of the ranking.
    """
    return velocity(stars, age_days(created_at, now)) * recency(pushed_at, now, half_life_days)


def fork_ratio(forks: int, stars: int) -> float:
    """Forks per star. Very high ratios usually mean templates or honeypots."""
    if stars <= 0:
        return 0.0
    return forks / stars


@dataclass(frozen=True)
class Metrics:
    stars: int
    age_days: float
    stars_per_day: float
    momentum: float
    fork_ratio: float
    idle_days: float


def compute(stars: int, forks: int, created_at: datetime, pushed_at: datetime,
            now: datetime, half_life_days: float = 30.0) -> Metrics:
    age = age_days(created_at, now)
    return Metrics(
        stars=stars,
        age_days=age,
        stars_per_day=velocity(stars, age),
        momentum=momentum(stars, created_at, pushed_at, now, half_life_days),
        fork_ratio=fork_ratio(forks, stars),
        idle_days=max((now - pushed_at).total_seconds() / 86400.0, 0.0),
    )
