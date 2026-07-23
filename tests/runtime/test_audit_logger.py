import json
import re
from pathlib import Path

import pytest

from runtime.safety.audit_logger import AuditEvent, AuditEventType, AuditLogger, AuditLoggerError


class TestAuditLoggerAppendOnly:
    def test_single_event_is_appended_with_hash_chain(self, tmp_path):
        logger = AuditLogger(log_dir=tmp_path, buffer_size=1)
        logger.log(AuditEvent(
            event_type=AuditEventType.PIPELINE_START,
            audit_anchor="anchor-1",
            session_id="session-1",
            agent_path="pipeline",
            payload={"user_input": "hello"},
        ))

        from datetime import datetime
        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        log_file = tmp_path / f"audit_{today_str}.jsonl"

        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["type"] == "pipeline_start"
        assert entry["audit_anchor"] == "anchor-1"
        assert entry["previous_hash"] == AuditLogger.GENESIS_HASH
        assert re.fullmatch(r"[a-f0-9]{64}", entry["sha256"])

    def test_multiple_events_chain_previous_hash(self, tmp_path):
        logger = AuditLogger(log_dir=tmp_path, buffer_size=2)
        logger.log(AuditEvent(
            event_type=AuditEventType.PIPELINE_START,
            audit_anchor="anchor-1",
            session_id="session-1",
            agent_path="pipeline",
        ))
        logger.log(AuditEvent(
            event_type=AuditEventType.AGENT_INVOKED,
            audit_anchor="anchor-1",
            session_id="session-1",
            agent_path="agent.md",
        ))
        logger.flush()

        from datetime import datetime
        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        log_file = tmp_path / f"audit_{today_str}.jsonl"

        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        first = json.loads(lines[0])
        second = json.loads(lines[1])
        assert second["previous_hash"] == first["sha256"]

    def test_verify_chain_passes_for_valid_log(self, tmp_path):
        logger = AuditLogger(log_dir=tmp_path, buffer_size=1)
        for i in range(3):
            logger.log(AuditEvent(
                event_type=AuditEventType.AGENT_INVOKED,
                audit_anchor="anchor",
                session_id="session",
                agent_path=f"agent-{i}.md",
            ))
        result = logger.verify_chain()
        assert result["valid"] is True
        assert result["entries"] == 3
        assert result["first_broken_line"] is None

    def test_verify_chain_fails_when_line_modified(self, tmp_path):
        logger = AuditLogger(log_dir=tmp_path, buffer_size=1)
        logger.log(AuditEvent(
            event_type=AuditEventType.AGENT_INVOKED,
            audit_anchor="anchor",
            session_id="session",
            agent_path="agent.md",
        ))
        logger.log(AuditEvent(
            event_type=AuditEventType.AGENT_COMPLETED,
            audit_anchor="anchor",
            session_id="session",
            agent_path="agent.md",
        ))

        from datetime import datetime
        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        log_file = tmp_path / f"audit_{today_str}.jsonl"

        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        second = json.loads(lines[1])
        second["payload"]["tampered"] = True
        lines[1] = json.dumps(second, sort_keys=True)
        log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        result = logger.verify_chain()
        assert result["valid"] is False
        assert result["first_broken_line"] == 2

    def test_new_logger_reads_last_hash_from_existing_file(self, tmp_path):
        logger = AuditLogger(log_dir=tmp_path, buffer_size=1)
        logger.log(AuditEvent(
            event_type=AuditEventType.PIPELINE_START,
            audit_anchor="anchor",
            session_id="session",
            agent_path="pipeline",
        ))
        logger.flush()

        from datetime import datetime
        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        log_file = tmp_path / f"audit_{today_str}.jsonl"
        first_hash = json.loads(log_file.read_text(encoding="utf-8").split("\n")[0])["sha256"]

        logger2 = AuditLogger(log_dir=tmp_path, buffer_size=1)
        logger2.log(AuditEvent(
            event_type=AuditEventType.PIPELINE_END,
            audit_anchor="anchor",
            session_id="session",
            agent_path="pipeline",
        ))

        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[1])["previous_hash"] == first_hash

    def test_helper_methods_use_audit_anchor(self, tmp_path):
        logger = AuditLogger(log_dir=tmp_path, buffer_size=1)
        logger.log_pipeline_start("session-1", "anchor-1", "hello world")
        logger.log_agent_invoked("agent.md", "session-1", "anchor-1", {"x": 1})
        logger.log_agent_completed("agent.md", "session-1", "anchor-1", {"y": 2}, 12.5)
        logger.log_safety_blocked("agent.md", "session-1", "anchor-1", "reason")

        from datetime import datetime
        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        log_file = tmp_path / f"audit_{today_str}.jsonl"
        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 4
        anchors = [json.loads(line)["audit_anchor"] for line in lines]
        assert all(a == "anchor-1" for a in anchors)

    def test_sanitize_truncates_long_strings(self, tmp_path):
        logger = AuditLogger(log_dir=tmp_path, buffer_size=1)
        long_value = "x" * 2000
        logger.log_agent_invoked("agent.md", "session-1", "anchor-1", {"text": long_value})

        from datetime import datetime
        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        log_file = tmp_path / f"audit_{today_str}.jsonl"
        entry = json.loads(log_file.read_text(encoding="utf-8").strip().split("\n")[0])
        assert entry["payload"]["inputs"]["text"].endswith("...")
        assert len(entry["payload"]["inputs"]["text"]) == 1003

    def test_sanitize_redacts_secret_keys(self, tmp_path):
        logger = AuditLogger(log_dir=tmp_path, buffer_size=1)
        logger.log_agent_invoked(
            "agent.md",
            "session-1",
            "anchor-1",
            {
                "api_key": "sk-12345",
                "unsplash_api_key": "uk-67890",
                "providerApiKey": "pk-abcde",
                "token": "t-kjhgf",
                "secret": "shhh",
                "password": "hunter2",
                "private_key": "-----BEGIN RSA PRIVATE KEY-----",
                "access_key": "AKIAIOSFODNN7EXAMPLE",
                "image_provider_api_key": "ipk-secret",
                "public": "visible",
            },
        )

        from datetime import datetime
        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        log_file = tmp_path / f"audit_{today_str}.jsonl"
        entry = json.loads(log_file.read_text(encoding="utf-8").strip().split("\n")[0])
        inputs = entry["payload"]["inputs"]
        for secret_key in (
            "api_key",
            "unsplash_api_key",
            "providerApiKey",
            "token",
            "secret",
            "password",
            "private_key",
            "access_key",
            "image_provider_api_key",
        ):
            assert inputs[secret_key] == "***REDACTED***", secret_key
        assert inputs["public"] == "visible"

    def test_sanitize_redacts_secrets_in_nested_arguments(self, tmp_path):
        logger = AuditLogger(log_dir=tmp_path, buffer_size=1)
        logger.log_tool_invoked(
            "figma_server",
            "session-1",
            "anchor-1",
            {
                "file_key": "abc123",
                "image_provider_api_key": "super-secret-key",
                "nested": {"credentials": {"password": "deep-secret"}},
            },
        )

        from datetime import datetime
        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        log_file = tmp_path / f"audit_{today_str}.jsonl"
        entry = json.loads(log_file.read_text(encoding="utf-8").strip().split("\n")[0])
        arguments = entry["payload"]["arguments"]
        assert arguments["file_key"] == "abc123"
        assert arguments["image_provider_api_key"] == "***REDACTED***"
        assert arguments["nested"]["credentials"] == "***REDACTED***"


class TestAuditLoggerErrors:
    def test_constructor_raises_when_log_dir_is_file(self, tmp_path):
        bad_path = tmp_path / "not_a_dir"
        bad_path.write_text("x", encoding="utf-8")
        with pytest.raises(AuditLoggerError):
            AuditLogger(log_dir=bad_path, buffer_size=1)
