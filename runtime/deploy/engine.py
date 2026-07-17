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

        if self.config.is_image_provider:
            return self._run_image_provider()

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

    def _run_image_provider(self) -> DeployResult:
        from .providers import DeployProviderFactory

        provider = DeployProviderFactory.get(self.config.provider)
        self.result.command = f"{self.config.provider} image deploy: {self.config.image_tag}"

        if self.config.dry_run:
            self.result.success = True
            self.result.notes.append(
                f"Dry-run mode: would deploy image {self.config.image_tag} to {self.config.provider}"
            )
            self.result.notes.append(
                f"Provider configured: {provider.is_configured()}"
            )
            return self.result

        if not provider.is_configured():
            self.result.errors.append({
                "file": "",
                "reason": f"{self.config.provider} provider is not configured (API key missing)",
            })
            return self.result

        project: dict[str, Any] = {
            "project_id": self.config.project_id,
            "language": self.config.language,
        }
        provider_config: dict[str, Any] = {
            "service_name": self.config.service_name,
            "app_name": self.config.app_name,
            "region": self.config.region,
            "owner_id": self.config.owner_id,
            "plan": self.config.plan,
        }
        provider_config = {k: v for k, v in provider_config.items() if v is not None}

        provider_result = provider.deploy(
            image_tag=self.config.image_tag or "",
            project=project,
            config=provider_config or None,
        )

        self.result.deploy_url = provider_result.service_url
        self.result.stdout = "\n".join(provider_result.logs)
        self.result.notes.extend(provider_result.logs)
        if provider_result.error:
            self.result.errors.append({"file": "", "reason": provider_result.error})
        else:
            self.result.success = bool(provider_result.service_id or provider_result.service_url)
            self.result.notes.append(f"Status: {provider_result.status}")

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
