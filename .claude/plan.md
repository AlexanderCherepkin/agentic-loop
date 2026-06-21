# Visual QA V2 — Enhanced Chromium Visual Validation

## Vision
Strengthen the existing Playwright-based Visual QA so it can validate generated Next.js pages against the real Figma design automatically. Introduce an I/O stage to download the Figma reference screenshot, harden the Chromium environment for deterministic screenshots, and add structural layout checks (bounding boxes, overflow, clipped text, overlaps). Feed the new reports into the refinement loop so layout regressions trigger deterministic AST adjustments.

## V2 Scope
Supported:
- Automatic download of the Figma reference screenshot via Figma Images API (`GET /v1/images/{file_key}`).
- Manual `--reference` fallback for local debugging.
- Exact viewport sizing matching the Figma frame.
- Stable screenshot environment: font loading, image loading, disabled transitions/animations.
- Macro bounding-box comparison for structural containers (header, main, sections, grids) with tolerance.
- Micro consistency checks: overflow, clipped text, unexpected element overlaps for non-positioned elements.
- Structured discrepancy reports consumed by the refinement loop.

Out of V2 scope:
- Pixel-perfect comparison of every leaf element.
- Visual diff of dynamic/interactive states (hover, click) — covered by interactive layer mapper.
- Full integration with the runtime main loop as a first-class tool (MCP-only figma pipeline focus).

## Output Artifacts
- `figma_reference.png` (or configured path) — downloaded reference screenshot.
- `visual_qa_report.json` — extended with `layout_checks`, `bbox_comparison`, `font_metrics`, `image_metrics`.
- `.tmp/browser/visual_qa/page_{ts}.png` — generated page screenshot.
- `.tmp/browser/visual_qa/diff_{ts}.png` (optional) — highlighted diff map.

## Architecture

### New Core Module: `figma-agent-core/figma_reference_downloader.py`
- `FigmaReferenceDownloader(token=None, url=None)`:
  - Reads `FIGMA_TOKEN` / `FIGMA_URL` from env, same as `AssetDownloader`.
  - `download_reference(file_key, node_id, output_path, scale=2.0, fmt="png")`:
    1. Calls `GET https://api.figma.com/v1/images/{file_key}?ids={node_id}&format={fmt}&scale={scale}`.
    2. Polls image URL if status is "pending" (Figma async rendering).
    3. Downloads binary to `output_path`.
    4. Returns `{"success": bool, "path": str, "width": int, "height": int, "error": str}`.
- CLI: `--file-key`, `--node-id`, `--scale`, `--format`, `--output`, `--token`, `--url`.

### Update `figma-agent-core/conductor.py`
- New stage `stage_download_figma_reference(...)`:
  - Requires `config["figma_file_key"]` (parsed from `--figma-file` / `FIGMA_URL`) and `config["figma_reference_node_id"]`.
  - Writes reference screenshot to `config["figma_reference_output"]` (default `.tmp/browser/figma_reference.png`).
- Insert stage into `stages_to_run` right after `bootstrap`:
  `["bootstrap", "download_figma_reference", "component_registry", "analyze", ...]`.
- `visual_qa` stage:
  - Pass `reference_path=config.get("figma_reference_output")` if no manual `--reference` provided.
- New CLI args:
  - `--figma-file` (file URL/key, fallback to env).
  - `--figma-reference-node-id` (node id of the frame/page to screenshot).
  - `--figma-reference-scale` (default 2.0).
  - `--figma-reference-output`.

### Update `figma-agent-core/visual_qa.py`
- `VisualQAEngine.run(..., reference_path=None, ast_nodes=None, figma_frame=None)`:
  1. Validate URL/network guard.
  2. Launch Chromium with Playwright (headless=True).
  3. Set viewport exactly to `figma_frame["width"] x figma_frame["height"]` (or CLI viewport).
  4. Inject CSS to disable `transition`, `animation`, `@media (prefers-reduced-motion)`.
  5. Navigate and wait for `networkidle`.
  6. Wait for `document.fonts.ready`.
  7. Wait for all images (`img`, `image`) to have `complete === true` and naturalWidth > 0.
  8. Screenshot full page.
  9. Run DOM assertions from AST.
  10. If reference screenshot exists, compute image diff score.
  11. Run structural layout checks.
