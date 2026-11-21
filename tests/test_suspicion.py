"""Tests for the star-farm heuristic."""

import unittest

from repo_radar.suspicion import assess


def base(**over):
    kwargs = dict(stars=3000, forks=90, age=120.0, has_description=True,
                  fork_ratio=0.03, stars_per_day=25.0)
    kwargs.update(over)
    return assess(**kwargs)


class CleanRepoTests(unittest.TestCase):
    def test_normal_growing_repo_is_not_flagged(self):
        result = base()
        self.assertFalse(result.flagged)
        self.assertEqual(result.reasons, [])


class FlagTests(unittest.TestCase):
    def test_no_description_adds_a_point(self):
        self.assertAlmostEqual(base(has_description=False).score, 0.2)

    def test_big_stars_with_no_forks_is_flagged(self):
        result = base(stars=50000, fork_ratio=0.002)
        self.assertTrue(result.flagged)
        self.assertIn("almost no forks for its size", result.reasons)

    def test_fork_heavy_repo_is_soft_flagged(self):
        result = base(stars=8000, fork_ratio=0.8)
        self.assertFalse(result.flagged)   # 0.2 alone is not enough
        self.assertIn("forks outnumber stars - likely templates", result.reasons)

    def test_impossible_star_rate_alone_is_a_nudge_not_a_verdict(self):
        """Real launches do hit 1000+/day, so speed alone must not flag a repo."""
        result = base(stars_per_day=1500)
        self.assertEqual(result.score, 0.4)
        self.assertFalse(result.flagged)
        self.assertIn("implausible star rate", result.reasons)

    def test_speed_plus_no_forks_is_flagged(self):
        result = base(stars=2000, fork_ratio=0.004, stars_per_day=1500)
        self.assertTrue(result.flagged)

    def test_fast_growth_is_only_a_nudge(self):
        result = base(stars_per_day=500)
        self.assertFalse(result.flagged)
        self.assertAlmostEqual(result.score, 0.15)

    def test_huge_and_new_is_flagged(self):
        result = base(stars=25000, age=20.0, stars_per_day=600)
        self.assertTrue(result.flagged)
        self.assertIn("huge and brand new", result.reasons)

    def test_score_is_capped_at_one(self):
        result = base(stars=40000, fork_ratio=0.0, stars_per_day=2000, age=10.0,
                      has_description=False)
        self.assertEqual(result.score, 1.0)

    def test_flag_threshold_is_half(self):
        self.assertTrue(assess(stars=9000, forks=10, age=60.0, has_description=False,
                               fork_ratio=0.001, stars_per_day=150.0).flagged)


if __name__ == "__main__":
    unittest.main()
