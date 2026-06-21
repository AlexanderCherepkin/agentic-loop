# Figma Components + Variants — Plan V1

## Vision
Move from pattern/duplicate-based component extraction to real Figma component semantics. Build a **Component Registry** pre-processor that understands Figma `COMPONENT_SET`, `COMPONENT`, `INSTANCE`, `variantProperties`, `componentSetId`, `componentId`, and `overrides`. Generate one strict TypeScript React component per Component Set, and render instances as typed JSX with smart overrides.

## V1 Scope
Supported:
- `COMPONENT_SET` nodes with `variantProperties`.
- `COMPONENT` variants inside a Component Set.
- `INSTANCE` nodes referencing a Component Set or a standalone Component.
- `variantProperties` overrides on instances.
- Text and node (icon/illustration) overrides.
- Nested component dependencies (one generated component uses another).

Out of V1 scope:
- Complex style overrides beyond color, text, visibility, and icon-swap.
- Interactive component variants beyond prop-driven selection.
- External Figma library components (tagged as `library` but not downloaded/defined in V1).

## Output Artifacts
- `component_registry.json` — mapping: `componentSetId`/`componentId` → metadata, variants, default variant, props interface, file path, dependency list.
- `src/components/ui/{PascalName}.tsx` — library/ui components generated from Figma Component Sets and standalone Components.
- `src/app/components/{PascalName}.tsx` — page-local feature components (fallback pattern-based extraction preserved).
- `src/types/components.ts` (optional V1) — shared TypeScript interfaces if multiple sets share props.

## Architecture

### New Core Module: `figma-agent-core/component_registry.py`
- `ComponentRegistry` dataclass.
- `RegistryBuilder.build(document)`:
  1. Recursively walk the Figma document.
  2. Collect `COMPONENT_SET` nodes and their child `COMPONENT` variants.
  3. Collect standalone `COMPONENT` nodes (not inside a Set).
  4. Collect `INSTANCE` nodes and map them to `componentSetId`/`componentId`.
  5. Build variant property metadata: prop name → type (enum of variant values), default value.
  6. Detect nested dependencies: a Component Set/Component contains `INSTANCE` nodes referencing other Component Sets/Components.
  7. Validate DAG; break cycles by treating cyclic refs as opaque children and emit warning.
  8. Write `component_registry.json`.
- Helpers: `_is_component_set`, `_is_component`, `_is_instance`, `_extract_variant_properties`, `_extract_overrides`, `_name_to_pascal`.

### Update `figma-agent-core/bootstrap.py`
- Preserve `componentSetId`, `componentId`, `variantProperties`, and `overrides` during compression.
- Ensure `is_structural` includes `COMPONENT_SET`.
- Do not flatten variant children of `COMPONENT_SET` prematurely; keep their structure.

### Update `figma-agent-core/layout_engine.py`
- After layout AST is built, load `component_registry.json`.
- When processing `INSTANCE` nodes:
  - If mapped to a Component Set → tag with `component_set_id`, `variant_props`, `overrides`, `component_ref: "<PascalName>"`, `is_instance: True`.
  - If mapped to a standalone Component → tag with `component_id`, `component_ref`, `is_instance: True`.
- Preserve override children as extra `TailwindNode` children under the instance node so `page_composer` can render them as JSX children/props.
- For nodes that are *inside* a Component Set variant during page layout, keep them in the AST but mark `component_context` so `page_composer` can skip them at page level if needed.

### Refactor `figma-agent-core/component_extractor.py`
- Introduce `ComponentGenerator` alongside the existing pattern-based extractor.
- `generate_from_registry(registry, layout_ast)`:
  1. Topologically sort Component Sets/Components by dependency DAG.
  2. For each Component Set:
     - Generate `src/components/ui/{PascalName}.tsx`.
     - Generate TypeScript interface from `variantProperties`.
     - Render default variant structure by running the layout AST of the Component Set's children through `page_composer`-like logic.
     - Apply variant conditional className/logic for differences between variants (V1: layout/style differences; structural differences rendered as small conditional branches if limited).
  3. For standalone Components → generate single `src/components/ui/{PascalName}.tsx`.
- `_generate_component_source(name, entry, layout_ast)`:
  - React import.
  - `export interface {Name}Props { ... }`.
  - Body: return JSX with `{children}` slots for overrides.
- Keep old `_extract_by_pattern` as fallback for non-registry components in `src/app/components/`.

### Dependency DAG Resolver
- Implemented inside `component_registry.py` (or split to `figma-agent-core/dependency_graph.py` if it grows).
- `build_dependency_graph(registry)` → adjacency list.
- `topological_sort(graph)` → ordered list for bottom-up generation.
- Cycle handling: detect, warn, break edge, render cyclic reference as opaque `div`.

### File Organization
- Library components: `src/components/ui/{PascalName}.tsx`.
- Feature/page-local components: `src/app/components/{PascalName}.tsx`.
- Shared interfaces: `src/types/components.ts` (V1 optional).

