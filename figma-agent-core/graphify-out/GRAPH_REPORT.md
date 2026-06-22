# Graph Report - figma-agent-core  (2026-06-22)

## Corpus Check
- 26 files · ~36,538 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 715 nodes · 1662 edges · 22 communities (20 shown, 2 thin omitted)
- Extraction: 99% EXTRACTED · 1% INFERRED · 0% AMBIGUOUS · INFERRED: 16 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `a57a4cb5`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]

## God Nodes (most connected - your core abstractions)
1. `FigmaLayoutEngine` - 38 edges
2. `run_pipeline()` - 26 edges
3. `TailwindNode` - 25 edges
4. `_run_command()` - 23 edges
5. `compose_page()` - 20 edges
6. `SemanticIndex` - 20 edges
7. `VisualQAEngine` - 19 edges
8. `SemanticMapper` - 18 edges
9. `RegistryBuilder` - 17 edges
10. `PreciseModeAuditor` - 17 edges

## Surprising Connections (you probably didn't know these)
- `Any` --uses--> `SemanticIndex`  [INFERRED]
  component_registry.py → semantic_matcher.py
- `Any` --uses--> `SemanticMatcher`  [INFERRED]
  component_registry.py → semantic_matcher.py
- `Path` --uses--> `SemanticIndex`  [INFERRED]
  component_registry.py → semantic_matcher.py
- `Path` --uses--> `SemanticMatcher`  [INFERRED]
  component_registry.py → semantic_matcher.py
- `ComponentRegistryError` --uses--> `SemanticIndex`  [INFERRED]
  component_registry.py → semantic_matcher.py

## Import Cycles
- None detected.

## Communities (22 total, 2 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.11
Nodes (24): _arbitrary(), _class_for_color(), _color_to_hex(), convert_figma_node(), FigmaLayoutEngine, _has_alpha(), _hex_to_rgba(), _hex_to_tailwind() (+16 more)

### Community 1 - "Community 1"
Cohesion: 0.08
Nodes (20): ActionGenerator, BackendBridge, BackendSpec, Endpoint, main(), Model, ModelField, OpenApiParser (+12 more)

