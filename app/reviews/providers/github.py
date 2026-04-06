"""GitHub REST API implementation of SCMProvider (Plan 63-A)."""

from __future__ import annotations

import asyncio
import logging

import httpx

from app.reviews.models import PullRequestInfo, ReviewComment

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_BACKOFF = (1, 2, 4)


class GitHubProvider:
    """GitHub REST API v3 provider."""

    def __init__(
        self, owner: str, repo: str, token: str, http_client: httpx.AsyncClient | None = None
    ):
        self.owner = owner
        self.repo = repo
        self.token = token
        self._client = http_client or httpx.AsyncClient(timeout=30)
        self._base = f"https://api.github.com/repos/{owner}/{repo}"

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:  # type: ignore[no-untyped-def]
        """Make a request with retry on 403/429."""
        headers = {**self._headers, **kwargs.pop("headers", {})}
        for attempt in range(1, _MAX_RETRIES + 1):
            resp = await self._client.request(method, url, headers=headers, **kwargs)
            if resp.status_code in (403, 429) and attempt < _MAX_RETRIES:
                wait = _RETRY_BACKOFF[attempt - 1]
                logger.warning(
                    "GitHub %s %s → %s, retry in %ss", method, url, resp.status_code, wait
                )
                await asyncio.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        return resp  # unreachable but keeps mypy happy

    async def get_pull_request(self, pr_id: int) -> PullRequestInfo:
        url = f"{self._base}/pulls/{pr_id}"
        resp = await self._request("GET", url)
        d = resp.json()
        return PullRequestInfo(
            number=d["number"],
            title=d["title"],
            description=d.get("body") or "",
            author=d["user"]["login"],
            base_branch=d["base"]["ref"],
            head_branch=d["head"]["ref"],
            url=d["html_url"],
            repo_owner=self.owner,
            repo_name=self.repo,
            files_changed=d.get("changed_files", 0),
            additions=d.get("additions", 0),
            deletions=d.get("deletions", 0),
            commit_sha=d["head"]["sha"],
        )

    async def get_diff(self, pr_id: int) -> str:
        url = f"{self._base}/pulls/{pr_id}"
        resp = await self._request("GET", url, headers={"Accept": "application/vnd.github.diff"})
        return resp.text

    async def get_changed_files(self, pr_id: int) -> list[dict]:
        url = f"{self._base}/pulls/{pr_id}/files"
        results: list[dict] = []
        page = 1
        while True:
            resp = await self._request("GET", url, params={"per_page": 100, "page": page})
            data = resp.json()
            if not data:
                break
            results.extend(data)
            page += 1
            if len(data) < 100:
                break
        return results

    async def post_review(
        self,
        pr_id: int,
        body: str,
        event: str,
        comments: list[ReviewComment],
    ) -> str:
        url = f"{self._base}/pulls/{pr_id}/reviews"
        gh_comments = []
        for c in comments:
            entry: dict = {
                "path": c.path,
                "line": c.line,
                "side": c.side,
                "body": c.body,
            }
            if c.start_line is not None:
                entry["start_line"] = c.start_line
                entry["start_side"] = c.start_side or c.side
            gh_comments.append(entry)

        payload = {
            "body": body,
            "event": event,
            "comments": gh_comments,
        }
        resp = await self._request("POST", url, json=payload)
        return resp.json().get("html_url", "")

    async def get_existing_review_comments(self, pr_id: int) -> list[dict]:
        url = f"{self._base}/pulls/{pr_id}/comments"
        resp = await self._request("GET", url, params={"per_page": 100})
        return resp.json()

    # ------------------------------------------------------------------
    # Repo metadata (Plan 63-B)
    # ------------------------------------------------------------------

    async def get_repo_info(self) -> dict:
        """Get repo metadata: language, default_branch, description."""
        resp = await self._request("GET", self._base)
        d = resp.json()
        return {
            "language": d.get("language"),
            "default_branch": d.get("default_branch", "main"),
            "description": d.get("description", ""),
        }

    async def get_file_tree(self, max_files: int = 500) -> list[str]:
        """Get repo file tree via git trees API (recursive, single call)."""
        # First get default branch SHA
        info = await self.get_repo_info()
        branch = info.get("default_branch", "main")
        url = f"{self._base}/git/trees/{branch}?recursive=1"
        try:
            resp = await self._request("GET", url)
        except httpx.HTTPStatusError:
            return []
        data = resp.json()
        tree = data.get("tree", [])
        paths: list[str] = []
        for item in tree:
            if len(paths) >= max_files:
                break
            path = item.get("path", "")
            # Only top 3 levels
            if path.count("/") <= 2:
                paths.append(path)
        return paths

    async def get_file_content(self, path: str) -> str:
        """Get raw file content via contents API."""
        url = f"{self._base}/contents/{path}"
        resp = await self._request(
            "GET", url, headers={"Accept": "application/vnd.github.raw+json"}
        )
        return resp.text
