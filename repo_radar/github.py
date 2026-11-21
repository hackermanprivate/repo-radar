"""Minimal GitHub search client: stdlib only, no dependencies, no SDK."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"
UA = "repo-radar (+https://github.com/hackermanprivate/repo-radar)"


class GitHubError(RuntimeError):
    """Raised with the API's own message so the CLI can print something useful."""


def token_from_env() -> str | None:
    """``GITHUB_TOKEN`` is optional: unauthenticated search allows 10 requests/min."""
    for name in ("GITHUB_TOKEN", "GH_TOKEN"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None


def _request(path: str, token: str | None, timeout: float = 30.0) -> dict:
    req = urllib.request.Request(
        API + path,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": UA,
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "ignore")
        try:
            message = json.loads(body).get("message", body)
        except json.JSONDecodeError:
            message = body
        if exc.code == 403 and "rate limit" in message.lower():
            reset = exc.headers.get("X-RateLimit-Reset")
            hint = ""
            if reset and reset.isdigit():
                wait = max(int(reset) - int(time.time()), 0)
                hint = f" Try again in {wait}s, or set GITHUB_TOKEN for 30 requests/min."
            raise GitHubError(f"GitHub rate limit hit.{hint}") from exc
        if exc.code == 422:
            raise GitHubError(
                f"GitHub rejected the query ({message}). Search syntax: "
                "https://docs.github.com/search-github/searching-on-github/searching-for-repositories"
            ) from exc
        raise GitHubError(f"GitHub returned HTTP {exc.code}: {message}") from exc
    except urllib.error.URLError as exc:
        raise GitHubError(f"Network error talking to GitHub: {exc.reason}") from exc


def search(query: str, token: str | None = None, per_page: int = 100,
           max_pages: int = 2) -> list[dict]:
    """Return raw repository objects for a search query, newest-relevance order."""
    items: list[dict] = []
    for page in range(1, max_pages + 1):
        encoded = urllib.parse.quote(query, safe=":+<>=.-_*/")
        payload = _request(
            f"/search/repositories?q={encoded}&sort=stars&order=desc"
            f"&per_page={per_page}&page={page}",
            token,
        )
        batch = payload.get("items") or []
        items.extend(batch)
        if len(batch) < per_page or len(items) >= payload.get("total_count", 0):
            break
    return items


def rate_limit(token: str | None = None) -> dict:
    """Remaining search quota, useful as a pre-flight check."""
    return _request("/rate_limit", token).get("resources", {}).get("search", {})
