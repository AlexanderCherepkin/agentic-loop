# Main Loop

## Role
Top-level orchestration agent that drives the entire ReAct (Reasoning + Acting) cycle. Receives the raw user request, iterates through planning, execution, observation, and self-correction until the task is complete, fails irrecoverably, or requires human escalation. Owns the session lifecycle, iteration budget, and final handoff to the result layer.

## Contract

### Receives
- `raw_user_input`: string, image, or structured payload from the user interface
- `session_context`: session_id, user profile, and conversation history pointer
- `system_wide_policies`: active policy and safety configuration identifiers
- `max_iterations`: integer — hard limit on ReAct loops (default 5)
- `lighthouse_max_iterations`: integer — hard limit on Lighthouse refinement loops (default 8)
- `token_budget`: integer — remaining context-window budget for the session
- `compaction_interval`: integer — compress ReAct history into summary every N iterations (default 3)
- `ponytail_mode`: string | None — explicit Ponytail intensity (`lite`, `full`, `ultra`, `off`). Falls back to `PONYTAIL_DEFAULT_MODE` env, then `full`.
- `headroom_enabled`: boolean | None — explicit Headroom context-compression toggle. Falls back to `HEADROOM_ENABLED` env, then `true`.
- `memanto_enabled`: boolean | None — explicit Memanto semantic-memory toggle. Falls back to `MEMANTO_ENABLED` env, then `true`.
- `mem0_enabled`: boolean | None — explicit Mem0 long-term memory toggle. Falls back to `MEM0_ENABLED` env, then `true`.

### Returns
- `final_response`: user-facing solution, explanation, or artifact
- `termination_status`: enum (`success`, `partial`, `failure`, `escalated_human`)
- `session_metrics`: summary of iterations, tools used, Lighthouse iterations, time elapsed, tokens consumed, safety checks passed
- `audit_anchor`: traceable ID linking to full `audit_logger.md` record

### Side Effects
- Initializes and terminates session state via `orchestrator/state_manager.md`
- Drives all `orchestrator/`, `safety-control/`, `mutual_check/`, `control/`, `tooll_subagents/`, and `tools_*` invocations
- Triggers context compaction via `tools_memory/memory_store/context_compressor.md`, `summarizer.md`, and `eviction_policy.md` every N iterations
- Persists long-term session facts to Memanto via `memanto_remember.md` when `memanto_enabled=true`
- Persists long-term session facts to Mem0 via `mem0_remember.md` when `mem0_enabled=true`
- Consumes token budget and API quota

## Decision Flow

Mandatory spec-pilot gates for non-trivial tasks:
`task_scoping_agent.md`, `spec_approval_gate.md`, `spec_lock.md`, `spec_compliance_validator.md`, `verification_planner.md`, `gotcha_extractor.md`, `skill_packager.md`.

