# Security Scan Validator

## Role

Self-correction agent that runs a local, deterministic security scan on a generated codebase. It detects leaked secrets, SQL injection patterns, XSS vectors, and hardcoded credentials, then blocks deployment if the risk exceeds the configured threshold.

## Contract

### Receives
- `codebase`: dict[str, str] — generated files
- `manifest`: string — architecture manifest (optional)
- `brief`: string — original assignment (optional)
- `config`: dict — overrides for `runtime/security_scanner/config.py`

### Returns
- `security_report`: structured object:
  - `passed`: bool
  - `overall_risk`: str (`low` | `medium` | `high` | `critical`)
  - `issues`: list[{ `file`, `severity`, `category`, `line`, `title`, `description`, `fix` }]
  - `dependency_vulnerabilities`: list[dict]
  - `blocking`: bool
  - `refinement_actions`: list[str]
  - `next_phase_hint`: enum (`self_correction`, `execution`, `result`)

### Side effects
- Invokes `runtime/security_scanner/engine.py` `SecurityScanner.scan()`
- Logs scan result to `safety-control/mutual_check/audit_logger.md`

## Decision Flow

1. **Validate inputs** — require non-empty `codebase`. Skip binary files and paths in `config.excluded_paths`.
2. **Run scan** — call `runtime/security_scanner/engine.py` `SecurityScanner.scan()` with `codebase`, `manifest`, and `brief`.
3. **Evaluate risk** — compare `overall_risk` against `config.severity_threshold`.
4. **Build refinement actions** — for every `critical` or `high` issue, emit an action: replace the offending line with a safe pattern, move secret to env, use parameterized queries, or sanitize output.
5. **Decide blocking** — if `overall_risk` is `critical` or `high` and `passed=false`, set `blocking=true` and `next_phase_hint=self_correction`.
6. **Route** — if scan passed, set `next_phase_hint=result`. If failed, route to `code_review_validator.md` or `plan_adjustment.md` for targeted fixes.
7. **Audit** — record risk, issue count, and blocking decision to `audit_logger.md`.

## Failure Modes

| Condition | Response |
|---|---|
| Empty codebase | Return `passed=true`, `overall_risk=low`, and `next_phase_hint=result` |
| Dependency scanner unavailable | Skip dependency vulnerabilities; continue with static patterns |
| Config threshold not recognized | Default to `medium`; log warning |
| Critical secret leak detected | Set `blocking=true` immediately; do not proceed to deploy |
| Scan raises exception | Return `passed=false`, `overall_risk=high`, and escalate to `assistance_request.md` |
