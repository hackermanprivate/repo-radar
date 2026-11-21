"""Tests for the ranking maths. No network access: every case uses a fixed clock."""

import unittest
from datetime import datetime, timedelta, timezone

from repo_radar.score import (
    age_days,
    compute,
    fork_ratio,
    momentum,
    parse_time,
    recency,
    velocity,
)

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)


def days_ago(n: float) -> datetime:
    return NOW - timedelta(days=n)


class ParseTimeTests(unittest.TestCase):
    def test_github_zulu_timestamp(self):
        self.assertEqual(parse_time("2026-11-20T04:08:31Z"), datetime(2026, 11, 20, 4, 8, 31, tzinfo=timezone.utc))

    def test_naive_timestamp_is_treated_as_utc(self):
        self.assertEqual(parse_time("2026-11-20T04:08:31").tzinfo, timezone.utc)

    def test_offset_timestamp_is_normalised(self):
        self.assertEqual(parse_time("2026-11-20T09:38:31+05:30"), datetime(2026, 11, 20, 4, 8, 31, tzinfo=timezone.utc))


class AgeTests(unittest.TestCase):
    def test_age_is_measured_in_days(self):
        self.assertAlmostEqual(age_days(days_ago(10), NOW), 10.0)

    def test_brand_new_repo_floors_at_one_day(self):
        """A repo created minutes ago must not produce a divide-by-zero velocity."""
        self.assertEqual(age_days(days_ago(0), NOW), 1.0)

    def test_future_timestamp_also_floors(self):
        self.assertEqual(age_days(NOW + timedelta(days=2), NOW), 1.0)


class VelocityTests(unittest.TestCase):
    def test_stars_per_day(self):
        self.assertAlmostEqual(velocity(3000, 30.0), 100.0)

    def test_zero_stars(self):
        self.assertEqual(velocity(0, 50.0), 0.0)


class RecencyTests(unittest.TestCase):
    def test_fresh_push_scores_one(self):
        self.assertAlmostEqual(recency(NOW, NOW), 1.0)

    def test_half_life(self):
        self.assertAlmostEqual(recency(days_ago(30), NOW, half_life_days=30), 0.5, places=6)

    def test_two_half_lives(self):
        self.assertAlmostEqual(recency(days_ago(60), NOW, half_life_days=30), 0.25, places=6)

    def test_never_negative_or_zero(self):
        self.assertGreater(recency(days_ago(3650), NOW), 0.0)


class MomentumTests(unittest.TestCase):
    def test_rising_beats_established(self):
        """2k stars in 60 days, pushed yesterday, outranks 40k stars in 4 years, idle 90 days."""
        rising = momentum(2000, days_ago(60), days_ago(1), NOW)
        established = momentum(40000, days_ago(1460), days_ago(90), NOW)
        self.assertGreater(rising, established)

    def test_abandoned_project_is_penalised(self):
        active = momentum(1000, days_ago(90), days_ago(1), NOW)
        stale = momentum(1000, days_ago(90), days_ago(180), NOW)
        self.assertGreater(active, stale)

    def test_equal_inputs_equal_output(self):
        a = momentum(500, days_ago(50), days_ago(5), NOW)
        b = momentum(500, days_ago(50), days_ago(5), NOW)
        self.assertEqual(a, b)


class ForkRatioTests(unittest.TestCase):
    def test_ratio(self):
        self.assertAlmostEqual(fork_ratio(25, 1000), 0.025)

    def test_zero_stars_is_safe(self):
        self.assertEqual(fork_ratio(3, 0), 0.0)


class ComputeTests(unittest.TestCase):
    def test_bundles_all_metrics(self):
        m = compute(3000, 60, days_ago(30), days_ago(2), NOW)
        self.assertEqual(m.stars, 3000)
        self.assertAlmostEqual(m.age_days, 30.0)
        self.assertAlmostEqual(m.stars_per_day, 100.0)
        self.assertAlmostEqual(m.idle_days, 2.0)
        self.assertAlmostEqual(m.fork_ratio, 0.02)
        self.assertGreater(m.momentum, 0)


if __name__ == "__main__":
    unittest.main()