### Update `figma-agent-core/page_composer.py`
- `_node_to_tsx` for instance nodes:
  - Import generated component from `src/components/ui/{Name}` (deduplicated at file top).
  - Render `<{Name} variant="..." ...overrides />`.
  - Map `variantProperties` to props.
  - Map text overrides to string props.
  - Map icon/node overrides to JSX children or typed prop.
- For nodes with old `component: True` → keep existing behavior.

### Integration into Pipeline
- `conductor.py`:
  - New stage `component_registry` after `bootstrap` and before `layout`.
  - `stage_layout` loads registry and tags instances.
  - Rename `stage_extract_components` → `stage_generate_components`: generates `src/components/ui/*.tsx` from registry.
  - `stage_compose` renders instances as typed JSX.
- New CLI args: `--component-registry`, `--components-output-dir`, `--components-types-dir`.

### MCP Server
- `mcp_servers/figma_server.py`:
  - New tool `figma_build_component_registry` — accepts `file_key`/`node_id` → writes `component_registry.json`.
  - Update `figma_extract_components` to use registry-aware generator.
  - Update `figma_run_pipeline` to include the registry stage.

### Agent Specs
- New `.agent_loop/tooll_subagents/planning/component_registry.md` — Algorithmic template for the registry builder agent.
- Update `.agent_loop/tooll_subagents/planning/figma_design_analyst.md` to include Component Sets/Variants in `design_blueprint`.
- Update `.agent_loop/tooll_subagents/planning/design_to_code_planner.md` to include `component_registry.json`, `src/components/ui/`, and dependency DAG in `handoff_package`.
- Update `.agent_loop/tooll_subagents/planning/tool_plan_selection.md` to include `figma_build_component_registry`.
- Update `.agent_loop/ARCHITECTURE.md` and `.agent_loop/TECHNICAL_ASSIGNMENT.md` counts and pipeline description.

### Tests
- `tests/figma/fixtures/component_set.json` — Figma document with `COMPONENT_SET`, two variants, and an `INSTANCE` with overrides.
- `tests/figma/test_component_registry.py`:
  - **Extract test**: registry contains correct `componentSetId`, variants, default variant, props.
  - **Dependency test**: DAG correctly orders nested components.
- `tests/figma/test_component_generator.py`:
  - **Generate test**: generated `Button.tsx` contains TypeScript interface and conditional variant classes.
  - **Build test**: generated file passes `tsc --noEmit` and project `eslint` syntax-level.
- `tests/figma/test_layout_engine_components.py`:
  - Layout tags instances with `component_ref` and `variant_props`.
- `tests/figma/test_page_composer_components.py`:
  - Compose renders `<Button variant="primary" label="Click" />` from an instance node.
- `tests/mcp/test_figma_server.py`: update tool counts and add registry tool test.

## Data Flow
```
Figma document
  ↓ bootstrap.py (preserves componentSetId, variantProperties, overrides)
  ↓ component_registry.py (builds registry + DAG)
component_registry.json
  ↓ layout_engine.py (tags INSTANCE nodes with component_ref + props)
layout_ast.json
  ↓ component_generator.py (topologically generates src/components/ui/*.tsx)
  ↓ page_composer.py (renders instances as typed JSX)
src/components/ui/*.tsx + page.tsx
```

## Acceptance Criteria
- `component_registry.py` on the fixture produces `component_registry.json` with ≥1 component set, correct variants, and no missing component refs.
- Layout engine tags instances with `component_ref` matching registry names.
- `ComponentGenerator` produces a React component file that:
  - Exports a named component.
  - Has a TypeScript interface derived from `variantProperties`.
  - Renders the default variant structure.
  - Compiles with `tsc --noEmit` and passes project `eslint`.
- DAG resolver correctly orders nested components; no component imports an undefined component.
- `page_composer.py` renders an instance as `<ComponentName ...props />` with all mapped props.
- `pytest tests/figma tests/mcp -q` remains green; existing tests do not regress.
- Validators: `validate_consistency.js` 0 errors, `validate_cross_references.js` 0 broken links.
- `graphify update .` executed.

## Tracker Tasks
1. Create `figma-agent-core/component_registry.py` with registry builder + DAG resolver.
2. Update `bootstrap.py` to preserve component/variant metadata.
3. Update `layout_engine.py` to tag instances from registry.
4. Refactor `component_extractor.py` → add `ComponentGenerator` with TypeScript props generation.
5. Update `page_composer.py` to render instance nodes as typed JSX.
6. Add tests: registry, generator, layout, composer, dependency, build.
7. Update `conductor.py` pipeline + CLI args.
8. Update `mcp_servers/figma_server.py` with registry tool.
9. Create/update agent specs and architecture docs.
10. Add memory file + run validators + update graphify.