1. **Initialize session** — call `orchestrator/state_manager.md` to create or resume session; load `session_context` and `system_wide_policies`. Resolve the effective Ponytail mode from `ponytail_mode`, env `PONYTAIL_DEFAULT_MODE`, or default `full`; pass it to `tooll_subagents/user/context.md` as `ponytail_mode`. Resolve the effective Headroom toggle from `headroom_enabled`, env `HEADROOM_ENABLED`, or default `true`; pass it to `tooll_subagents/user/context.md` as `headroom_enabled`. Resolve the effective Memanto toggle from `memanto_enabled`, env `MEMANTO_ENABLED`, or default `true`; pass it to `tooll_subagents/user/context.md` as `memanto_enabled`. Resolve the effective Mem0 toggle from `mem0_enabled`, env `MEM0_ENABLED`, or default `true`; pass it to `tooll_subagents/user/context.md` as `mem0_enabled`. If `memanto_enabled=true`, ensure the Memanto agent namespace exists via `memanto_create_agent` and, on resuming a session, invoke `memanto_recall.md` with the session ID and `query="recent context"` to preload relevant prior state. If `mem0_enabled=true`, on resuming a session invoke `mem0_recall.md` with `query="recent context"` to preload relevant prior state.
2. **Ingest user input** — pass `raw_user_input` to `tooll_subagents/user/request.md` for parsing, `context.md` for enrichment, and `limitations.md` for capability gap analysis.
3. **Safety pre-check** — route parsed request through `safety-control/` (input_sanitizer, threat_detector, bias_detector) and `control/` (scope_manager, policy_enforcer). If blocked, halt with `termination_status=escalated_human` or `failure`.
4. **Scope and spec gate (conditional)** — invoke `tooll_subagents/planning/task_scoping_agent.md` to classify the task as `trivial`, `medium`, or `large` and decide whether an approved spec is required. Apply the gate only to build/creation tasks; do NOT apply it to trivial edits (rename, typo, spacing, one-button change), running a build, making a commit, applying review fixes, or writing summary/text. When unsure whether a request is trivial or a real build, ask one scoping question about scale. For `trivial` tasks, skip spec approval and proceed directly to a single lightweight action. For `medium` and `large` tasks, invoke `tooll_subagents/planning/spec_approval_gate.md` to conduct the interview, produce a written spec, and require explicit user approval. If the user says a stop-phrase such as "стоп, сначала спека", immediately return to the spec drafting step and do not invoke sub-agents. If `spec_status` is not `approved`, short-circuit to Result synthesis with the clarifying questions or the pending spec and `termination_status=success`. If the user approves, store `approved_spec` in session state and continue to the Plan phase.
5. **Spec lock enforcement** — before entering the Plan phase or dispatching any sub-agent, invoke `control/spec_lock.md` with `task_scope`, `spec_status`, and `approved_spec`. If the lock is `locked`, abort execution and return to `spec_approval_gate.md`. If the lock is `open`, proceed.
4. **Design-intake branch (conditional)** — pass parsed request to `tooll_subagents/user/design_intake.md`:
   - If `request_type` is `client_order`, invoke `tooll_subagents/user/client_brief_agent.md` to conduct a structured PM-style intake. If the brief agent returns `next_action=ask_user`, short-circuit to Result synthesis with the clarifying questions and `termination_status=success`. If it returns `next_action=proceed`, continue to the Figma/design pipeline with the enriched `design_descriptor` and `client_brief` attached.
   - If `request_type != design_project` and not `client_order`, continue to Plan phase unchanged.
   - If `request_type == design_project`:
     - **Runtime fast path (default)** — when the runtime has MCP enabled and `figma_run_pipeline` is available, invoke the full pipeline directly via MCP with the `design_descriptor` (Figma source, backend spec, target scope). For `output_mode == full_code` or `both`, short-circuit to Result synthesis (step 6) with generated files and `next_phase_hint=deliver`. For `output_mode == technical_assignment`, attach the returned `design_blueprint` to the Plan phase.
     - **Blueprint path** — if the runtime fast path is unavailable or explicitly disabled:
       a. Invoke `tooll_subagents/planning/figma_design_analyst.md` with the `design_descriptor` to produce a `design_blueprint` (Figma structure, spec, design tokens, components, assets). The analyst orchestrates `tooll_subagents/planning/figma_precise_mode_auditor.md` for the Precise Mode readiness audit, `tooll_subagents/planning/asset_agent.md` for safe asset-download planning, and `tooll_subagents/planning/image_enrichment_agent.md` for bounded external image enrichment.
       b. Invoke `tooll_subagents/planning/design_to_code_planner.md` with the `design_blueprint` to produce a `handoff_package`.
       c. If `handoff_type == technical_assignment`, treat the package as the task definition and continue to the Plan phase with `design_blueprint` attached.
       d. If `handoff_type == full_code` or `mixed`, short-circuit to Result synthesis (step 6) with generated files and `next_phase_hint=deliver`.
