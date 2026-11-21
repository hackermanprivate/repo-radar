"""Build RISING.md: a dated snapshot of repos that cleared the momentum bar today.

Run by .github/workflows/rising.yml once a day. Every run commits real, dated data,
which is what makes the file worth visiting rather than a static README.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from repo_radar.cli import build_query, rank  # noqa: E402
from repo_radar.github import search, token_from_env  # noqa: E402

QUERIES = [
    ("AI agents", "topic:ai-agents", 240),
    ("Self-hosted", "topic:self-hosted", 365),
    ("Developer tools", "topic:developer-tools", 180),
    ("Rust", "language:rust", 365),
]

LIMIT = 6


def main() -> int:
    token = token_from_env()
    now = datetime.now(timezone.utc)
    out = [
        "# Rising now",
        "",
        f"Snapshot taken **{now.strftime('%Y-%m-%d %H:%M UTC')}** by "
        "[`scripts/build_rising.py`](scripts/build_rising.py) in a scheduled Action.",
        "",
        "Ranked by momentum = stars/day since creation, decayed by 30-day idle half-life. "
        "`?` marks a repo whose star count looks bought (see the suspicion rules in the README).",
        "",
    ]
    total = 0
    for label, query, max_age in QUERIES:
        full = build_query(query, min_stars=200, active_days=None, max_age_days=max_age)
        try:
            items = search(full, token, per_page=100, max_pages=2)
        except Exception as exc:  # a single failed query must not kill the snapshot
            out += [f"## {label}", "", f"_query failed: {exc}_", ""]
            continue
        rows = rank(items, "momentum", now=now)
        rows = [r for r in rows if not r["suspicion"].flagged][:LIMIT]
        out += [f"## {label}", "", "| repo | stars | age | ★/day | idle |", "|---|---:|---:|---:|---:|"]
        for row in rows:
            repo, m = row["repo"], row["metrics"]
            age = f"{m.age_days / 30.4:.0f}mo" if m.age_days >= 60 else f"{m.age_days:.0f}d"
            idle = f"{m.idle_days:.0f}d"
            out.append(
                f'| [{repo["full_name"]}]({repo["html_url"]}) | {m.stars:,} | {age} | '
                f'{m.stars_per_day:.0f} | {idle} |'
            )
            total += 1
        out.append("")
    out += ["---", "", f"{total} repositories in this snapshot. Regenerated daily; history is in the commit log.", ""]

    with open("RISING.md", "w", encoding="utf-8") as handle:
        handle.write("\n".join(out))
    print(f"wrote RISING.md with {total} repos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
