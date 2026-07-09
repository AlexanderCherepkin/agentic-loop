# Cookie Consent Blocker

## Role
Execution agent that enforces cookie consent default-deny by blocking analytics and marketing scripts until the user explicitly opts in. Works with `analytics_runtime_integrator.md` and the consent store.

## Contract

### Receives
- `provider_config`: from `analytics_provider_selector.md`
- `script_manifest`: from `analytics_script_injector.md`
- `target_dir`: str
- `consent_store_path`: str — path to generated consent store

### Returns
- `blocker_report`: dict — {
  - `blocked_providers`: list[str]
  - `allowed_providers`: list[str]
  - `files_modified`: list[str]
  - `errors`: list of { `file`, `reason` }
}
- `next_phase_hint`: enum (`observability`, `execution`, `result`)

### Side effects
- Rewrites provider modules to check consent before loading scripts
- Logs changes to `audit_logger.md`

## Decision Flow

1. **Load consent store** — read `src/lib/consent-store.ts` to identify category names and default values.
2. **For each provider in `provider_config`**:
   a. If category is `necessary`, mark `allowed`.
   b. If category is `analytics`/`marketing`/`functional`, wrap initialization with `if (consent[category])` guard.
3. **Modify script injection** — replace unconditional `<script src>` with dynamic loader that checks consent state.
4. **Handle re-consent** — ensure scripts load when user changes consent from `false` to `true` via consent-store event.
5. **Validate safety guardrails** — before rewriting, confirm no destructive changes outside `target_dir`; route through `safety_guardrails.md`.
6. **Return report**.

## Failure Modes

| Condition | Response |
|---|---|
| Consent store missing | Abort; route to `analytics_runtime_integrator.md` to regenerate it |
| Provider module missing | Skip provider; record error |
| Category not found in consent store | Default to `false`; warn |
| `safety_guardrails.md` blocks | Abort; preserve state; route to `safety-control/safety_assessor.md` |
| `file_system_guard.md` blocks write | Abort; route to `human_approval.md` |
