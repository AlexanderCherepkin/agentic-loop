# Main Loop

## Role
Top-level orchestration agent that drives the entire ReAct (Reasoning + Acting) cycle. Receives the raw user request, iterates through planning, execution, observation, and self-correction until the task is complete, fails irrecoverably, or requires human escalation. Owns the session lifecycle, iteration budget, and final handoff to the result layer.

## Contract

### Receives
- `raw_user_input`: string, image, or structured payload from the user interface
- `session_context`: session_id, user profile, and conversation history pointer
- `system_wide_policies`: active policy and safety configuration identifiers
- `max_iterations`: integer — hard limit on ReAct loops (default 5)
- `token_budget`: integer — remaining context-window budget for the session
- `compaction_interval`: integer — compress ReAct history into summary every N iterations (default 3)

### Returns
- `final_response`: user-facing solution, explanation, or artifact
- `termination_status`: enum (`success`, `partial`, `failure`, `escalated_human`)
- `session_metrics`: summary of iterations, tools used, time elapsed, tokens consumed, safety checks passed
- `audit_anchor`: traceable ID linking to full `audit_logger.md` record

### Side Effects
- Initializes and terminates session state via `orchestrator/state_manager.md`
- Drives all `orchestrator/`, `safety-control/`, `mutual_check/`, `control/`, `tooll_subagents/`, and `tools_*` invocations
- Triggers context compaction via `tools_memory/memory_store/context_compressor.md`, `summarizer.md`, and `eviction_policy.md` every N iterations
- Consumes token budget and API quota

## Decision Flow

1. **Initialize session** — call `orchestrator/state_manager.md` to create or resume session; load `session_context` and `system_wide_policies`.
2. **Ingest user input** — pass `raw_user_input` to `tooll_subagents/user/request.md` for parsing, `context.md` for enrichment, and `limitations.md` for capability gap analysis.
3. **Safety pre-check** — route parsed request through `safety-control/` (input_sanitizer, threat_detector, bias_detector) and `control/` (scope_manager, policy_enforcer). If blocked, halt with `termination_status=escalated_human` or `failure`.
4. **Design-intake branch (conditional)** — pass parsed request to `tooll_subagents/user/design_intake.md`:
   - If `request_type != design_project`, continue to Plan phase unchanged.
   - If `request_type == design_project`:
     - **Runtime fast path (default)** — when the runtime has MCP enabled and `figma_run_pipeline` is available, invoke the full pipeline directly via MCP with the `design_descriptor` (Figma source, backend spec, target scope). For `output_mode == full_code` or `both`, short-circuit to Result synthesis (step 6) with generated files and `next_phase_hint=deliver`. For `output_mode == technical_assignment`, attach the returned `design_blueprint` to the Plan phase.
     - **Blueprint path** — if the runtime fast path is unavailable or explicitly disabled:
       a. Invoke `tooll_subagents/planning/figma_design_analyst.md` with the `design_descriptor` to produce a `design_blueprint` (Figma structure, spec, design tokens, components, assets).
       b. Invoke `tooll_subagents/planning/design_to_code_planner.md` with the `design_blueprint` to produce a `handoff_package`.
       c. If `handoff_type == technical_assignment`, treat the package as the task definition and continue to the Plan phase with `design_blueprint` attached.
       d. If `handoff_type == full_code` or `mixed`, short-circuit to Result synthesis (step 6) with generated files and `next_phase_hint=deliver`.
