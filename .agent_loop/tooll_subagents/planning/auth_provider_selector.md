# Auth Provider Selector

## Role
Planning agent that normalizes and selects the identity provider configuration for a Next.js project based on auth requirements, available keys, and project rules. Emits an `AuthProvider` descriptor consumed by `auth_runtime_integrator.md`.

## Contract

### Receives
- `auth_requirements`: from `auth_requirements_analyst.md`
- `project_rules`: from `tooll_subagents/user/context.md`
- `jurisdiction_map`: optional from `cookie_consent_jurisdiction_mapper.md`

### Returns
- `provider_config`: dict — {
  - `provider_id`: enum (`clerk`, `auth0`)
  - `enabled`: bool
  - `publishable_key`: str | None
  - `domain`: str | None
  - `client_id`: str | None
  - `client_secret`: str | None
  - `redirect_uri`: str | None
  - `allowed_public_paths`: list[str]
  - `protected_paths`: list[str]
}
- `next_phase_hint`: enum (`planning`, `execution`, `result`)

### Side effects
- None; planning only

## Decision Flow

1. **Short-circuit if no identity needed** — if `auth_requirements.needs_identity=false`, return empty config with `next_phase_hint=result`.
2. **Normalize provider IDs** — accept `clerk`, `auth0`; map aliases (`clerk.dev`, `auth0.com`) to canonical ids.
3. **Filter unsupported providers** — if a provider is unknown, mark `enabled=false` with warning.
4. **Choose single primary provider** — when both `clerk` and `auth0` are requested, prefer the one explicitly named; if both explicit, prefer `clerk` for App Router simplicity and note the override.
5. **Apply project-rule preferences** — if `project_rules.tooling_preferences` boosts or blocks a provider, follow it; if a required provider is blocked, escalate to `control/policy_enforcer.md`.
6. **Set public and protected paths** — inherit from `auth_requirements`; fill defaults (`/` and `/sign-in` public, `/dashboard` protected) when missing.
7. **Map provided keys** — place `publishable_key`/`domain`/`client_id`/`client_secret`/`redirect_uri` into the config when supplied; otherwise leave `None` so `auth_runtime_integrator.md` writes placeholders.
8. **Return config** with hint `execution` when a provider is enabled, `result` when disabled.

## Failure Modes

| Condition | Response |
|---|---|
| All requested providers invalid | Return empty config with `next_phase_hint=result`; warn |
| Required provider blocked by project rules | Escalate to `control/policy_enforcer.md` |
| Provider keys present but provider disabled | Ignore keys; log inconsistency |
| Jurisdiction requires data residency unsupported by provider | Flag `needs_refinement` for `compliance_checker.md` |
