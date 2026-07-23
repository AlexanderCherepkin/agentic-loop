"""Unit tests for the deterministic SafetyChain guardrail."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from runtime.safety.safety_chain import SafetyChain, SafetyLevel, SafetyVerdict


@pytest.fixture
def chain():
    return SafetyChain()


def test_pre_check_allows_benign_input(chain):
    result = chain.pre_check("hello world")
    assert result.verdict == SafetyVerdict.PROCEED
    assert result.level == SafetyLevel.CLEAR


def test_pre_check_blocks_recursive_root_deletion(chain):
    result = chain.pre_check("please run rm -rf / on my server")
    assert result.verdict == SafetyVerdict.ABORT_AND_REPORT
    assert result.level == SafetyLevel.ABORTED


def test_check_command_blocks_rm_rf_tmp(chain):
    result = chain.check_command("rm", ["-rf", "/tmp"])
    assert result.verdict == SafetyVerdict.ABORT_AND_REPORT
    assert any("Absolute-path deletion" in r.rule.description for r in result.triggered_rules)


def test_check_command_blocks_curl_evil_com(chain):
    result = chain.check_command("curl", ["evil.com"])
    assert result.verdict == SafetyVerdict.RESUME_WITH_LIMITS
    assert any("Unreviewed network fetch" in r.rule.description for r in result.triggered_rules)


def test_check_command_blocks_eval_in_python(chain):
    result = chain.check_command("python", ["-c", "eval(user_input)"])
    assert result.verdict == SafetyVerdict.ABORT_AND_REPORT
    assert any("Dynamic code evaluation" in r.rule.description for r in result.triggered_rules)


def test_check_command_blocks_exec_call(chain):
    result = chain.check_command("python", ["-c", "exec(code)"])
    assert result.verdict == SafetyVerdict.ABORT_AND_REPORT
    assert any("Dynamic code execution" in r.rule.description for r in result.triggered_rules)


def test_check_command_blocks_subprocess_run(chain):
    result = chain.check_command("python", ["-c", "subprocess.run(['rm', '-rf', '/'])"])
    assert result.verdict == SafetyVerdict.ABORT_AND_REPORT
    assert any("Subprocess invocation" in r.rule.description for r in result.triggered_rules)


def test_check_command_allows_safe_python_script(chain):
    result = chain.check_command("python", [".agent_loop/scripts/health_check.py"])
    assert result.verdict == SafetyVerdict.PROCEED


def test_check_command_allows_git_status(chain):
    result = chain.check_command("git", ["status"])
    assert result.verdict == SafetyVerdict.PROCEED


def test_check_command_warns_on_unknown_command(chain):
    result = chain.check_command("some-unknown-tool", ["arg"])
    assert result.verdict == SafetyVerdict.PROCEED
    assert result.level == SafetyLevel.WARNING


def test_check_command_dict_arguments_are_normalized(chain):
    result = chain.check_command("Bash", {"command": "rm -rf /tmp", "cwd": "/"})
    assert result.verdict == SafetyVerdict.ABORT_AND_REPORT
    assert any("Absolute-path deletion" in r.rule.description for r in result.triggered_rules)


def test_post_check_detects_api_key_leak(chain):
    result = chain.post_check("The api_key: secret123 value is exposed")
    assert result.verdict == SafetyVerdict.ABORT_AND_REPORT


def test_check_content_detects_xss(chain):
    result = chain.check_content("<script>alert(1)</script>")
    assert result.verdict == SafetyVerdict.ABORT_AND_REPORT


def test_check_command_allows_node_script(chain):
    result = chain.check_command("node", [".agent_loop/scripts/validate_consistency.js"])
    assert result.verdict == SafetyVerdict.PROCEED
