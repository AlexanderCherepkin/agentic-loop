"""Open Design bridge for local-first, privacy-first premium design.

Syncs DTCG tokens and DESIGN.md with a local Open Design (nexu-io) desktop
instance via its local HTTP API. Reads back policy updates so the local
instance can act as an additional anti-slop validator.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class OpenDesignBridgeResult:
    ok: bool = False
    skill_id: str | None = None
    policy_synced: bool = False
    tokens_synced: bool = False
    notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class OpenDesignBridge:
    """Two-way sync between Agentic Loop DTCG artifacts and Open Design Desktop."""

    DEFAULT_PORT = 8123
    DEFAULT_PATH = "/api/v1/skills/register"

    def __init__(
        self,
        workspace_root: Path | str = ".",
        host: str = "127.0.0.1",
        port: int = DEFAULT_PORT,
        skill_path: Path | str | None = None,
    ):
        self.workspace = Path(workspace_root).resolve()
        self.base_url = f"http://{host}:{port}"
        self.skill_path = Path(skill_path) if skill_path else self.workspace / ".claude" / "skills" / "premium-design.skill.md"

    def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return {"status": resp.status, "data": json.loads(resp.read().decode("utf-8"))}
        except urllib.error.HTTPError as exc:
            return {"status": exc.code, "error": exc.read().decode("utf-8", errors="ignore")}
        except urllib.error.URLError as exc:
            return {"status": 0, "error": str(exc.reason)}
        except Exception as exc:
            return {"status": 0, "error": str(exc)}

    def sync_skill(self) -> OpenDesignBridgeResult:
        """Register the Anti-Slop skill in Open Design Desktop."""
        result = OpenDesignBridgeResult()
        if not self.skill_path.exists():
            result.errors.append(f"Skill file not found: {self.skill_path}")
            return result

        skill_text = self.skill_path.read_text(encoding="utf-8")
        # Extract the 44-rule block if present; otherwise ship the whole skill.
        rules = skill_text
        marker_start = "## 02. Спецификация 44 запретов"
        marker_end = "## 03."
        start = skill_text.find(marker_start)
        if start != -1:
            end = skill_text.find(marker_end, start)
            if end != -1:
                rules = skill_text[start:end]

        payload = {
            "name": "premium-design-anti-slop",
            "description": "Premium UI/UX QA filter with 44 deterministic anti-slop rules",
            "version": "1.0.0",
            "global_trigger": True,
            "system_prompt_injection": rules,
            "config_matrix": {
                "variance": 0.5,
                "density": 0.3,
                "motion": 0.5,
            },
        }

        response = self._post(self.DEFAULT_PATH, payload)
        if response.get("status") in (200, 201):
            result.ok = True
            result.skill_id = response.get("data", {}).get("id")
            result.policy_synced = True
            result.notes.append(f"Skill registered at {self.base_url}{self.DEFAULT_PATH}")
        else:
            result.errors.append(response.get("error", "unknown Open Design API error"))
            result.notes.append("Make sure Open Design Desktop is running.")
        return result

    def sync_tokens(
        self,
        tokens_path: Path | str | None = None,
        design_md_path: Path | str | None = None,
    ) -> OpenDesignBridgeResult:
        """Push DTCG tokens and DESIGN.md to Open Design as project context."""
        result = OpenDesignBridgeResult()
        tokens_path = Path(tokens_path) if tokens_path else self.workspace / "design_tokens.json"
        design_md_path = Path(design_md_path) if design_md_path else self.workspace / "DESIGN.md"

        if not tokens_path.exists():
            result.errors.append(f"Tokens not found: {tokens_path}")
            return result

        tokens = json.loads(tokens_path.read_text(encoding="utf-8"))
        design_md = (
            design_md_path.read_text(encoding="utf-8")
            if design_md_path.exists()
            else ""
        )

        payload: dict[str, Any] = {
            "project_context": {
                "design_tokens": tokens,
                "design_md": design_md,
                "workspace": str(self.workspace),
            }
        }

        response = self._post("/api/v1/projects/context", payload)
        if response.get("status") in (200, 201, 204):
            result.ok = True
            result.tokens_synced = True
            result.notes.append("Project context synced to Open Design")
        else:
            result.errors.append(response.get("error", "unknown Open Design API error"))
        return result

    def pull_policy(self) -> dict[str, Any]:
        """Read back the current anti-slop policy from Open Design Desktop."""
        url = f"{self.base_url}/api/v1/skills/premium-design-anti-slop/policy"
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            return {"error": str(exc)}

    def full_sync(self) -> OpenDesignBridgeResult:
        """Register skill + push tokens + pull policy."""
        skill_result = self.sync_skill()
        if not skill_result.ok:
            return skill_result

        token_result = self.sync_tokens()
        skill_result.ok = token_result.ok
        skill_result.tokens_synced = token_result.tokens_synced
        skill_result.errors.extend(token_result.errors)
        skill_result.notes.extend(token_result.notes)

        policy = self.pull_policy()
        if "error" not in policy:
            skill_result.notes.append("Policy pulled from Open Design")
        return skill_result
