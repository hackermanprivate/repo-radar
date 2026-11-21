"""Command line interface for repo-radar."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timedelta, timezone

from . import __version__
from .github import GitHubError, rate_limit, search, token_from_env
from .score import compute, parse_time
from .suspicion import assess

SORTS = ("momentum", "stars", "velocity", "age")


def build_query(text: str, min_stars: int, active_days: int | None,
                max_age_days: int | None) -> str:
    """Compose a GitHub search query from the CLI flags."""
    parts = [text.strip()]
    if min_stars > 0:
        parts.append(f"stars:>={min_stars}")
    now = datetime.now(timezone.utc)
    if active_days:
        cutoff = (now - timedelta(days=active_days)).strftime("%Y-%m-%d")
        parts.append(f"pushed:>={cutoff}")
    if max_age_days:
        cutoff = (now - timedelta(days=max_age_days)).strftime("%Y-%m-%d")
        parts.append(f"created:>={cutoff}")
    return " ".join(p for p in parts if p)


def rank(items: list[dict], sort: str, now: datetime | None = None) -> list[dict]:
    """Attach metrics to each repo and sort. Pure, so tests can pass a fixed ``now``."""
    now = now or datetime.now(timezone.utc)
    rows = []
    for item in items:
        if item.get("fork") or item.get("archived"):
            continue
        try:
            created = parse_time(item["created_at"])
            pushed = parse_time(item["pushed_at"])
        except (KeyError, ValueError):
            continue
        metrics = compute(
            stars=int(item.get("stargazers_count") or 0),
            forks=int(item.get("forks_count") or 0),
            created_at=created,
            pushed_at=pushed,
            now=now,
        )
        flag = assess(
            stars=metrics.stars,
            forks=int(item.get("forks_count") or 0),
            age=metrics.age_days,
            has_description=bool((item.get("description") or "").strip()),
            fork_ratio=metrics.fork_ratio,
            stars_per_day=metrics.stars_per_day,
        )
        rows.append({"repo": item, "metrics": metrics, "suspicion": flag})
    keys = {
        "momentum": lambda r: r["metrics"].momentum,
        "stars": lambda r: r["metrics"].stars,
        "velocity": lambda r: r["metrics"].stars_per_day,
        "age": lambda r: -r["metrics"].age_days,
    }
    rows.sort(key=keys[sort], reverse=True)
    return rows


def _human_age(days: float) -> str:
    if days < 60:
        return f"{days:.0f}d"
    if days < 730:
        return f"{days / 30.4:.0f}mo"
    return f"{days / 365.25:.1f}y"


def _truncate(text: str, width: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= width else text[: width - 1] + "…"


def format_table(rows: list[dict], limit: int) -> str:
    """Fixed-width table. No colour, no dependencies - pipes cleanly into less/grep."""
    if not rows:
        return "No repositories matched. Try relaxing --min-stars, --active-days or the query."
    head = f'{"#":>3}  {"repository":38}  {"stars":>7}  {"age":>5}  {"★/day":>7}  {"idle":>5}'
    lines = [head, "-" * len(head)]
    for index, row in enumerate(rows[:limit], start=1):
        repo, m = row["repo"], row["metrics"]
        mark = " ?" if row["suspicion"].flagged else ""
        lines.append(
            f'{index:>3}  {_truncate(repo["full_name"], 38):38}  {m.stars:>7,}  '
            f'{_human_age(m.age_days):>5}  {m.stars_per_day:>7.1f}  {_human_age(m.idle_days):>5}{mark}'
        )
    return "\n".join(lines)


def format_detail(rows: list[dict], limit: int) -> str:
    """One block per repo: enough context to decide whether to open it."""
    blocks = []
    for row in rows[:limit]:
        repo, m = row["repo"], row["metrics"]
        desc = (repo.get("description") or "").strip()
        block = (
            f'{repo["full_name"]}  ★{m.stars:,}  {m.stars_per_day:.1f}/day  '
            f'{_human_age(m.age_days)} old  last push {_human_age(m.idle_days)} ago'
            + (f'\n  {desc}' if desc else "")
            + f'\n  {repo.get("html_url", "")}'
        )
        if row["suspicion"].score:
            block += f'\n  suspicion {row["suspicion"].score:.2f}: ' + "; ".join(row["suspicion"].reasons)
        blocks.append(block)
    return "\n\n".join(blocks)


def to_json(rows: list[dict], limit: int) -> str:
    payload = []
    for row in rows[:limit]:
        repo, m = row["repo"], row["metrics"]
        payload.append({
            "repo": repo["full_name"],
            "url": repo.get("html_url"),
            "description": repo.get("description"),
            "language": repo.get("language"),
            "stars": m.stars,
            "forks": repo.get("forks_count", 0),
            "age_days": round(m.age_days, 1),
            "stars_per_day": round(m.stars_per_day, 2),
            "momentum": round(m.momentum, 2),
            "fork_ratio": round(m.fork_ratio, 2),
            "idle_days": round(m.idle_days, 1),
            "suspicion": row["suspicion"].score,
            "suspicion_reasons": row["suspicion"].reasons,
            "topics": repo.get("topics", []),
        })
    return json.dumps(payload, indent=2)


def to_csv(rows: list[dict], limit: int) -> str:
    import io

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["repo", "stars", "age_days", "stars_per_day", "momentum", "idle_days", "suspicion", "url"])
    for row in rows[:limit]:
        repo, m = row["repo"], row["metrics"]
        writer.writerow([repo["full_name"], m.stars, round(m.age_days, 1),
                         round(m.stars_per_day, 2), round(m.momentum, 2),
                         round(m.idle_days, 1), row["suspicion"].score,
                         repo.get("html_url", "")])
    return buffer.getvalue().rstrip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="repo-radar",
        description="Find GitHub repositories that are rising fast, not merely large.",
        epilog='examples:\n'
               '  repo-radar "topic:ai-agents" --max-age-days 120\n'
               '  repo-radar "vector database" --min-stars 200 --active-days 14\n'
               '  repo-radar "language:rust cli" --sort velocity --json',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("query", nargs="+", help="search text, or GitHub search qualifiers")
    parser.add_argument("--min-stars", type=int, default=50, help="floor (default 50)")
    parser.add_argument("--active-days", type=int, default=None,
                        help="only repos pushed within N days")
    parser.add_argument("--max-age-days", type=int, default=None,
                        help="only repos created within N days (finds new projects)")
    parser.add_argument("--limit", type=int, default=15, help="rows to print (default 15)")
    parser.add_argument("--sort", choices=SORTS, default="momentum",
                        help="ranking key (default momentum = velocity weighted by recency)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--csv", action="store_true", help="CSV output")
    parser.add_argument("--detail", action="store_true", help="description block per repo")
    parser.add_argument("--hide-suspicious", action="store_true",
                        help="drop repos that look star-farmed (they are only marked by default)")
    parser.add_argument("--version", action="version", version=f"repo-radar {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    query = build_query(" ".join(args.query), args.min_stars, args.active_days, args.max_age_days)
    token = token_from_env()

    try:
        remaining = rate_limit(token).get("remaining")
        if remaining is not None and remaining <= 1:
            print(
                "Out of GitHub search quota for now (10/min unauthenticated, 30/min with a "
                "token). Set GITHUB_TOKEN and retry.",
                file=sys.stderr,
            )
            return 2
        items = search(query, token)
    except GitHubError as exc:
        print(f"repo-radar: {exc}", file=sys.stderr)
        return 2

    rows = rank(items, args.sort)
    flagged = sum(1 for r in rows if r["suspicion"].flagged)
    if args.hide_suspicious:
        rows = [r for r in rows if not r["suspicion"].flagged]

    if args.json:
        print(to_json(rows, args.limit))
    elif args.csv:
        print(to_csv(rows, args.limit))
    elif args.detail:
        print(format_detail(rows, args.limit))
    else:
        print(f'query: {query}\n')
        print(format_table(rows, args.limit))
        print("\nmomentum = stars/day since creation, decayed by idle time (30-day half-life)")
        if flagged:
            print(f'{flagged} marked ? look star-farmed - --detail shows why, --hide-suspicious drops them')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
