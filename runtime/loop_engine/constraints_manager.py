"""Read and update .agent_loop/CONSTRAINTS.md for self-improving loops."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ConstraintEntry:
    rule: str
    source: str
    added_at: str


class ConstraintsManager:
    """Append-only manager for loop constraints.

    Loads `.agent_loop/CONSTRAINTS.md` at the start of every loop run and
    appends new rules discovered by the verifier. Never deletes rules.
    """

    DEFAULT_PATH: Path = Path(".agent_loop") / "CONSTRAINTS.md"

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else self.DEFAULT_PATH

    def load(self) -> list[ConstraintEntry]:
        if not self.path.exists():
            return []
        entries: list[ConstraintEntry] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("-"):
                line = line[1:].strip()
            parts = line.split("|", 2)
            if len(parts) == 3:
                entries.append(
                    ConstraintEntry(
                        rule=parts[0].strip(),
                        source=parts[1].strip(),
                        added_at=parts[2].strip(),
                    )
                )
            else:
                entries.append(ConstraintEntry(rule=line, source="manual", added_at="unknown"))
        return entries

    def add(self, rule: str, source: str = "verifier") -> ConstraintEntry:
        from datetime import datetime, timezone

        entry = ConstraintEntry(
            rule=rule.strip(),
            source=source,
            added_at=datetime.now(timezone.utc).isoformat(),
        )
        self._ensure_file()
        with self.path.open("a", encoding="utf-8") as f:
            f.write(f"\n- {entry.rule} | {entry.source} | {entry.added_at}")
        return entry

    def append(self, rule: str, source: str = "verifier") -> ConstraintEntry:
        """Alias for `add` matching the test/CLI vocabulary."""
        return self.add(rule, source)

    def read(self) -> str:
        """Return raw contents of the constraints file."""
        if not self.path.exists():
            return ""
        return self.path.read_text(encoding="utf-8")

    def add_many(
        self,
        rules: list[str],
        source: str = "verifier",
    ) -> list[ConstraintEntry]:
        return [self.add(rule, source) for rule in rules]

    def to_context(self) -> dict[str, Any]:
        entries = self.load()
        return {
            "path": str(self.path),
            "count": len(entries),
            "rules": [e.rule for e in entries],
            "entries": [
                {"rule": e.rule, "source": e.source, "added_at": e.added_at}
                for e in entries
            ],
        }

    def _ensure_file(self) -> None:
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                "# Loop Constraints\n\n"
                "Auto-populated by loop verifier. Manual edits allowed but logged.\n",
                encoding="utf-8",
            )
