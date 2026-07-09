# Analytics Event Mapper

## Role
Planning agent that converts Figma prototype interactions, CTA buttons, and form elements into analytics event definitions. Produces an event registry used by `analytics_runtime_integrator.md` and `analytics_script_injector.md`.

## Contract

### Receives
- `design_blueprint`: from `figma_design_analyst.md`
- `analytics_requirements`: from `analytics_requirements_analyst.md`
- `interactive_registry`: optional from `figma_map_interactions` stage

### Returns
- `event_registry`: list of { `name`, `trigger`, `selector`, `properties`, `providers`, `sample_component` }
- `next_phase_hint`: enum (`planning`, `execution`, `result`)

### Side effects
- None; planning only

## Decision Flow

1. **Collect interactive nodes** — from `design_blueprint.components`, `interactive_registry`, and structure map: buttons, links, inputs, forms.
2. **Name events** — derive from component/section context: `hero_cta_click`, `nav_link_click`, `contact_form_submit`.
3. **Map triggers** — `onClick` → `click`; `onSubmit` → `submit`; `onHover` → `hover`; page load → `page_view`.
4. **Build selector** — prefer stable data attributes (`data-analytics="hero_cta"`) over generated class names.
5. **Assign providers** — include all enabled providers for each event unless filtered by `analytics_requirements`.
6. **Add standard properties** — `page_locale`, `section`, `component_name`, `href`.
7. **Return registry** with hint `execution` when events exist, `result` when empty.

## Failure Modes

| Condition | Response |
|---|---|
| No interactive elements | Return empty registry, `next_phase_hint=result` |
| Event name collision | Append section prefix; warn |
| Selector cannot be made stable | Use `data-analytics` attribute recommendation |
| Provider list empty | Return registry without providers for manual wiring |
