"""Tests for query building, ranking and output formatting. No network access."""

import json
import unittest
from datetime import datetime, timedelta, timezone

from repo_radar.cli import build_query, format_table, rank, to_csv, to_json

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)


def repo(name, stars, age_days, idle_days, forks=None, **extra):
    created = NOW - timedelta(days=age_days)
    pushed = NOW - timedelta(days=idle_days)
    item = {
        "full_name": name,
        "stargazers_count": stars,
        "forks_count": stars // 20 if forks is None else forks,
        "created_at": created.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pushed_at": pushed.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "html_url": f"https://github.com/{name}",
        "description": f"{name} does a thing",
        "language": "Python",
        "topics": ["cli"],
    }
    item.update(extra)
    return item


class BuildQueryTests(unittest.TestCase):
    def test_min_stars_only(self):
        query = build_query("topic:cli", 100, None, None)
        self.assertEqual(query, "topic:cli stars:>=100")

    def test_active_days_adds_pushed_cutoff(self):
        query = build_query("kafka", 50, 14, None)
        self.assertIn("stars:>=50", query)
        self.assertIn("pushed:>=", query)

    def test_max_age_days_adds_created_cutoff(self):
        query = build_query("agents", 0, None, 90)
        self.assertIn("created:>=", query)
        self.assertNotIn("stars:>=", query)

    def test_multiple_words_are_joined(self):
        self.assertEqual(build_query("vector  database", 0, None, None), "vector  database")


class RankTests(unittest.TestCase):
    def test_rising_ranks_above_large_and_idle(self):
        items = [
            repo("big/old", 40000, 1460, 90),
            repo("new/hot", 2000, 60, 1),
        ]
        rows = rank(items, "momentum", now=NOW)
        self.assertEqual(rows[0]["repo"]["full_name"], "new/hot")

    def test_stars_sort_is_absolute(self):
        items = [repo("big/old", 40000, 1460, 90), repo("new/hot", 2000, 60, 1)]
        rows = rank(items, "stars", now=NOW)
        self.assertEqual(rows[0]["repo"]["full_name"], "big/old")

    def test_forks_are_excluded(self):
        items = [repo("someone/fork", 5000, 30, 1, fork=True), repo("real/repo", 100, 30, 1)]
        rows = rank(items, "momentum", now=NOW)
        self.assertEqual([r["repo"]["full_name"] for r in rows], ["real/repo"])

    def test_archived_repos_are_excluded(self):
        items = [repo("dead/repo", 9000, 400, 200, archived=True), repo("live/repo", 100, 30, 1)]
        rows = rank(items, "momentum", now=NOW)
        self.assertEqual([r["repo"]["full_name"] for r in rows], ["live/repo"])

    def test_broken_timestamps_are_skipped(self):
        items = [repo("bad/time", 100, 30, 1, created_at="not-a-date"), repo("ok/repo", 100, 30, 1)]
        rows = rank(items, "momentum", now=NOW)
        self.assertEqual([r["repo"]["full_name"] for r in rows], ["ok/repo"])

    def test_age_sort_is_youngest_first(self):
        items = [repo("older/one", 500, 800, 5), repo("younger/one", 100, 20, 1)]
        rows = rank(items, "age", now=NOW)
        self.assertEqual(rows[0]["repo"]["full_name"], "younger/one")


class OutputTests(unittest.TestCase):
    def setUp(self):
        self.rows = rank(
            [repo("new/hot", 2000, 60, 1), repo("big/old", 40000, 1460, 90)],
            "momentum",
            now=NOW,
        )

    def test_table_has_header_and_rows(self):
        text = format_table(self.rows, 5)
        self.assertIn("repository", text)
        self.assertIn("new/hot", text)
        self.assertEqual(len(text.splitlines()), 4)  # header, rule, two rows

    def test_table_respects_limit(self):
        text = format_table(self.rows, 1)
        self.assertEqual(len(text.splitlines()), 3)

    def test_empty_result_is_explained(self):
        self.assertIn("No repositories matched", format_table([], 5))

    def test_json_is_valid_and_complete(self):
        payload = json.loads(to_json(self.rows, 2))
        self.assertEqual(len(payload), 2)
        self.assertEqual(payload[0]["repo"], "new/hot")
        for key in ("stars", "stars_per_day", "momentum", "fork_ratio", "idle_days"):
            self.assertIn(key, payload[0])

    def test_csv_round_trips(self):
        lines = to_csv(self.rows, 2).splitlines()
        self.assertEqual(lines[0].split(",")[0], "repo")
        self.assertEqual(len(lines), 3)


if __name__ == "__main__":
    unittest.main()
