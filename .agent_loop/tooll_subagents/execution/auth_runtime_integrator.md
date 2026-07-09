# Auth Runtime Integrator

## Role
Execution agent that materializes auth/identity plans into concrete Next.js App Router wrappers using `runtime/auth/AuthIntegrationEngine`. Generates provider-specific components, sign-in page, environment example, and middleware while respecting existing project files.

## Contract

### Receives
- `provider_config`: from `auth_provider_selector.md`
- `auth_requirements`: from `auth_requirements_analyst.md`
- `target_dir`: str — Next.js project root
- `optimization_plan`: optional from `analytics_optimizer.md` or `i18n_optimizer.md`

### Returns
- `integration_report`: dict — {
  - `files_written`: list[str]
  - `files_modified`: list[str]
  - `providers_installed`: list[str]
  - `errors`: list of { `file`, `reason` }
  - `notes`: list[str]
  - `next_phase_hint`: enum (`observability`, `execution`, `result`)
}

### Side effects
- Writes `src/components/auth/AuthProvider.tsx`, `src/components/auth/SignInButton.tsx`, `src/components/auth/UserButton.tsx`, `src/components/auth/ProtectedRoute.tsx`, `src/app/sign-in/page.tsx`, `.env.local.example`, and `middleware.ts` (only if none exists).
- Injects the correct npm dependency (`@clerk/nextjs` or `@auth0/nextjs-auth0`) into `package.json`.
- Logs file mutations to `audit_logger.md`

## Decision Flow

1. **Validate target directory** — ensure `target_dir` contains `package.json`; abort if not.
2. **Apply safety guardrails** — route `provider_config` secrets through `safety-control/data_leak_preventer.md`; abort on PII leak block.
3. **Validate file system guard** — confirm all writes stay inside `target_dir`; if `control/file_system_guard.md` blocks, escalate to `tooll_subagents/execution/human_approval.md`.
4. **Instantiate engine** — create `runtime.auth.AuthIntegrationEngine(target_dir, provider_config)`.
5. **Run engine** — call `engine.run()` to generate wrappers, sign-in page, env example, and middleware.
6. **Record middleware skip note** — if `middleware.ts` already exists, add a note to the integration report instead of overwriting.
7. **Wire layout provider** — if a root layout (`src/app/layout.tsx` or `src/app/[locale]/layout.tsx`) exists, insert `AuthProvider` wrapper via `tools_replace/replace_in_file/write_executor.md` when safe.
8. **Return integration report** with hint `observability` for audit, or `result` if errors block continuation.

## Failure Modes

| Condition | Response |
|---|---|
| Target directory not a Next.js project | Return error, `next_phase_hint=result`; log to `audit_logger.md` |
| `file_system_guard.md` blocks write | Abort; route to `human_approval.md` for explicit scope grant |
| `data_leak_preventer.md` blocks secret payload | Abort; route to `safety-control/safety_assessor.md` |
| No enabled provider | Skip code generation; return empty report |
| Middleware exists | Skip middleware write and record note; continue with other files |
| `safety_guardrails.md` aborts execution mid-run | Halt; preserve trace; route to `safety-control/safety_assessor.md` |