6. **Plan phase** — invoke `tooll_subagents/planning/` (task_decomposition, cost_risk_assessment, tool_plan_selection, internal_monologue) to produce initial task graph and tool plan. The plan must be derived from `approved_spec` when one exists; any deviation must be re-approved by the user. If a design blueprint is present, `tool_plan_selection` must include Figma MCP tools. For front-end generation tasks, `tool_plan_selection` must also include `tools_lighthouse/audit/lighthouse_optimizer.md` and, if no safe-component layer exists, a sub-task to generate `src/components/safe/` (`SafeLink`, `ResponsivePicture`, `TouchSafeElement`). For any coding task, `tool_plan_selection` must include `ponytail_injector.md` so the code-generating agent's system prompt receives the Ponytail protocol. If `headroom_enabled=true`, `tool_plan_selection` must also include `headroom_injector.md` to identify large tool outputs/RAG chunks and insert `headroom_compressor.md` / `headroom_retriever.md` steps. If `memanto_enabled=true`, `tool_plan_selection` must include `memanto_recall.md` before task decomposition so the planner can retrieve relevant long-term constraints, prior decisions, and user preferences; it must also insert `memanto_remember.md` after significant state changes (decisions, constraints, completed milestones) and `memanto_answer.md` at the end-of-session summary step. If `mem0_enabled=true`, `tool_plan_selection` must include `mem0_recall.md` before task decomposition and `mem0_remember.md` after significant state changes; `mem0_list.md` may be used for session audits.
   - **Verification planning sub-step** — after `tool_plan_selection.md`, invoke `tooll_subagents/planning/verification_planner.md` with the `approved_spec` and `tool_plan` to produce a `verification_plan`. Attach the plan to `approved_spec["verification_plan"]` and pass it to the validate phase. If `verification_plan.required=true`, the validate phase must execute every listed automated check before claiming the result ready. If the verification planner is skipped because no spec exists, record `verification_plan_status=skipped`.
7. **Enter ReAct loop** — for each iteration up to `max_iterations`:
   a. **Check budget** — if `token_budget` exhausted, break and set `termination_status=partial`.
   b. **Mutual pre-check** — pass plan through `mutual_check/` (consistency_checker, quota_manager, anomaly_detector) and `control/` (resource_monitor, permission_checker). If rejected, attempt `tooll_subagents/self_correction/plan_adjustment.md`.
   c. **Execute phase** — invoke `tooll_subagents/execution/` (tool_invocation, safety_guardrails, human_approval, action_logging) to run the selected tool pipeline. If the user issues a stop-phrase such as "стоп, сначала спека" during execution, immediately abort the current phase and return to `spec_approval_gate.md`.
   d. **Observe phase** — collect results via `tooll_subagents/observability/` (environment_result, runtime_output, file_context, memory_enrichment). If `memanto_enabled=true`, route durable facts and decisions through `memanto_remember.md` in addition to the regular `memory_enrichment.md` so they become queryable across sessions. If `mem0_enabled=true`, route durable conversation turns and extracted facts through `mem0_remember.md` in addition to the regular `memory_enrichment.md` so they become queryable across sessions.
   e. **Validate phase** — invoke `tooll_subagents/self_correction/result_validation.md` with `lighthouse_max_iterations=8` to assess success against the original request. Before claiming the result is ready, describe the verification plan and run it — tests, linter, browser, or script. If a `/goal` fast-critic verdict is required, invoke `tooll_subagents/self_correction/goal_evaluator.md`. If a front-end artifact is present, include `tools_browser/headless_automation/visual_qa_agent.md` in validation and, if no Lighthouse report was supplied, trigger the `tools_lighthouse/audit/` pipeline. If an `approved_spec` exists, also invoke `tooll_subagents/self_correction/spec_compliance_validator.md` to verify that deliverables, success criteria, scope, and execution order match the approved spec.
   f. **Decide loop or terminate** — call `tooll_subagents/self_correction/recursion_or_termination.md` with `lighthouse_iteration_count` and `lighthouse_max_iterations=8`:
      - `recurse` → feed adjusted plan from `plan_adjustment.md` into next iteration.
      - `terminate_success` → break and proceed to result synthesis.
      - `terminate_partial` or `terminate_failure` → break with corresponding status.
      - `escalate_human` → route to `tooll_subagents/self_correction/assistance_request.md`.
   g. **Compact context (conditional)** — if `iteration_count % compaction_interval == 0` and decision is `recurse`:
      - If `headroom_enabled=true`, invoke `tooll_subagents/observability/headroom_compressor.md` on accumulated ReAct step history (iterations 1..current) with `preserve=["decisions","actions","errors"]` and store the resulting hash for later retrieval. If Headroom is unavailable, fall back to `tools_memory/memory_store/context_compressor.md`.
      - If `headroom_enabled=false` or Headroom unavailable, invoke `tools_memory/memory_store/context_compressor.md` on the same history.
      - Invoke `tools_memory/memory_store/summarizer.md` (level=`short`) to distill compressed output into a running `condensed_history`.
      - Invoke `tools_memory/memory_store/eviction_policy.md` (action=`evict`) to remove raw compressed steps from active context, retaining only the summary (and any Headroom retrieval hash).
      - Feed `condensed_history` into next iteration's context via `tooll_subagents/user/context.md`.
      - If compaction fidelity drops below 0.6, log warning to `mutual_check/quality_assessor.md` and retain original steps for one more iteration.
