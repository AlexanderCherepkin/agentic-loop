from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import DeployConfig


@dataclass
class DeployResult:
    provider: str = ""
    command: str = ""
    dry_run: bool = True
    success: bool = False
    deploy_url: str | None = None
    stdout: str = ""
    stderr: str = ""
    returncode: int | None = None
    errors: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class DeployEngine:
    def __init__(self, target_dir: Path | str, config: DeployConfig | None = None):
        self.target_dir = Path(target_dir).resolve()
        self.config = config or DeployConfig()
        self.config.target_dir = self.target_dir
        self.result = DeployResult(provider=self.config.provider, dry_run=self.config.dry_run)

    def run(self) -> DeployResult:
        validation_errors = self.config.validate()
        if validation_errors:
            for err in validation_errors:
                self.result.errors.append({"file": "", "reason": err})
            return self.result

        command = self._build_command()
        self.result.command = command

        if self.config.dry_run:
            self.result.success = True
            self.result.notes.append(f"Dry-run mode: would run '{command}'")
            return self.result

        env = os.environ.copy()
        env.update(self.config.env)
        shell = os.name == "nt"
        try:
            proc = subprocess.run(
                command,
                cwd=str(self.target_dir),
                env=env,
                shell=shell,
                capture_output=True,
                text=True,
                timeout=self.config.timeout,
            )
            self.result.returncode = proc.returncode
            self.result.stdout = proc.stdout
            self.result.stderr = proc.stderr
            self.result.success = proc.returncode == 0
            self.result.deploy_url = self._extract_url(proc.stdout + "\n" + proc.stderr)
            if not self.result.success:
                self.result.errors.append({
                    "file": "",
                    "reason": f"Deploy command exited with code {proc.returncode}",
                })
        except subprocess.TimeoutExpired as exc:
            self.result.errors.append({"file": "", "reason": f"Deploy timed out after {self.config.timeout}s"})
            self.result.stdout = exc.stdout or ""
            self.result.stderr = exc.stderr or ""
        except Exception as exc:
            self.result.errors.append({"file": "", "reason": str(exc)})

        return self.result

    def _build_command(self) -> str:
        if self.config.provider == "vercel":
            return "npx vercel --prod --yes"
        if self.config.provider == "netlify":
            return f"{self.config.build_command} && npx netlify deploy --prod --dir={self.config.dist_dir}"
        return f"{self.config.build_command} && echo 'Build complete. Upload {self.config.dist_dir}/ to your host.'"

    @staticmethod
    def _extract_url(text: str) -> str | None:
        for line in text.splitlines():
            # Vercel: https://project.vercel.app
            match = re.search(r"https?://[\w\-.]+\.vercel\.app", line)
            if match:
                return match.group(0)
            # Netlify: https://site--xxx.netlify.app or https://xxx.netlify.app
            match = re.search(r"https?://[\w\-.]+\.netlify\.app", line)
            if match:
                return match.group(0)
            # Generic URLs printed after Deploy: or URL:
            match = re.search(r"(?:Deploy|URL|Live).*?(https?://\S+)", line, re.IGNORECASE)
            if match:
                return match.group(1).rstrip(".")
        return None
