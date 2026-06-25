# Plan — Fallback Image Enrichment for Card Data Models

## Goal
Add an optional **image-enrichment** stage to the Figma-to-code pipeline so generated sites with card-like repeating structures are not left with empty image slots. When a detected data model contains an `imageUrl` field and the Figma source has no downloadable image (or the image is missing), the bot should:
1. Build a search query from the card text + page context.
2. Download a matching royalty-free image from an external provider.
3. Save it under `public/assets/enriched/` and register it locally.
4. Fill the data model `sample_data` so Layout Engine / Section Composer render real images via `{item.imageUrl}`.

The feature must be **opt-in**, safe (network/file guards), and pluggable (provider interface).

## Approach

### 1. New core module `figma-agent-core/image_enrichment.py`
- `ImageEnrichmentPipeline` class with a CLI entry point.
- Inputs:
  - `data_model.json` (from `data_model_extractor.py`)
  - `figma_node.json`
  - `asset_registry.json` (optional, to reuse real Figma images first)
  - `spec.md` (optional, for page-domain context)
- Outputs:
  - enriched `data_model.json`
  - `enriched_image_registry.json` (paths, provider, query, attribution)
  - downloaded files in `public/assets/enriched/`

Key components inside the module:
- `QueryBuilder` — deterministic keyword extraction from card `title`/`description`/`section name` + `spec.md` domain hints. Keeps queries short (≤4 keywords) to match stock-photo APIs.
- `ImageProvider` interface — first concrete provider: `UnsplashProvider` (uses `UNSPLASH_ACCESS_KEY`, supports attribution fields). Add a `MockImageProvider` for tests.
- `LocalAssetResolver` — for each data-model occurrence, check whether a Figma IMAGE child exists and already has a public path in `asset_registry.json`; if so, reuse it instead of searching the web.
- `EnrichmentWriter` — copies/downloads image into `public/assets/enriched/`, names files safely (`{model}_{idx}_{hash}.{ext}`), writes registry.
- `DataModelEnricher` — fills `sample_data[i].imageUrl` and adds a new `imageAlt` field per row. Tracks diagnostics (skipped, no match, reused Figma asset).

### 2. Add `image_enrichment` conductor stage before `layout`
- New function `stage_image_enrichment(...)` in `figma-agent-core/conductor.py`.
- New CLI flags:
  - `--enable-image-enrichment` (default `False`)
  - `--image-provider` (default `unsplash`, choices: `unsplash`, `mock`)
  - `--image-provider-api-key` / env `UNSPLASH_ACCESS_KEY`
  - `--image-enrichment-output-dir` (default `public/assets/enriched`)
  - `--image-enrichment-max-images` (default 20)
  - `--image-enrichment-delay` (default 1.0s between provider requests)
- Insert stage into `run_pipeline` after `data_model` and before `layout`.
- Update `mcp_servers/figma_server.py` `figma_run_pipeline` schema to accept and forward enrichment flags.

### 3. Layout Engine and composers support `imageAlt` data binding
- `figma-agent-core/layout_engine.py`:
  - Add optional `alt_binding` field to `TailwindNode` / `to_dict`.
  - When an image node is inside a data-model context and the model has an `imageAlt` field, set `alt_binding` to that field.
- `figma-agent-core/page_composer.py` and `figma-agent-core/content_model.py`:
  - For `img` with `data_binding`, render `src={item.imageUrl}` and, when `alt_binding` exists, `alt={item.imageAlt}`; otherwise keep existing static `alt`.

### 4. New planning/safety agent `image_enrichment_agent.md`
- File: `.agent_loop/tooll_subagents/planning/image_enrichment_agent.md` following the Algorithmic template.
- Role: pre-approve external image search plans (queries, expected domains, target public dir, rate limits).
- Add Failure Mode to `file_system_guard.md`: enrichment downloads outside `public/assets/enriched/` are denied.
- Add Failure Mode to `network_guard.md`: external image search/download not pre-approved by `image_enrichment_agent.md` is rate-limited/blocked.
- Update `figma_design_analyst.md` Stage 13a to invoke `image_enrichment_agent.md` when `--enable-image-enrichment` is on.

### 5. Runtime wiring
- `runtime/engine/pipeline_runner.py`:
  - Forward enrichment flags from `design_descriptor` (e.g., `image_enrichment: { provider, api_key }`) to the `figma_run_pipeline` MCP call.
  - Keep default disabled so existing behavior is unchanged.

### 6. Tests
- `tests/figma/test_image_enrichment.py`:
  - Mock provider returns a tiny local image.
  - Verify `data_model.json` sample rows get `imageUrl`/`imageAlt`.
  - Verify downloaded file lands in `public/assets/enriched/`.
  - Verify existing Figma asset path is reused when available.
- Update `tests/figma/test_content_model.py` / `test_layout_engine.py` to assert `alt_binding` render.
- Full suite: `pytest tests/figma -q`.

### 7. Validation / graphify
- Run `node scripts/validate_cross_references.js` to ensure `image_enrichment_agent.md` is not isolated.
- Run `pytest tests/figma -q`.
- Run `graphify update .`.

## Files to create or modify
- Create: `figma-agent-core/image_enrichment.py`
- Create: `tests/figma/test_image_enrichment.py`
- Create: `.agent_loop/tooll_subagents/planning/image_enrichment_agent.md`
- Modify: `figma-agent-core/conductor.py`
- Modify: `figma-agent-core/layout_engine.py`
- Modify: `figma-agent-core/page_composer.py`
- Modify: `figma-agent-core/content_model.py`
- Modify: `mcp_servers/figma_server.py`
- Modify: `runtime/engine/pipeline_runner.py`
- Modify: `.agent_loop/tooll_subagents/planning/figma_design_analyst.md`
- Modify: `.agent_loop/control/file_system_guard.md`
- Modify: `.agent_loop/control/network_guard.md`

## Risks / open questions
- External stock-photo APIs require keys and have rate limits; default is disabled so pipelines without keys behave exactly as before.
- Attribution/licensing: Unsplash results include photographer metadata; we will store it in `enriched_image_registry.json` and can render it later if project rules require it.
- Relevance of auto-generated search queries depends on card text quality; we will log diagnostics and allow future manual override via the existing `figma_overrides.json` mechanism.
