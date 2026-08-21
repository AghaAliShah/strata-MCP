# Thin async wrapper around the subset of the GitHub REST API this project needs.
# Every function here does one HTTP call and returns plain dict/list/str —
# no MCP concepts live in this file, so it stays testable/reusable on its own.

import base64
import datetime

import httpx

from mcp_server.config import GITHUB_TOKEN

GITHUB_API = "https://api.github.com"


def _check(resp: httpx.Response) -> httpx.Response:
    """Turn GitHub's generic 403 into an actionable message before raising."""
    if resp.status_code == 403 and resp.headers.get("X-RateLimit-Remaining") == "0":
        limit = resp.headers.get("X-RateLimit-Limit", "?")
        reset = resp.headers.get("X-RateLimit-Reset", "")
        when = ""
        if reset.isdigit():
            when = datetime.datetime.fromtimestamp(int(reset)).strftime(" (resets %H:%M:%S)")
        hint = (
            " Set GITHUB_TOKEN in .env to raise this to 5000/hour."
            if not GITHUB_TOKEN
            else ""
        )
        raise RuntimeError(f"GitHub rate limit hit: {limit}/hour exhausted{when}.{hint}")
    resp.raise_for_status()
    return resp


def _headers() -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


async def search_repositories(query: str, limit: int = 10) -> list[dict]:
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        resp = await client.get(
            f"{GITHUB_API}/search/repositories",
            headers=_headers(),
            params={"q": query, "per_page": limit},
        )
        _check(resp)
        return resp.json()["items"]


async def get_repo(owner: str, repo: str) -> dict:
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        resp = await client.get(f"{GITHUB_API}/repos/{owner}/{repo}", headers=_headers())
        _check(resp)
        return resp.json()


async def list_contents(owner: str, repo: str, path: str = "") -> list[dict]:
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}", headers=_headers()
        )
        _check(resp)
        data = resp.json()
        # GitHub returns a single object (not a list) when `path` points at a file.
        return data if isinstance(data, list) else [data]


async def get_file_content(owner: str, repo: str, path: str) -> str:
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}", headers=_headers()
        )
        _check(resp)
        data = resp.json()
        if data.get("encoding") != "base64":
            raise ValueError(f"Unexpected encoding for {path}: {data.get('encoding')!r}")
        return base64.b64decode(data["content"]).decode("utf-8", errors="replace")


async def get_tree(owner: str, repo: str, branch: str) -> list[dict]:
    """Whole file tree in ONE call (recursive), instead of walking folder by folder."""
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/{branch}",
            headers=_headers(),
            params={"recursive": "1"},
        )
        _check(resp)
        data = resp.json()
        return [
            {"path": t["path"], "type": t["type"], "size": t.get("size", 0)}
            for t in data.get("tree", [])
        ]


async def get_languages(owner: str, repo: str) -> dict:
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/languages", headers=_headers()
        )
        _check(resp)
        return resp.json()
