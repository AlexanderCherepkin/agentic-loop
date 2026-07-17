# Dispatcher

## Role
Execution broker that submits concrete work units to selected agents and manages their lifecycle. Handles parameter marshaling, timeout enforcement, retry scheduling, and result collection. Bridges the abstract routing decision from `router.md` into actual agent invocation.

## Contract

### Receives
- `dispatch_request`: structured work unit with target agent, parameters, timeout, and priority
- `agent_descriptor`: metadata about target agent (capability version, concurrency limit, expected latency)
- `execution_mode`: enum (`sync`, `async`, `fire_and_forget`, `batch`)
- `retry_config`: max retries, backoff strategy, and circuit-breaker threshold
- `spec_lock_status`: enum (`open`, `locked`) from `control/spec_lock.md`
- `approved_spec`: dict | None — required when `spec_lock_status=open` for non-trivial work

### Returns
- `dispatch_status`: enum (`submitted`, `queued`, `rejected`, `timeout`, `failed`)
- `result_payload`: agent output if `sync` and completed; null if `async` or pending
- `job_id`: unique identifier for tracking this work unit
- `completion_estimate`: predicted completion time or null if indeterminate

### Side Effects
- Submits work to target agent's execution queue
- Consumes quota via `mutual_check/quota_manager.md`
- Updates agent load metrics
- Logs to `audit_logger.md`

## Decision Flow

1. **Validate request** — ensure `dispatch_request` contains required fields and `agent_descriptor` matches known capability registry.
2. **Check spec lock** — if `spec_lock_status=locked`, return `dispatch_status=rejected` and route back to `control/spec_lock.md`/`tooll_subagents/planning/spec_approval_gate.md`. If `spec_lock_status=open` but `approved_spec` is missing for non-trivial work, treat as locked.
3. **Check quota** — consult `mutual_check/quota_manager.md` for resource availability; if insufficient, `dispatch_status=queued` or `rejected`.
4. **Check agent health** — verify target agent is not in circuit-breaker open state or resource-starved.
5. **Marshal parameters** — convert `dispatch_request` parameters into agent's expected input schema; validate against contract.
6. **Submit work** —
   - `sync`: invoke and block until result or timeout; enforce timeout strictly.
   - `async`: enqueue, return `job_id` immediately; result delivered via callback or polling.
   - `fire_and_forget`: enqueue without result tracking; return immediately.
   - `batch`: collect multiple requests, submit as single batch if agent supports it; return batch job ID.
7. **Monitor execution** — track `job_id` progress; if timeout or error, apply `retry_config` (retry with backoff, fail open, or circuit-break).
8. **Collect result** — on completion, deserialize output, validate against expected schema, and return.
9. **Handle failure** — if retries exhausted, return `failed` with last error; if circuit-breaker threshold reached, mark agent as degraded and route to `fallback_destination` from `router.md`.
10. **Log and return** — emit status, result, job ID, completion estimate.

## Failure Modes

| Condition | Response |
|---|---|
| Target agent crashed or unresponsive | `dispatch_status=failed`, retry to fallback agent; alert `state_manager.md` to update health |
| `spec_lock_status=locked` | `dispatch_status=rejected`, reason="No sub-agents without an approved spec"; route to `control/spec_lock.md` |
| Parameter marshaling fails (schema mismatch) | `dispatch_status=rejected`, return schema error; route to `tooll_subagents/planning/tool_plan_selection.md` for replanning |
| Timeout exceeded but agent still running | `dispatch_status=timeout`, attempt graceful cancellation; return partial result if any |
| Circuit-breaker open for all agents in category | `dispatch_status=rejected`, escalate to `control/human_oversight.md` with degraded-capacity alert |
| Batch submission partially fails | Return mixed-status result with per-item outcomes; flag failed items for individual retry |
| Quota exhaustion mid-dispatch | `dispatch_status=queued` with estimated admission time; do not auto-cancel |
