from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class AuditEventType(str, Enum):
    AGENT_INVOKED = "agent_invoked"
    AGENT_COMPLETED = "agent_completed"
    AGENT_FAILED = "agent_failed"
    SAFETY_CHECK = "safety_check"
    SAFETY_BLOCKED = "safety_blocked"
    PIPELINE_START = "pipeline_start"
    PIPELINE_END = "pipeline_end"
    STATE_CHANGE = "state_change"
    MESSAGE_SENT = "message_sent"
    ERROR = "error"
    HUMAN_OVERSIGHT = "human_oversight"
    TOOL_INVOKED = "tool_invoked"
    TOOL_COMPLETED = "tool_completed"
    TOOL_FAILED = "tool_failed"


@dataclass
class AuditEvent:
    event_type: AuditEventType
    audit_anchor: str
    session_id: str
    agent_path: str = ""
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: float = field(default_factory=time.time)
    payload: dict[str, Any] = field(default_factory=dict)
    result: str = ""


class AuditLoggerError(Exception):
    """Raised when the append-only audit log cannot be written or verified."""


class AuditLogger:
    """Append-only audit logger with SHA-256 hash chaining.

    Every log entry is a single line of JSON containing a `sha256` digest and the
    digest of the previous entry (`previous_hash`). This creates a tamper-evident
    chain: modifying or removing any entry invalidates the chain on verification.

    The logger is intentionally simple and deterministic: events are written in
    append mode only, never rewritten in place. A small in-memory buffer is kept
    for batching, but `flush()` appends and fsyncs to disk.
    """

    GENESIS_HASH = "0" * 64

    def __init__(self, log_dir: str | Path = "./logs/audit", buffer_size: int = 1):
        self.log_dir = Path(log_dir)
        if self.log_dir.exists() and not self.log_dir.is_dir():
            raise AuditLoggerError(f"Audit log path exists and is not a directory: {self.log_dir}")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._buffer: list[AuditEvent] = []
        self._max_buffer = max(1, buffer_size)
        self._last_hash = self._read_last_hash()

    def _read_last_hash(self) -> str:
        """Return the sha256 of the most recent committed entry, or genesis."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_file = self.log_dir / f"audit_{today}.jsonl"
        if not log_file.exists():
            return self.GENESIS_HASH
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if "sha256" in entry and isinstance(entry["sha256"], str) and len(entry["sha256"]) == 64:
                        return entry["sha256"]
                except json.JSONDecodeError:
                    continue
        except Exception:
            pass
        return self.GENESIS_HASH

    def log(self, event: AuditEvent) -> None:
        """Buffer an audit event; flush when buffer reaches the configured size."""
        self._buffer.append(event)
        if len(self._buffer) >= self._max_buffer:
            self.flush()

    def log_agent_invoked(self, agent_path: str, session_id: str, audit_anchor: str, inputs: dict[str, Any]):
        self.log(AuditEvent(
            event_type=AuditEventType.AGENT_INVOKED,
            audit_anchor=audit_anchor,
            agent_path=agent_path,
            session_id=session_id,
            payload={"inputs": self._sanitize(inputs)},
        ))

    def log_agent_completed(self, agent_path: str, session_id: str, audit_anchor: str,
                            outputs: dict[str, Any] | None, latency_ms: float):
        self.log(AuditEvent(
            event_type=AuditEventType.AGENT_COMPLETED,
            audit_anchor=audit_anchor,
            agent_path=agent_path,
            session_id=session_id,
            payload={"outputs": self._sanitize(outputs), "latency_ms": latency_ms},
        ))

    def log_agent_failed(self, agent_path: str, session_id: str, audit_anchor: str, error: str):
        self.log(AuditEvent(
            event_type=AuditEventType.AGENT_FAILED,
            audit_anchor=audit_anchor,
            agent_path=agent_path,
            session_id=session_id,
            payload={"error": error},
        ))

    def log_tool_invoked(self, tool_name: str, session_id: str, audit_anchor: str, arguments: dict[str, Any]):
        self.log(AuditEvent(
            event_type=AuditEventType.TOOL_INVOKED,
            audit_anchor=audit_anchor,
            agent_path=tool_name,
            session_id=session_id,
            payload={"arguments": self._sanitize(arguments)},
        ))

    def log_tool_completed(self, tool_name: str, session_id: str, audit_anchor: str,
                           output_summary: dict[str, Any], latency_ms: float):
        self.log(AuditEvent(
            event_type=AuditEventType.TOOL_COMPLETED,
            audit_anchor=audit_anchor,
            agent_path=tool_name,
            session_id=session_id,
            payload={"output_summary": self._sanitize(output_summary), "latency_ms": latency_ms},
        ))

    def log_tool_failed(self, tool_name: str, session_id: str, audit_anchor: str, error: str):
        self.log(AuditEvent(
            event_type=AuditEventType.TOOL_FAILED,
            audit_anchor=audit_anchor,
            agent_path=tool_name,
            session_id=session_id,
            payload={"error": error},
        ))

    def log_safety_blocked(self, agent_path: str, session_id: str, audit_anchor: str, reason: str):
        self.log(AuditEvent(
            event_type=AuditEventType.SAFETY_BLOCKED,
            audit_anchor=audit_anchor,
            agent_path=agent_path,
            session_id=session_id,
            payload={"reason": reason},
        ))

    def log_pipeline_start(self, session_id: str, audit_anchor: str, user_input: str):
        self.log(AuditEvent(
            event_type=AuditEventType.PIPELINE_START,
            audit_anchor=audit_anchor,
            session_id=session_id,
            payload={"user_input": user_input[:200]},
        ))

    def log_pipeline_end(self, session_id: str, audit_anchor: str, status: str, metrics: dict[str, Any]):
        self.log(AuditEvent(
            event_type=AuditEventType.PIPELINE_END,
            audit_anchor=audit_anchor,
            session_id=session_id,
            payload={"status": status, "metrics": self._sanitize(metrics)},
        ))

    def flush(self) -> None:
        """Append buffered events to today's log file with hash chaining.

        The file is opened in append mode only. Each line is immutable once
        written. The method fsyncs to reduce the window for data loss.
        """
        if not self._buffer:
            return
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_file = self.log_dir / f"audit_{today}.jsonl"
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                for event in self._buffer:
                    entry = self._serialize_event(event)
                    entry["previous_hash"] = self._last_hash
                    entry["sha256"] = self._hash_entry(entry)
                    self._last_hash = entry["sha256"]
                    line = json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n"
                    f.write(line)
                f.flush()
                # Best-effort fsync; failures are not fatal but degrade durability.
                try:
                    import os
                    os.fsync(f.fileno())
                except Exception:
                    pass
            self._buffer.clear()
        except Exception as exc:
            raise AuditLoggerError(f"Failed to append audit log to {log_file}: {exc}") from exc

    def close(self) -> None:
        """Flush remaining buffer. Called at pipeline end."""
        self.flush()

    def verify_chain(self, log_file: str | Path | None = None) -> dict[str, Any]:
        """Verify the integrity of the append-only audit log.

        Returns a dict with `valid` (bool), `entries` (int), and `first_broken_line`
        (1-based line number of the first hash mismatch, or None).
        """
        if log_file is None:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            log_file = self.log_dir / f"audit_{today}.jsonl"
        else:
            log_file = Path(log_file)

        result = {"valid": True, "entries": 0, "first_broken_line": None}
        if not log_file.exists():
            return result

        previous_hash = self.GENESIS_HASH
        with open(log_file, "r", encoding="utf-8") as f:
            for line_number, raw_line in enumerate(f, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    result["valid"] = False
                    if result["first_broken_line"] is None:
                        result["first_broken_line"] = line_number
                    break

                stored_hash = entry.get("sha256")
                stored_previous = entry.get("previous_hash")
                recompute = {k: v for k, v in entry.items() if k != "sha256"}
                expected_hash = self._hash_entry(recompute)

                if stored_hash != expected_hash or stored_previous != previous_hash:
                    result["valid"] = False
                    if result["first_broken_line"] is None:
                        result["first_broken_line"] = line_number
                    break

                previous_hash = stored_hash
                result["entries"] += 1

        return result

    def _serialize_event(self, event: AuditEvent) -> dict[str, Any]:
        return {
            "event_id": event.event_id,
            "audit_anchor": event.audit_anchor,
            "type": event.event_type.value,
            "timestamp": event.timestamp,
            "agent": event.agent_path,
            "session": event.session_id,
            "payload": event.payload,
            "result": event.result,
        }

    def _hash_entry(self, entry: dict[str, Any]) -> str:
        """Return SHA-256 hex digest of a canonical JSON serialization."""
        canonical = json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _sanitize(self, data: dict[str, Any] | None) -> dict[str, Any]:
        if data is None:
            return {}
        sanitized: dict[str, Any] = {}
        for k, v in data.items():
            if isinstance(v, str) and len(v) > 1000:
                sanitized[k] = v[:1000] + "..."
            else:
                sanitized[k] = v
        return sanitized
