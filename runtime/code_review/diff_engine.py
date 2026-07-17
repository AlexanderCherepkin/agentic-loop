"""Diff / patch-based code review applier."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class Patch(BaseModel):
    """A single replacement patch: replace ``old`` with ``new`` in ``file``."""

    file: str = Field(..., description="Relative path to file")
    old: str = Field(..., description="Exact fragment to replace")
    new: str = Field(..., description="Replacement fragment")


class PatchApplication(BaseModel):
    """Result of applying one patch."""

    patch: Patch
    applied: bool
    message: str


class PatchApplier:
    """Applies a list of Patch objects to a codebase dictionary."""

    def apply(
        self,
        patches: list[Patch],
        codebase: dict[str, str],
    ) -> tuple[dict[str, str], list[PatchApplication]]:
        """Return a new codebase and the status of each patch."""
        result = dict(codebase)
        statuses: list[PatchApplication] = []

        for patch in patches:
            if patch.file not in result:
                statuses.append(
                    PatchApplication(
                        patch=patch,
                        applied=False,
                        message=f"File {patch.file} not found",
                    )
                )
                continue

            content = result[patch.file]
            if patch.old not in content:
                statuses.append(
                    PatchApplication(
                        patch=patch,
                        applied=False,
                        message=f"Fragment not found in {patch.file}",
                    )
                )
                continue

            count = content.count(patch.old)
            if count > 1:
                statuses.append(
                    PatchApplication(
                        patch=patch,
                        applied=False,
                        message=f"Ambiguous fragment ({count} occurrences) in {patch.file}",
                    )
                )
                continue

            result[patch.file] = content.replace(patch.old, patch.new, 1)
            statuses.append(
                PatchApplication(
                    patch=patch,
                    applied=True,
                    message=f"Applied to {patch.file}",
                )
            )

        return result, statuses

    def apply_dict_patches(
        self,
        patches: list[dict[str, Any]],
        codebase: dict[str, str],
    ) -> tuple[dict[str, str], list[dict[str, Any]]]:
        """Convenience wrapper for raw dict patches."""
        model_patches = [Patch(**p) for p in patches]
        result, statuses = self.apply(model_patches, codebase)
        return result, [s.model_dump() for s in statuses]
