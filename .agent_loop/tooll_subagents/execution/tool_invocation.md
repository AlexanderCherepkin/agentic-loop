# Tool Invocation

## Role
Execution driver that dispatches selected tool agents with properly formatted parameters, handles invocation sequencing, and manages the handoff between planning and actual tool execution. Acts as the bridge from abstract plan to concrete tool calls.

## Contract

### Receives
- `tool_plan`: ordered list from `tool_plan_selection.md`
- `execution_context`: runtime environment state (permissions, working directory, available resources)
- `timeout_budget`: milliseconds remaining for this execution phase
- `retry_policy`: enum (`none`, `fixed`, `exponential_backoff`, `circuit_breaker`)

### Returns
- `invocation_results`: list of tool outputs with status, latency, and metadata
- `partial_completion`: boolean — whether all planned tools executed or execution stopped early
- `next_action`: enum (`continue`, `retry_failed`, `abort`, `escalate`) — recommended next step
- `execution_trace`: ordered log of each invocation with input, output summary, and timestamp

### Side Effects
- Calls tool agents via orchestrator/dispatcher.md
- Consumes API quota and token budget
- Mutates filesystem or environment state as per tool behavior

## Decision Flow

1. **Validate tool plan** — verify each tool in plan is available, permitted, and parameter schema matches tool contract.
2. **Pre-flight check** — confirm `timeout_budget` sufficient for estimated latency; if not, prioritize critical path tools.
3. **Initialize trace** — create empty `execution_trace` with plan metadata and start timestamp.
4. **Iterate invocations** — for each tool in `tool_plan`:
   a. Marshal parameters into tool-specific format.
   b. Submit to orchestrator/dispatcher.md with timeout shard.
   c. Wait for result or timeout.
   d. Record result in `execution_trace`.
   e. If success, append output to `invocation_results`.
   f. If failure, apply `retry_policy` (max 3 retries for fixed/exp; circuit_breaker halts after 2 consecutive failures).
5. **Detect partial completion** — if any tool failed permanently or timeout exhausted, set `partial_completion=true`.
6. **Determine next action** — `continue` if all succeeded and more steps remain; `retry_failed` if transient errors and budget allows; `abort` if critical failure or safety block; `escalate` if repeated failure on same tool or novel error.
7. **Return** — emit results, completion flag, next action, trace.

## Failure Modes

| Condition | Response |
|---|---|
| Tool agent unavailable (not loaded or crashed) | `next_action=escalate`, `partial_completion=true`; alert `orchestrator/state_manager.md` |
| Parameter schema mismatch | `next_action=abort`, log schema error; route to `self_correction/plan_adjustment.md` |
| Timeout exhausted mid-sequence | `partial_completion=true`, `next_action=retry_failed` if idempotent; else `abort` |
| Tool returns corrupted or non-deserializable output | `next_action=retry_failed` once; if persists, `abort` and flag `observability/runtime_output.md` |
| Safety layer blocks tool mid-execution | `next_action=abort`, preserve trace up to block point; route to `safety-control/safety_assessor.md` |