5. **Plan phase** — invoke `tooll_subagents/planning/` (task_decomposition, cost_risk_assessment, tool_plan_selection, internal_monologue) to produce initial task graph and tool plan. If a design blueprint is present, `tool_plan_selection` must include Figma MCP tools.
6. **Enter ReAct loop** — for each iteration up to `max_iterations`:
   a. **Check budget** — if `token_budget` exhausted, break and set `termination_status=partial`.
   b. **Mutual pre-check** — pass plan through `mutual_check/` (consistency_checker, quota_manager, anomaly_detector) and `control/` (resource_monitor, permission_checker). If rejected, attempt `tooll_subagents/self_correction/plan_adjustment.md`.
   c. **Execute phase** — invoke `tooll_subagents/execution/` (tool_invocation, safety_guardrails, human_approval, action_logging) to run the selected tool pipeline.
   d. **Observe phase** — collect results via `tooll_subagents/observability/` (environment_result, runtime_output, file_context, memory_enrichment).
   e. **Validate phase** — invoke `tooll_subagents/self_correction/result_validation.md` to assess success against original request.
   f. **Decide loop or terminate** — call `tooll_subagents/self_correction/recursion_or_termination.md`:
      - `recurse` → feed adjusted plan from `plan_adjustment.md` into next iteration.
      - `terminate_success` → break and proceed to result synthesis.
      - `terminate_partial` or `terminate_failure` → break with corresponding status.
      - `escalate_human` → route to `tooll_subagents/self_correction/assistance_request.md`.
   g. **Compact context (conditional)** — if `iteration_count % compaction_interval == 0` and decision is `recurse`:
      - Invoke `tools_memory/memory_store/context_compressor.md` on accumulated ReAct step history (iterations 1..current) with `preserve=["decisions","actions","errors"]` and `format="structured"`.
      - Invoke `tools_memory/memory_store/summarizer.md` (level=`short`) to distill compressed output into a running `condensed_history`.
      - Invoke `tools_memory/memory_store/eviction_policy.md` (action=`evict`) to remove raw compressed steps from active context, retaining only the summary.
      - Feed `condensed_history` into next iteration's context via `tooll_subagents/user/context.md`.
      - If compaction fidelity drops below 0.6, log warning to `mutual_check/quality_assessor.md` and retain original steps for one more iteration.
7. **Synthesize result** — invoke `tooll_subagents/result/` (solution, modified_files, action_report, summary_recommendations) to compose final deliverables. If a design handoff package is present, include generated files, assets, and `next_phase_hint` in the output.
8. **Safety post-check** — route final output through `safety-control/output_reviewer.md`, `data_leak_preventer.md`, and `content_checker.md`.
9. **Final mutual check** — pass through `mutual_check/quality_assessor.md` and `result_validator.md`.
10. **Deliver** — return `final_response`, `termination_status`, `session_metrics`, and `audit_anchor`.
11. **Cleanup** — archive session state, release quota locks, and log completion to `audit_logger.md`.

## Failure Modes

| Condition | Response |
|---|---|
| Raw user input completely unparseable | `termination_status=failure`, `final_response` = clarification request; preserve session |
| Safety pre-check blocks on every iteration | `termination_status=escalated_human`, route to `control/human_oversight.md` |
| Max iterations reached without success | `termination_status=partial`, include `session_metrics` and best-effort result |
| Token budget exhausted mid-iteration | Gracefully truncate, set `termination_status=partial`, return partial result with budget notice |
| Core orchestrator or safety agent unreachable | `termination_status=failure`, emit diagnostic anchor, queue for system recovery |
| ReAct loop enters oscillation (same plan repeated) | Force break after 2 identical iterations, invoke `plan_adjustment.md` with forced novelty constraint |
| Session state corruption detected | Attempt recovery from last known good checkpoint; if fails, `termination_status=failure` |
| Context compaction fails (compressor returns error) | Skip compaction this iteration; retry on next `compaction_interval` tick; log to `mutual_check/anomaly_detector.md` |
| Compaction fidelity < 0.6 (critical information at risk) | Retain original steps for one more iteration; re-attempt with larger `target_size`; if still low fidelity after 2 retries, skip compaction and alert `control/human_oversight.md` |
| Eviction would remove steps still referenced by active plan | Defer eviction for referenced steps; compact only non-referenced segments; log partial compaction to `audit_logger.md` |
