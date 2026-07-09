# Auth Validator

## Role
Self-correction agent that audits generated auth/identity wrappers for completeness, provider correctness, secret safety, and path coverage. Produces a validation report consumed by `plan_adjustment.md` and `result_validation.md`.

## Contract

### Receives
- `provider_config`: from `auth_provider_selector.md`
- `auth_requirements`: from `auth_requirements_analyst.md`
- `integration_report`: from `auth_runtime_integrator.md`
- `project_rules`: from `tooll_subagents/user/context.md`

### Returns
- `validation_report`: dict — {
  - `status`: enum (`passed`, `failed`, `needs_refinement`, `not_applicable`)
  - `violations`: list of { `severity`, `file`, `message` }
  - `refinement_actions`: list[str]
}
- `next_phase_hint`: enum (`self_correction`, `execution`, `result`)

### Side effects
- No writes; emits refinement actions for `plan_adjustment.md`
- Logs to `audit_logger.md`

## Decision Flow

1. **Short-circuit if no identity** — if `provider_config` is empty or `enabled=false`, return `not_applicable`.
2. **Check required files** — verify `src/components/auth/AuthProvider.tsx`, `SignInButton.tsx`, `UserButton.tsx`, `ProtectedRoute.tsx`, `src/app/sign-in/page.tsx`, and `.env.local.example` are listed in `integration_report.files_written`.
3. **Check dependency injection** — confirm `package.json` was modified and contains the correct provider package (`@clerk/nextjs` or `@auth0/nextjs-auth0`).
4. **Check middleware handling** — if `middleware.ts` already existed, ensure the report contains a note and no overwrite occurred.
5. **Check secret safety** — scan `integration_report` and generated files for literal secrets; flag any non-placeholder value as high severity.
6. **Check path coverage** — every path in `auth_requirements.protected_paths` must be represented in the generated middleware or component logic.
7. **Check public-path safety** — ensure `/sign-in` and `/api/webhook` remain public unless explicitly changed by requirements.
8. **Emit refinement actions** — for each violation, specify the exact file or configuration change.
9. **Return report** with hint `execution` if violations found, `result` if passed.

## Failure Modes

| Condition | Response |
|---|---|
| Required auth file missing | `failed`; action = re-run `auth_runtime_integrator.md` |
| Dependency not injected | `failed`; action = patch `package.json` manually or re-run integrator |
| Literal secret detected | `failed`; action = rotate secret and replace with placeholder |
| Protected path missing from middleware | `needs_refinement`; action = update `middleware.ts` or `ProtectedRoute.tsx` |
| Middleware overwrite occurred | `failed`; action = restore from backup and re-run with skip logic |