### Community 2 - "Community 2"
Cohesion: 0.07
Nodes (55): CompletedProcess, _collect_top_level_sections(), main(), Any, Этап 1a: скачивание референсного скриншота Figma-фрейма через Images API., Этап 1b: построение реестра Figma-компонентов (Component Sets, Variants, Instanc, Этап 1c: аудит готовности Precise Mode перед генерацией кода., Этап 2: анализ структуры Figma. (+47 more)

### Community 3 - "Community 3"
Cohesion: 0.05
Nodes (42): ComponentMapper, ComponentRegistry, ComponentRegistryError, _extract_exports_and_props(), _find(), InstanceEntry, _is_component(), _is_component_set() (+34 more)

### Community 4 - "Community 4"
Cohesion: 0.10
Nodes (48): _apply_component_mappings(), _build_form_hooks(), _build_handler(), _build_state_hooks(), _class_string(), _collect_all_nodes(), _collect_fonts(), _collect_validated_forms() (+40 more)

### Community 5 - "Community 5"
Cohesion: 0.09
Nodes (24): _asset_dest_path(), AssetDownloader, AssetExtractor, AssetOptimizer, AssetPipeline, _extract_box_size(), FontCollector, InlineSvgExtractor (+16 more)

### Community 6 - "Community 6"
Cohesion: 0.12
Nodes (31): _assign_component_names(), _class_string(), _collect_all_nodes(), _collect_substantial_nodes(), ComponentExtractor, ComponentGenerator, _detect_font_imports(), ExtractedComponent (+23 more)

### Community 7 - "Community 7"
Cohesion: 0.08
Nodes (30): _download_assets_for_context(), FigmaAgent, _inject_asset_paths(), main(), _maybe_bootstrap(), Any, Path, Рекурсивно добавляет publicPath в ассет-ноды для передачи в LLM. (+22 more)

### Community 8 - "Community 8"
Cohesion: 0.22
Nodes (19): _build_match_index(), compose_responsive_ast(), constraint_to_classes(), detect_breakpoint_frames(), _diff_classes(), _find_figma_node(), _load_json(), main() (+11 more)

### Community 9 - "Community 9"
Cohesion: 0.16
Nodes (11): DomAssertion, _expected_nodes_from_ast(), _is_allowed_url(), main(), Any, Path, Извлекает минимальные DOM-assertions из Tailwind AST., run_visual_qa() (+3 more)

### Community 10 - "Community 10"
Cohesion: 0.15
Nodes (19): cache_age_minutes(), check_figma_connection(), extract_effects(), extract_fills(), extract_text_style(), FigmaExtractor, find_node_by_id(), load_existing_cache() (+11 more)

### Community 11 - "Community 11"
Cohesion: 0.18
Nodes (27): _apply_component_mappings(), _apply_slot(), _assign_prop_names(), build_content_model(), _build_data_code(), _build_page_code(), _class_string(), _collect_all_nodes() (+19 more)

### Community 12 - "Community 12"
Cohesion: 0.21
Nodes (10): _box_area(), _boxes_overlap(), CheckResult, find_node_by_id(), load_figma_json(), main(), PreciseModeAuditor, _px() (+2 more)

### Community 13 - "Community 13"
Cohesion: 0.23
Nodes (19): _apply_layout_adjustments(), _check_reason(), _extract_figma_id(), _find_node_by_figma_id(), _load_json(), _load_module(), main(), Any (+11 more)

### Community 14 - "Community 14"
Cohesion: 0.26
Nodes (16): check_file(), _check_import_path_safety(), _check_patterns(), _check_placeholders(), _check_project_rules(), ComplianceReport, _extract_text_literals(), _is_inside_workspace() (+8 more)

### Community 15 - "Community 15"
Cohesion: 0.27
Nodes (18): _attach_interactions(), _build_interaction(), _camel_case(), _collect_routes(), _extract_navigation_info(), _extract_overlay_info(), _extract_reaction_type(), _extract_url_info() (+10 more)

### Community 16 - "Community 16"
Cohesion: 0.25
Nodes (9): download_figma_reference(), FigmaReferenceDownloader, main(), _parse_file_key(), Any, Path, Скачивает референсный скриншот Figma-фрейма через Figma Images API., _resolve_image_url() (+1 more)

### Community 17 - "Community 17"
Cohesion: 0.13
Nodes (27): find_node_by_id(), get_node_details(), inspect_node(), list_top_level_nodes(), load_figma_json(), main(), Any, Собирает краткую статистику по дереву. (+19 more)

### Community 18 - "Community 18"
Cohesion: 0.17
Nodes (11): 1. Установка зависимостей, 2. Настройка окружения, 3. Запуск полного пайплайна, Figma Agent Core, Безопасность, Быстрый старт, Дизайн-токены и ассеты, Работа с конкретной секцией (+3 more)

### Community 19 - "Community 19"
Cohesion: 0.50
Nodes (7): _ensure_dotenv(), FigmaConfig, is_figma_configured(), load_figma_config(), require_figma_config(), _resolve_file_key(), _resolve_node_id()

## Knowledge Gaps
- **15 isolated node(s):** `Response`, `CompletedProcess`, `Path`, `Path`, `run.sh script` (+10 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Are the 2 inferred relationships involving `Any` (e.g. with `SemanticIndex` and `SemanticMatcher`) actually correct?**
  _`Any` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Превращает произвольное имя Figma-ноды в валидное PascalCase-имя компонента.`, `Если JSON-контекст отсутствует и есть токен с URL, автоматически запускает boots`, `Находит isAsset ноды в текущем контексте, запрашивает URL'ы и скачивает ассеты в` to the rest of the system?**
  _114 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.11259920634920635 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.07978142076502732 - nodes in this community are weakly interconnected._
- **Should `Community 2` be split into smaller, more focused modules?**
  _Cohesion score 0.06883116883116883 - nodes in this community are weakly interconnected._
- **Should `Community 3` be split into smaller, more focused modules?**
  _Cohesion score 0.053776079929473995 - nodes in this community are weakly interconnected._
- **Should `Community 4` be split into smaller, more focused modules?**
  _Cohesion score 0.1036734693877551 - nodes in this community are weakly interconnected._