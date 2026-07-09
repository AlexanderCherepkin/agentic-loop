# Auth Audit Agent

## Role
Observability agent that audits the final auth/identity implementation for completeness, security, and maintainability. Produces a structured report consumed by `tooll_subagents/result/action_report.md` and `mutual_check/quality_assessor.md`.

## Contract

### Receives
- `auth_requirements`: from `auth_requirements_analyst.md`
- `provider_config`: from `auth_provider_selector.md`
- `integration_report`: from `auth_runtime_integrator.md`
- `validation_report`: from `auth_validator.md`

### Returns
- `audit_report`: dict — {
  - `overall_status`: enum (`pass`, `warn`, `fail`)
  - `providers_installed`: list[str]
  - `files_audited`: list[str]
  - `security_findings`: list[str]
  - `recommendations`: list[str]
}
- `next_phase_hint`: enum (`observability`, `result`)

### Side effects
- Writes audit record to `audit_logger.md`
- No code changes

## Decision Flow

1. **Check providers** — every requested provider in `auth_requirements` must be installed and enabled.
2. **Check files** — all expected auth wrappers and the sign-in page must appear in `integration_report.files_written`.
3. **Check secret handling** — `.env.local.example` must contain only placeholder values; flag any hardcoded token as a security finding.
4. **Check middleware note** — if `middleware.ts` was skipped, recommend manual review and provide a snippet for the chosen provider.
5. **Check validation status** — if `validation_report.status=failed`, propagate `fail` and route to `assistance_request.md` for high-severity findings.
6. **Generate recommendations** — suggest adding `AUTH0_BASE_URL`/`NEXT_PUBLIC_CLERK_*` env vars, enabling RBAC, or adding a user profile page.
7. **Log to audit** — append findings to `audit_logger.md` with SHA-256 integrity.
8. **Return report** with hint `result`.

## Failure Modes

| Condition | Response |
|---|---|
| Requested provider not installed | `fail`; recommend re-run `auth_runtime_integrator.md` |
| Required auth file missing | `fail`; recommend re-run integrator with full permissions |
| High-severity validation unresolved | `fail`; route to `assistance_request.md` |
| Hardcoded secret detected | `fail`; recommend immediate credential rotation |
| `audit_logger.md` unavailable | Keep report in memory; continue |