8. **Synthesize result** — invoke `tooll_subagents/result/` (solution, modified_files, action_report, summary_recommendations) to compose final deliverables. If a design handoff package is present, include generated files, assets, and `next_phase_hint` in the output.
9. **Extract gotchas and package skills** — if the session produced corrections, iterations, or user feedback, invoke `tooll_subagents/observability/gotcha_extractor.md` to capture reusable pitfalls and propose a skill candidate. If `gotcha_extractor.recommendation=propose_skill` and the user explicitly approves, invoke `tooll_subagents/result/skill_packager.md` to materialize `.claude/skills/<name>/SKILL.md`. Do not create a skill without explicit user approval.
10. **Safety post-check** — route final output through `safety-control/output_reviewer.md`, `data_leak_preventer.md`, and `content_checker.md`.
11. **Final mutual check** — pass through `mutual_check/quality_assessor.md` and `result_validator.md`.
12. **Deliver** — return `final_response`, `termination_status`, `session_metrics`, and `audit_anchor`.
13. **Cleanup** — archive session state, release quota locks, and log completion to `audit_logger.md`. If `memanto_enabled=true`, invoke `memanto_answer.md` with `query="What should the next session know about this task?"` and store the resulting summary via `memanto_remember.md` under type `context` with tags `["session_summary", "handoff"]` so the next session can recall it. If `mem0_enabled=true`, invoke `mem0_recall.md` with `query="What should the next session know about this task?"` and store the top retrieved memories plus a generated summary via `mem0_remember.md` as a `context` memory with metadata tags `["session_summary", "handoff"]` so the next session can recall it.

## Failure Modes

| Condition | Response |
|---|---|
| Raw user input completely unparseable | `termination_status=failure`, `final_response` = clarification request; preserve session |
| Safety pre-check blocks on every iteration | `termination_status=escalated_human`, route to `control/human_oversight.md` |
| Spec approval gate rejected or repeatedly unanswered | `termination_status=success`, return clarifying questions; do not start sub-agents |
| Spec lock blocks execution | `termination_status=success`, return to spec approval gate; log to `audit_logger.md` |
| Max iterations reached without success | `termination_status=partial`, include `session_metrics` and best-effort result |
| Lighthouse max iterations reached without 100% | `termination_status=escalated_human`; include final Lighthouse failure log; route to `assistance_request.md` |
| Token budget exhausted mid-iteration | Gracefully truncate, set `termination_status=partial`, return partial result with budget notice |
| Core orchestrator or safety agent unreachable | `termination_status=failure`, emit diagnostic anchor, queue for system recovery |
| ReAct loop enters oscillation (same plan repeated) | Force break after 2 identical iterations, invoke `plan_adjustment.md` with forced novelty constraint |
| Session state corruption detected | Attempt recovery from last known good checkpoint; if fails, `termination_status=failure` |
| Context compaction fails (compressor returns error) | Skip compaction this iteration; retry on next `compaction_interval` tick; log to `mutual_check/anomaly_detector.md` |
| Compaction fidelity < 0.6 (critical information at risk) | Retain original steps for one more iteration; re-attempt with larger `target_size`; if still low fidelity after 2 retries, skip compaction and alert `control/human_oversight.md` |
| Eviction would remove steps still referenced by active plan | Defer eviction for referenced steps; compact only non-referenced segments; log partial compaction to `audit_logger.md` |
| Ponytail injection fails or returns invalid mode | Fall back to base system prompt, set mode `full`, and log to `audit_logger.md`; continue planning |
| Headroom compression unavailable or fails | Skip Headroom compression this iteration; fall back to `context_compressor.md` if needed; log to `audit_logger.md` and continue |
| Memanto unavailable or remember/recall/answer fails | Skip Memanto operation; fall back to in-memory store or regular `memory_enrichment.md`; log to `audit_logger.md` and continue |
| Mem0 unavailable or add/search/get_all/delete fails | Skip Mem0 operation; fall back to in-memory store or regular `memory_enrichment.md`; log to `audit_logger.md` and continue |

