# Plan — Content and Code Separation (Page/Section/Data Models)

## Goal
Extend the existing Content Model stage so generated sites separate structure, content, and data models:
1. Emit a `content_model.json` describing each section with typed fields (heading, subtitle, CTA text, CTA link, image).
2. Render the page from an array of sections imported from a data file.
3. Add a `data_model_extractor.py` that proposes JSON/Prisma models for repeating Figma structures (cards, nav links, authors).
4. Add data-binding annotations in the Layout Engine so JSX can read from a data model instead of hard-coded text.

## Approach

### 1. Enrich `content_model.py`
- Extend `_find_content_slots` to classify slots by role:
  - `heading` for `h1`/`h2` text.
  - `subtitle` for `h3`/`h4`/`p` text inside a section header.
  - `ctaText` for `button`/`a` text.
  - `ctaHref` for `a href` / `button` target (if available in `interactive.triggers`).
  - `image` for `img src`.
  - Fallback generic `textN`/`srcN` for other slots.
- Update `_section_component_code` to generate a typed props interface with all extracted fields, and render `{props.heading}` / `{props.image}` etc.
- Update `_build_data_code` to export `pageData` plus a `sections` array ordered list: `sections: [{ name: "Hero", component: "Hero" }, ...]`.
- Add `_build_content_model_json` producing `content_model.json`:
  ```json
  {
    "version": "1",
    "sections": [
      {
        "name": "Hero",
        "slug": "hero",
        "component": "Hero",
        "fields": [
          { "name": "heading", "type": "text", "label": "Heading", "required": true },
          { "name": "subtitle", "type": "text", "label": "Subtitle" },
          { "name": "ctaText", "type": "text", "label": "CTA Text" },
          { "name": "ctaHref", "type": "url", "label": "CTA Link" },
          { "name": "image", "type": "image", "label": "Image" }
        ]
      }
    ]
  }
  ```
- Add new CLI arg `--content-model-output` default `content_model.json` and pass it through `conductor.py`.
- Change `_build_page_code` to render the page by mapping over `pageData.sections`:
  ```tsx
  import { pageData, sections } from "./page.data";
  import Hero from "@/app/sections/Hero";
  // ...
  {sections.map((s) => {
    const Component = { Hero, Features, ... }[s.component];
    return <Component key={s.slug} {...pageData[s.component]} />;
  })}
  ```
  Keep per-section imports for type safety and tree-shaking.

### 2. New module `figma-agent-core/data_model_extractor.py`
- Input: raw `figma_node.json` (or any node tree JSON).
- Detect repeating subtrees using a structural fingerprint:
  - Include node type, name base, visible child count, and primitive child types.
  - Group identical fingerprints; require `min_occurrences=2`.
- Heuristic model naming from the common ancestor or first occurrence name:
  - `Card` → `FeatureCard`, `PricingCard`, etc.
  - `Link` / `Nav` → `NavLink`.
  - `Author` / `Team` → `Author`, `TeamMember`.
- Propose fields by inspecting leaf text and image nodes inside the repeated structure:
  - Text children → `title`, `description` (by tag/position).
  - Image nodes → `imageUrl`.
  - Link-like nodes → `href`.
- Output JSON report:
  ```json
  {
    "models": [
      {
        "name": "NavLink",
        "occurrences": 5,
        "sample_figma_id": "123:1",
        "fields": [
          { "name": "label", "type": "String" },
          { "name": "href", "type": "String" }
        ],
        "suggested_prisma": "model NavLink { id String @id @default(uuid()) label String href String }"
      }
    ]
  }
  ```
- Provide CLI: `--file`, `--output`, `--min-occurrences`, `--top-n`.
- Add minimal unit tests in `tests/figma/test_data_model_extractor.py`.

### 3. Layout Engine data-binding fields
- Add optional `--data-model` argument to `layout_engine.py`. When provided, the engine reads `data_model.json` (or the extractor output) to annotate matching nodes.
- In `TailwindNode` add `data_binding: Optional[Dict[str,str]]` with keys:
  - `model` — e.g. `NavLink`
  - `field` — e.g. `label`
  - `index` — for list rendering
- When a Figma node name or path matches a data model pattern, the Layout Engine:
  - Sets `text_expr` / `src_expr` to reference the data field instead of literal text/src.
  - Marks the parent list container with `data_source={model}` and `data_is_list=True`.
- Update `content_model.py` `_render_node` to understand `text_expr`, `src_expr`, and `data_source`.
- Update `page_composer.py` `_node_to_tsx` so it can render `{item.label}` inside a list map if data binding is present (fallback to hard-coded text when no binding).

### 4. Conductor integration
- Add new stage `data_model` after `analyze` (optional) and pass output to `layout` via `--data-model`.
- Extend `stage_content_model` to accept and forward `--content-model-output`.
- Add config keys:
  - `content_model_json_output`
  - `data_model_enabled`
  - `data_model_output`
  - `data_model_min_occurrences`

### 5. Tests
- `tests/figma/test_content_model.py`:
  - typed field extraction (heading/cta/image)
  - `content_model.json` output
  - page.tsx renders `sections.map`
- New `tests/figma/test_data_model_extractor.py`:
  - detect repeated cards and nav links
  - suggested model names and fields
- `tests/figma/test_layout_engine.py`:
  - data-binding annotations when `--data-model` provided

## Files to create or modify
- Create: `figma-agent-core/data_model_extractor.py`
- Create: `tests/figma/test_data_model_extractor.py`
- Modify: `figma-agent-core/content_model.py`
- Modify: `figma-agent-core/layout_engine.py`
- Modify: `figma-agent-core/page_composer.py` (data-binding render)
- Modify: `figma-agent-core/conductor.py` (stage wiring and config)
- Modify: `tests/figma/test_content_model.py`
- Modify: `tests/figma/test_layout_engine.py`

## Validation
1. Run `pytest tests/figma -q` — target: all pass, current 251 + new tests.
2. Run `node scripts/safety_check.js` on changed files.
3. Run `graphify update .` to refresh knowledge graph.

## Risks / open questions
- Page rendering as `sections.map` loses static import tree-shaking if components dictionary is not statically analyzable; using a static switch/import block preserves it.
- Data model matching heuristics may be noisy; we will keep it optional and provide a confidence score in the extractor report.
