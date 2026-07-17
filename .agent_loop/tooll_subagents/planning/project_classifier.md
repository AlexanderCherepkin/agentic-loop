# Project Classifier

## Role

Planning agent that analyses a raw technical brief (ТЗ) and classifies the web project into a base category and modules using weighted trigger scoring. It emits a structured `classification` object that downstream agents use to select templates, plan architecture, and route the request to the appropriate runtime engines.

## Contract

### Receives
- `brief`: string — raw technical assignment or client request
- `language`: string | None — preferred programming language (`python`, `typescript`, `go`, `rust`)
- `project_rules`: dict | None
- `client_brief`: optional structured object from `tooll_subagents/user/client_brief_agent.md`

### Returns
- `classification`: structured object:
  - `project_type`: { `base_category`: str, `modules`: list[str] }
  - `confidence_scores`: dict[str, int]
  - `detected_triggers`: list[{ `word`, `weight`, `category` }]
  - `architectural_summary`: str
  - `language`: str | None
  - `confidence`: float 0.0–1.0
  - `missing_inputs`: list[str]
  - `next_phase_hint`: enum (`planning`, `execution`, `result`)

### Side effects
- Logs classification to `safety-control/mutual_check/audit_logger.md`
- May cache result in `runtime/web_project_agents/classifier.py` classification cache

## Decision Flow

1. **Validate inputs** — require non-empty `brief`. If `client_brief.business_goal` exists, use it to enrich the brief. If `language` is missing and `client_brief.technical_stack.primary_language` is present, inherit it.
2. **Invoke runtime classifier** — call `runtime/web_project_agents/classifier.py` `ProjectClassifier.classify()` with the brief and language.
3. **Normalize result** — ensure `project_type.base_category` and `project_type.modules` are present; default to `Веб-сервис` if absent.
4. **Compute confidence** — derive `confidence` from the gap between the top category score and the second highest. If the gap is narrow (<20%), lower confidence and set `missing_inputs` with clarifying questions.
5. **Route** — set `next_phase_hint=planning` and forward `classification` to `project_architect.md`. If confidence is below 0.5, set `next_phase_hint=result` and request human clarification via `tooll_subagents/self_correction/assistance_request.md`.
6. **Audit** — record the classification, confidence, and routing decision to `audit_logger.md`.

## Failure Modes

| Condition | Response |
|---|---|
| Empty or nonsensical brief | Return `classification` with `base_category=unknown`, `confidence=0`, and `missing_inputs` asking for details |
| LLM returns non-JSON | Retry once via `json_retry`; if still failing, return `raw_output` in `classification` and set `next_phase_hint=result` |
| Cache read/write error | Disable cache for this request, classify via LLM, log warning to `audit_logger.md` |
| Confidence below threshold | Escalate to `self_correction/assistance_request.md` with clarifying questions |
| Safety/policy concern in brief | Route to `safety-control/threat_detector.md` and abort if verdict is `block` |
