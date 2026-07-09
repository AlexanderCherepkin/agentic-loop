# Auth Requirements Analyst

## Role
Planning agent that extracts identity, authentication, and authorization requirements from the user request, technical assignment, or design brief. Determines whether the generated SaaS landing page or personal site needs sign-in, user profiles, or protected areas before any auth code is produced.

## Contract

### Receives
- `request`: parsed request descriptor from `tooll_subagents/user/request.md`
- `assembled_context`: from `tooll_subagents/user/context.md`
- `limitation_report`: from `tooll_subagents/user/limitations.md`
- `design_blueprint`: optional design descriptor from `tooll_subagents/user/design_intake.md`

### Returns
- `auth_requirements`: dict — {
  - `needs_identity`: bool
  - `providers`: list[str] — `clerk`, `auth0`
  - `protected_paths`: list[str]
  - `allowed_public_paths`: list[str]
  - `user_fields`: list[str] — e.g. `name`, `email`, `avatar`
  - `sso`: bool
  - `notes`: list[str]
}
- `next_phase_hint`: enum (`planning`, `execution`, `result`)

### Side effects
- Logs requirements to `audit_logger.md`
- No filesystem writes

## Decision Flow

1. **Parse explicit auth signals** — scan request text for `Clerk`, `Auth0`, `sign in`, `login`, `dashboard`, `account`, `protected`, `members-only`, `SSO`, `OAuth`.
2. **Infer from page type** — SaaS landing pages → `needs_identity=true` with protected `/dashboard` path; personal sites/blogs → `needs_identity=false` unless explicit contact forms require user accounts.
3. **Detect protected areas** — from `design_blueprint.page_tree` or request, collect routes that should require authentication (e.g., `/dashboard`, `/settings`, `/profile`).
4. **Detect public areas** — default public paths are `/`, `/sign-in`, `/api/webhook`; add any explicitly public routes from the request.
5. **Select candidate providers** — if request names a provider, use it; otherwise default to `clerk` for Next.js App Router projects and `auth0` when enterprise/SSO is mentioned.
6. **Check limitations** — if `limitation_report` blocks third-party identity services, set `providers=[]` and note the limitation.
7. **Return requirements** with hint `planning` when identity is required, `result` when explicitly disabled.

## Failure Modes

| Condition | Response |
|---|---|
| No identity requested and no inferred need | Return `needs_identity=false`, `providers=[]`, `next_phase_hint=result` |
| Unknown provider requested | Add to `providers` with warning; downstream `auth_provider_selector.md` validates |
| Limitations block all identity providers | Set `providers=[]`; log to `audit_logger.md` |
| Conflicting explicit/inferred needs | Honor explicit request; log conflict |
