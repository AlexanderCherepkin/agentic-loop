# Preview Runtime Integrator

## Role
Execution agent that runs the client preview and approval workflow for a generated Next.js site using `runtime/preview/PreviewEngine`. Captures screenshot, builds preview report, and collects client feedback.

## Contract

### Receives
- `preview_requirements`: from `tooll_subagents/planning/preview_planner.md`
- `target_dir`: str — project workspace root
- `visual_qa_report`: optional report from `tools_browser/headless_automation/visual_qa_agent.md`
- `safe_component_manifest`: optional list of generated safe components from `design_to_code_planner.md`

### Returns
- `preview_integration_report`: dict — {
  - `status`: str
  - `page_url`: str | None
  - `screenshot_path`: str | None
  - `preview_html_path`: str | None
  - `feedback_file_path`: str | None
  - `approved`: bool | None
  - `can_refine`: bool
  - `refinement_hints`: list[str]
  - `errors`: list[dict[str, Any]]
  - `notes`: list[str]
  - `next_phase_hint`: enum (`observability`, `execution`, `result`)
}

### Side effects
- May start a local Next.js dev server and capture screenshot.
- Writes preview artifacts to `preview_requirements.output_dir`.
- Logs to `safety-control/mutual_check/audit_logger.md`.

## Decision Flow

1. **Validate target directory** — ensure `target_dir` contains the generated site directory referenced by `preview_requirements.site_dir`.
2. **Check network and file-system guards** — local dev server must be allowed; if blocked, use `page_url` or escalate to `human_approval.md`.
3. **Build config** — create `PreviewConfig` from `preview_requirements`.
4. **Run PreviewEngine** — invoke `runtime/preview/PreviewEngine(target_dir, config).run()`.
5. **Handle feedback** — if `approved=false`, pass `refinement_hints` to `plan_adjustment.md`; if `approved=true`, hint `result`.
6. **Return integration report** with hint `observability` when awaiting feedback, `result` when approved or skipped.

## Failure Modes

| Condition | Response |
|---|---|
| Generated site directory not found | Return error, `next_phase_hint=result`; log to `audit_logger.md` |
| Dev server start fails | `status=blocked`; route to `plan_adjustment.md` |
| Screenshot capture fails | Continue; report missing screenshot |
| Feedback indicates rejection | `can_refine=true`; route to `plan_adjustment.md` |
| Network guard blocks external URLs in screenshot | Restrict `allowed_domains`; retry once |