- New helpers:
  - `_wait_for_stable_state(page)` — fonts + images + rAF double tick.
  - `_inject_freeze_css(page)`.
  - `_collect_layout_nodes(page, ast_nodes)` — walk AST structural tags (section, header, main, footer, article, div with grid/flex classes) and query their bounding boxes.
  - `_compare_bboxes(page_bboxes, figma_bboxes, tolerance=8)` — match by `data-figma-id` if present, otherwise by heuristic tag + position; report mismatch if dimensions differ by more than tolerance.
  - `_detect_overflow(page)` — for each candidate element, compare `scrollWidth > clientWidth` or `scrollHeight > clientHeight`; skip `overflow: visible` intentional.
  - `_detect_clipped_text(page)` — check if text nodes have `scrollHeight > clientHeight` with `line-height`.
  - `_detect_overlaps(page)` — for non-positioned/static siblings, flag bounding-box overlaps that are not expected (skip `absolute`/`fixed` children).
- Extend `VisualQaReport` with:
  - `layout_checks: List[Dict[str, Any]]`
  - `bbox_comparison: Dict[str, Any]`
  - `font_metrics: Dict[str, Any]`
  - `image_metrics: Dict[str, Any]`

### Update `figma-agent-core/refinement_loop.py`
- Extend `_visual_qa_needs_refinement` to trigger on `layout_checks` failures (overflow, clipped, overlap, bbox mismatch).
- Extend `_apply_layout_adjustments`:
  - Overflow → add `overflow-hidden` or convert `h-full` → `h-auto` / `min-h-0`.
  - Clipped text → add `whitespace-normal`, `break-words`, `line-clamp-3`, or reduce `text-*`.
  - BBox mismatch → add padding/margin classes on the matched node.
  - Overlap → add `flex-col` / `gap-*` or flag `relative` containment.
- Keep deterministic; never use LLM here.

### Update `figma-agent-core/bootstrap.py`
- Ensure compressed nodes keep `absoluteBoundingBox` and `constraints` for structural containers so `visual_qa.py` can compare against Figma bboxes without re-downloading the full document.
- If not already preserved, add `absoluteBoundingBox` to the kept structural fields.

### Agent Specs / Docs
- Update `.agent_loop/tooll_subagents/planning/figma_design_analyst.md` or create `.agent_loop/tooll_subagents/execution/visual_qa_engineer.md` if required by architecture counts (maintain 172 total; prefer updating existing specs).
- Update `.agent_loop/ARCHITECTURE.md` and `.agent_loop/TECHNICAL_ASSIGNMENT.md` to mention `download_figma_reference` stage and structural layout checks.
- Update `CLAUDE.md` memory summary if counts change.

### Tests
- `tests/figma/test_figma_reference_downloader.py`:
  - Mock Figma Images API response, mock polling, verify output file is written.
- `tests/figma/test_visual_qa.py` additions:
  - Viewport set from `figma_frame`.
  - CSS freeze injected.
  - `document.fonts.ready` awaited.
  - Overflow/clipped/overlap detection returns correct reports.
  - BBox comparison with tolerance.
- `tests/figma/test_refinement_loop.py` additions:
  - Refinement triggered by layout check discrepancies.
  - Correct adjustment types generated for overflow/bbox mismatch.
- `tests/figma/test_conductor.py` if exists, or extend existing conductor tests to assert `download_figma_reference` stage is wired.

## Data Flow
```
Figma document
  ↓ bootstrap.py (preserves absoluteBoundingBox for structural nodes)
  ↓ stage_download_figma_reference (Figma Images API → figma_reference.png)
Generated Next.js page
  ↓ stage_visual_qa (real Chromium, stable state, screenshot, diff, layout checks)
  ↓ stage_refinement (if layout discrepancies → deterministic AST adjustments)
  ↓ re-compose + re-visual_qa until passing or max iterations
```

## Acceptance Criteria
- `figma_reference_downloader.py` downloads a PNG from mocked Figma API and saves it to the configured path.
- `conductor.py` has `download_figma_reference` stage after `bootstrap` and passes the path to `visual_qa`.
- `visual_qa.py` sets exact viewport, freezes CSS, waits for fonts/images, and screenshots.
- Structural layout checks detect overflow, clipped text, and bbox mismatch within tolerance.
- `refinement_loop.py` converts layout discrepancies into deterministic AST adjustments.
- `pytest tests/figma tests/mcp -q` remains green.
- Validators 0 errors; graphify updated; memory file written; commit pushed.

## Tracker Tasks
1. Create `figma-agent-core/figma_reference_downloader.py`.
2. Add `stage_download_figma_reference` to `conductor.py` + CLI args.
3. Harden `visual_qa.py` Chromium environment (viewport, fonts, images, CSS freeze).
4. Add structural layout checks to `visual_qa.py`.
5. Integrate layout reports into `refinement_loop.py` adjustments.
6. Add/update tests.
7. Update agent specs and architecture docs.
8. Run tests, validators, graphify, commit and push.
