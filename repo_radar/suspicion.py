"""Astroturf detection.

GitHub search ranks by raw stars, and stars are cheap to buy. A repo can be
pushed into a 'trending' list with 80k stars, one commit and no forks. The
signals below are deliberately blunt: they only fire on shapes that are hard to
reach honestly, and every one of them explains itself so the user can disagree.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Suspicion:
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)

    @property
    def flagged(self) -> bool:
        """Needs corroboration: one strong signal alone (0.4) is only a warning."""
        return self.score >= 0.5


def assess(stars: int, forks: int, age: float, has_description: bool,
           fork_ratio: float, stars_per_day: float) -> Suspicion:
    """Score 0-1. >= 0.5 means 'look at this before you trust the number'."""
    result = Suspicion()

    def add(points: float, reason: str) -> None:
        result.score += points
        result.reasons.append(reason)

    if not has_description:
        add(0.2, "no description")

    # Real projects get forked. A large star count with almost no forks is the
    # single most common signature of bought stars.
    if stars >= 1500 and fork_ratio < 0.005:
        add(0.5, "almost no forks for its size")
    elif stars >= 1500 and fork_ratio < 0.01:
        add(0.4, "few forks for its size")
    elif stars >= 5000 and fork_ratio > 0.5:
        add(0.2, "forks outnumber stars - likely templates")

    # 800 new stars a day sustained is beyond what organic interest produces for
    # anything but a handful of launches, and those arrive with forks and issues.
    # On its own this is a nudge, not a verdict - real launches do grow this fast.
    if stars_per_day > 800:
        add(0.4, "implausible star rate")
    elif stars_per_day > 400:
        add(0.15, "very fast growth")

    # 20k stars inside six weeks is a marketing event, not a repo maturing.
    if stars >= 20000 and age < 45:
        add(0.4, "huge and brand new")

    result.score = min(round(result.score, 2), 1.0)
    return result
