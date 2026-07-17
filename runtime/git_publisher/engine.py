from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .config import GitPublisherConfig

logger = logging.getLogger(__name__)


@dataclass
class GitPublishResult:
    provider: str = ""
    project_id: str = ""
    url: str | None = None
    clone_url: str | None = None
    success: bool = False
    error: str | None = None
    files_committed: int = 0
    logs: list[str] = field(default_factory=list)


class GitPublisherEngine:
    """Publish a generated codebase to GitHub or GitLab.

    Optional dependencies:
      - PyGithub for GitHub
      - python-gitlab for GitLab
    """

    def __init__(self, config: GitPublisherConfig | None = None):
        self.config = config or GitPublisherConfig()

    def publish(
        self,
        project_id: str,
        codebase: dict[str, str],
        commit_message: str | None = None,
    ) -> GitPublishResult:
        result = GitPublishResult(
            provider=self.config.provider,
            project_id=project_id,
        )
        if self.config.provider == "github":
            return self._publish_github(
                project_id=project_id,
                codebase=codebase,
                commit_message=commit_message or self.config.base_commit_message,
                result=result,
            )
        if self.config.provider == "gitlab":
            return self._publish_gitlab(
                project_id=project_id,
                codebase=codebase,
                commit_message=commit_message or self.config.base_commit_message,
                result=result,
            )
        result.error = f"Unknown git provider: {self.config.provider}"
        return result

    def _publish_github(
        self,
        project_id: str,
        codebase: dict[str, str],
        commit_message: str,
        result: GitPublishResult,
    ) -> GitPublishResult:
        token = self.config.github_token
        if not token:
            result.error = "GITHUB_TOKEN is not set"
            return result

        try:
            from github import Github
        except ImportError as exc:
            result.error = f"PyGithub is not installed: {exc}"
            return result

        try:
            g = Github(token)
            user = g.get_user()
            repo = user.create_repo(project_id, private=self.config.private)
            for path, content in codebase.items():
                repo.create_file(
                    path=path,
                    message=f"Add {path}",
                    content=content.encode("utf-8"),
                )
            result.url = repo.html_url
            result.clone_url = repo.clone_url
            result.files_committed = len(codebase)
            result.success = True
            result.logs.append(f"GitHub repo created: {repo.html_url}")
            logger.info("GitHub repo created: %s", repo.html_url)
        except Exception as exc:
            result.error = str(exc)
            result.logs.append(f"GitHub publish failed: {exc}")
            logger.exception("GitHub publish failed")

        return result

    def _publish_gitlab(
        self,
        project_id: str,
        codebase: dict[str, str],
        commit_message: str,
        result: GitPublishResult,
    ) -> GitPublishResult:
        token = self.config.gitlab_token
        if not token:
            result.error = "GITLAB_TOKEN is not set"
            return result

        try:
            import gitlab
        except ImportError as exc:
            result.error = f"python-gitlab is not installed: {exc}"
            return result

        try:
            gl = gitlab.Gitlab("https://gitlab.com", private_token=token)
            visibility = "private" if self.config.private else "public"
            project = gl.projects.create({"name": project_id, "visibility": visibility})
            for path, content in codebase.items():
                project.files.create(
                    {
                        "file_path": path,
                        "branch": "main",
                        "content": content,
                        "commit_message": f"Add {path}",
                    }
                )
            result.url = project.web_url
            result.clone_url = project.http_url_to_repo
            result.files_committed = len(codebase)
            result.success = True
            result.logs.append(f"GitLab project created: {project.web_url}")
            logger.info("GitLab project created: %s", project.web_url)
        except Exception as exc:
            result.error = str(exc)
            result.logs.append(f"GitLab publish failed: {exc}")
            logger.exception("GitLab publish failed")

        return result
