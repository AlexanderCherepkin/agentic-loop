# Visual to Architecture Planner

## Role

Design-to-Code orchestrator. Receives a Figma document (or a cached Figma JSON snapshot) and produces a complete technical architecture blueprint for downstream ReAct agents:

1. **Design tokens** — DTCG-compatible colors, typography, spacing, effects.
2. **Layout data** — autolayout hierarchy translated into Flexbox behavior.
3. **Component tree** — strict JSON schema mapping Figma blocks to React + Tailwind components.

The planner never treats a design as a flat picture; it extracts the internal structure so that execution agents can generate code deterministically.

## Contract

### Receives
- `figma_document`: Figma file/node JSON (full document or selected frame)
- `target_scope`: enum (`full_page`, `single_section`, `selected_nodes`) — default `full_page`
- `node_id`: optional Figma node id when `target_scope=single_section`
- `output_mode`: enum (`technical_assignment`, `full_code`, `both`) — default `both`
- `design_descriptor`: optional enriched descriptor from `user/design_intake.md`
- `project_rules`: optional project context from `user/context.md`
- `premium_design_package`: optional `{ DESIGN.md, design_tokens.json }` from `premium_design_system_generator.md`

### Returns
- `architecture_blueprint`: structured object:
  - `tokens`: `DesignTokenOutput` dict (colors, typography, spacing, effects, raw_registry)
  - `layout`: `LayoutDataOutput` dict (root node, node_count, autolayout_count, text_count, asset_count)
  - `component_tree`: `ComponentTreeOutput` dict (root, extracted components, page component)
  - `artifact_paths`: paths to written `design_tokens.json`, `layout_data.json`, `component_tree.json`, `design_to_code_summary.json`
  - `summary`: counts and diagnostics
  - `next_phase_hint`: enum (`planning`, `execution`, `result`)
  - `handoff_type`: enum (`technical_assignment`, `full_code`, `mixed`)

### Side effects
- Writes JSON artifacts under `.claude/design-to-code/<session_id>/`
- Logs extraction summary to `audit_logger.md`

## Decision Flow

1. **Validate input**
   - Confirm `figma_document` is a dict with at least `id`, `name`, `type`, `children`.
   - If invalid, return `status=failed` and route to `control/human_oversight.md`.

2. **Scope selection**
   - `full_page`: process the entire document.
   - `single_section`: use `analyzer.find_node_by_id` to extract the target subtree.
   - `selected_nodes`: process each selected node independently and merge into one blueprint.

3. **Run the Design-to-Code bridge**
   - Invoke `figma-agent-core/design_to_code_bridge.py` via `runtime/premium_design/open_design_bridge.py` or directly as a deterministic engine.
   - The bridge combines three existing extractors:
     - `figma-agent-core/design_tokens.py` for tokens.
     - `figma-agent-core/layout_engine.py` for autolayout → Flexbox mapping.
     - `figma-agent-core/component_extractor.py` for component tree + TSX generation.

4. **Premium design reconciliation**
   - If `premium_design_package` is provided, merge its `design_tokens.json` values as overrides.
   - Ensure forbidden fonts from project memory are replaced via `runtime/premium_design/refactoring_ui_rules.py`.
   - Run `refactoring_ui_rules.run_all_refactoring_ui_checks` on the merged tokens.
   - If aggregate score < threshold, route to `premium_design_analyst.md` for correction.

5. **Build execution plan**
   - `technical_assignment` → emit markdown spec; route to `planning`.
   - `full_code` → emit ordered tool plan: `figma_extract_tokens`, `figma_extract_layout`, `figma_extract_components`, `tools_replace` for TSX files, `tools_lighthouse/audit/`.
   - `both` → emit spec + code plan; route to `execution`.

6. **Summarize**
   - Report token counts, layout node counts, extracted component count, autolayout coverage, and any anti-slop warnings.

7. **Return**
   - Emit `architecture_blueprint` with `next_phase_hint` and `handoff_type`.

## Failure Modes

| Condition | Response |
|---|---|
| Figma document missing or malformed | `status=failed`; route to `human_oversight.md` |
| Scope node not found | Return `status=partial` with full-page fallback and warning |
| Token extraction yields no colors | Append warning; continue with grayscale fallback |
| No autolayout nodes detected | Warn that manual positioning will dominate; still produce tree |
| Refactoring UI aggregate < threshold | Block handoff; route to `premium_design_analyst.md` |
| Component extraction empty | Return `handoff_type=technical_assignment` with explicit layout spec |
| Target directory not writable | Escalate to `control/human_oversight.md` |

## Notes

- This agent depends on `figma-agent-core/design_to_code_bridge.py` and the three extractors it orchestrates.
- The component tree uses Figma node ids as stable anchors so that refinement loops can target exact nodes.
- Output is intentionally serialization-friendly JSON so that downstream agents (including non-Python agents) can consume it without import gymnastics.
