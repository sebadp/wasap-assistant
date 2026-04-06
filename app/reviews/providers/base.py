"""SCM Provider protocol — abstract interface for GitHub/GitLab/etc. (Plan 63-A)."""

from __future__ import annotations

from typing import Protocol

from app.reviews.models import PullRequestInfo, ReviewComment


class SCMProvider(Protocol):
    """Abstract interface for source code management providers."""

    async def get_pull_request(self, pr_id: int) -> PullRequestInfo: ...

    async def get_diff(self, pr_id: int) -> str: ...

    async def get_changed_files(self, pr_id: int) -> list[dict]: ...

    async def post_review(
        self,
        pr_id: int,
        body: str,
        event: str,
        comments: list[ReviewComment],
    ) -> str: ...

    async def get_existing_review_comments(self, pr_id: int) -> list[dict]: ...
