import os
import sys
import json
import time
import logging
import argparse
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from dotenv import load_dotenv

import analyzer


load_dotenv()


logger = logging.getLogger("conductor")


def _setup_logging(log_file: str = "conductor.log", verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def _run_command(command: List[str], timeout: int = 600) -> subprocess.CompletedProcess:
    """Запускает subprocess и логирует результат.

    Если скрипт не найден относительно рабочей директории, но существует
    рядом с conductor.py (в figma-agent-core), подставляет полный путь.
    """
    if len(command) >= 2 and command[1].endswith(".py"):
        script = Path(command[1])
        if not script.exists() and not script.is_absolute():
            candidate = Path(__file__).parent / script.name
            if candidate.exists():
                command[1] = str(candidate)
    logger.info(f"Running: {' '.join(command)}")
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.stdout:
            for line in result.stdout.splitlines():
                logger.info(line)
        if result.stderr:
            for line in result.stderr.splitlines():
                logger.warning(line)
        if result.returncode != 0:
            logger.error(f"Command failed with exit code {result.returncode}: {' '.join(command)}")
        else:
            logger.info(f"Command succeeded: {' '.join(command)}")
        return result
    except subprocess.TimeoutExpired:
        logger.error(f"Command timed out after {timeout}s: {' '.join(command)}")
        raise
    except Exception as e:
        logger.error(f"Command error: {e}")
        raise


def stage_bootstrap(
    force_refresh: bool = False,
    node_id: Optional[str] = None,
    api_depth: int = 2,
    dry_run: bool = False,
) -> bool:
    """Этап 1: загрузка данных из Figma API."""
    logger.info("=== STAGE: bootstrap ===")
    command = [sys.executable, "bootstrap.py", "--api-depth", str(api_depth)]
    if force_refresh:
        command.append("--force")
    if node_id:
        command.extend(["--node-id", node_id])

    if dry_run:
        logger.info(f"[DRY-RUN] Would run: {' '.join(command)}")
        return True

    result = _run_command(command, timeout=300)
    return result.returncode == 0


def stage_download_figma_reference(
    file_key: Optional[str] = None,
    url: Optional[str] = None,
    node_id: Optional[str] = None,
    output: str = ".tmp/browser/figma_reference.png",
    scale: float = 2.0,
    dry_run: bool = False,
) -> bool:
    """Этап 1a: скачивание референсного скриншота Figma-фрейма через Images API."""
    logger.info("=== STAGE: download_figma_reference ===")
    if not node_id:
        logger.warning("download_figma_reference requires --figma-reference-node-id. Skipping.")
        return False

    command = [
        sys.executable,
        "figma_reference_downloader.py",
        "--node-id", node_id,
        "--output", output,
        "--scale", str(scale),
    ]
    if file_key:
        command.extend(["--file-key", file_key])
    if url:
        command.extend(["--url", url])

    if dry_run:
        logger.info(f"[DRY-RUN] Would run: {' '.join(command)}")
        return True

    result = _run_command(command, timeout=120)
    return result.returncode == 0


def stage_component_registry(
    file: str = "figma_node.json",
    output: str = "component_registry.json",
    mapper_output: str = "figma_component_map.json",
    node_id: Optional[str] = None,
    scan_dirs: Optional[List[str]] = None,
    semantic_threshold: float = 0.5,
    override_path: str = ".agent_loop/figma_overrides.json",
    dry_run: bool = False,
) -> bool:
    """Этап 1b: построение реестра Figma-компонентов (Component Sets, Variants, Instances, DAG)."""
    logger.info("=== STAGE: component_registry ===")
    command = [sys.executable, "component_registry.py", "--file", file, "--output", output, "--mapper-output", mapper_output, "--semantic-threshold", str(semantic_threshold), "--override-path", override_path]
    if node_id:
        command.extend(["--node-id", node_id])
    for d in scan_dirs or []:
        command.extend(["--scan-dir", d])

    if dry_run:
        logger.info(f"[DRY-RUN] Would run: {' '.join(command)}")
        return True

    result = _run_command(command, timeout=120)
    return result.returncode == 0


def stage_data_model(
    file: str = "figma_node.json",
    node_id: Optional[str] = None,
    output: str = "data_model.json",
    min_occurrences: int = 2,
    top_n: int = 10,
    dry_run: bool = False,
) -> bool:
    """Этап 1d: обнаружение повторяющихся Figma-структур и предложение JSON/Prisma моделей данных."""
    logger.info("=== STAGE: data_model ===")
    command = [
        sys.executable,
        "data_model_extractor.py",
        "--file", file,
        "--output", output,
        "--min-occurrences", str(min_occurrences),
        "--top-n", str(top_n),
    ]
    if node_id:
        command.extend(["--node-id", node_id])

    if dry_run:
        logger.info(f"[DRY-RUN] Would run: {' '.join(command)}")
        return True

    result = _run_command(command, timeout=120)
    return result.returncode == 0


def stage_image_enrichment(
    data_model_file: str = "data_model.json",
    figma_file: str = "figma_node.json",
    spec_file: str = "spec.md",
    public_dir: str = "public",
    assets_registry_file: str = "asset_registry.json",
    provider: str = "unsplash",
    provider_api_key: Optional[str] = None,
    output_dir: str = "public/assets/enriched",
    max_images: int = 20,
    skip_existing: bool = True,
    dry_run: bool = False,
) -> bool:
    """Этап 1d-enrich: подбор изображений для data_model-карточек без картинок."""
    logger.info("=== STAGE: image_enrichment ===")
    # Если выбран Unsplash, но ключа нет, автоматически переключаемся на
    # бесплатный генеративный провайдер Pollinations, чтобы не падать.
    effective_provider = provider
    if effective_provider == "unsplash" and not (provider_api_key or os.environ.get("UNSPLASH_ACCESS_KEY")):
        logger.info("[IMAGE-ENRICH] No Unsplash API key found; falling back to Pollinations AI provider")
        effective_provider = "pollinations"
    asset_registry_path = Path(public_dir) / assets_registry_file
    command = [
        sys.executable,
        "image_enrichment.py",
        "--data-model", data_model_file,
        "--figma-file", figma_file,
        "--spec-file", spec_file,
        "--output", data_model_file,
        "--provider", effective_provider,
        "--output-dir", output_dir,
        "--max-images", str(max_images),
    ]
    if asset_registry_path.exists():
        command.extend(["--asset-registry", str(asset_registry_path)])
    if provider_api_key and effective_provider == "unsplash":
        command.extend(["--provider-api-key", provider_api_key])
    if not skip_existing:
        command.append("--no-skip-existing")

    if dry_run:
        logger.info(f"[DRY-RUN] Would run: {' '.join(command)}")
        return True

    result = _run_command(command, timeout=300)
    return result.returncode == 0


def stage_precise_mode_audit(
    file: str = "figma_node.json",
    node_id: Optional[str] = None,
    target_viewport: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Этап 1c: аудит готовности Precise Mode перед генерацией кода."""
    logger.info("=== STAGE: precise_mode_audit ===")
    command = [sys.executable, "precise_mode_auditor.py", "--file", file]
    if node_id:
        command.extend(["--node-id", node_id])
    if target_viewport:
        command.extend(["--target-viewport", target_viewport])
    command.extend(["--output", "precise_mode_report.json"])

    if dry_run:
        logger.info(f"[DRY-RUN] Would run: {' '.join(command)}")
        return {"success": True, "status": "ready", "dry_run": True}

    result = _run_command(command, timeout=120)
    report: Dict[str, Any] = {"success": result.returncode == 0}
    if Path("precise_mode_report.json").exists():
        try:
            report["precise_mode"] = json.loads(Path("precise_mode_report.json").read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Could not read precise_mode_report.json: {e}")
    return report


def stage_analyze(file: str = "figma_node.json", dry_run: bool = False) -> bool:
    """Этап 2: анализ структуры Figma."""
    logger.info("=== STAGE: analyze ===")
    command = [sys.executable, "analyzer.py", "--file", file]

    if dry_run:
        logger.info(f"[DRY-RUN] Would run: {' '.join(command)}")
        return True

    result = _run_command(command, timeout=120)
    return result.returncode == 0


def stage_generate_components(
    figma_file: str = "figma_node.json",
    output_dir: str = "src/components/ui",
    mapper_file: str = "figma_component_map.json",
    dry_run: bool = False,
) -> bool:
    """Этап 2b: генерация React-компонентов из реальных Figma Component Sets."""
    logger.info("=== STAGE: generate_components ===")
    command = [
        sys.executable,
        "component_extractor.py",
        "--generate-ui",
        "--figma-file", figma_file,
        "--output-dir", output_dir,
        "--mapper-file", mapper_file,
    ]

    if dry_run:
        logger.info(f"[DRY-RUN] Would run: {' '.join(command)}")
        return True

    result = _run_command(command, timeout=120)
    return result.returncode == 0


def stage_spec(
    file: str = "figma_node.json",
    node_id: Optional[str] = None,
    output: str = "spec.md",
    dry_run: bool = False,
) -> bool:
    """Этап 3: генерация технического задания."""
    logger.info("=== STAGE: spec ===")
    command = [sys.executable, "spec_writer.py", "--file", file, "--output", output]
    if node_id:
        command.extend(["--node-id", node_id])

    if dry_run:
        logger.info(f"[DRY-RUN] Would run: {' '.join(command)}")
        return True

    result = _run_command(command, timeout=120)
    return result.returncode == 0


def stage_tokens(
    file: str = "figma_node.json",
    output_dir: str = ".",
    registry_file: str = "design_tokens.json",
    tailwind_config: str = "tailwind.config.ts",
    globals_css: str = "src/app/globals.css",
    dry_run: bool = False,
) -> bool:
    """Этап 3a: извлечение дизайн-токенов и генерация Tailwind-конфига + globals.css."""
    logger.info("=== STAGE: tokens ===")
    command = [
        sys.executable,
        "design_tokens.py",
        "--file",
        file,
        "--output-dir",
        output_dir,
        "--registry",
        registry_file,
        "--tailwind-config",
        tailwind_config,
        "--globals-css",
        globals_css,
    ]

    if dry_run:
        logger.info(f"[DRY-RUN] Would run: {' '.join(command)}")
        return True

    result = _run_command(command, timeout=120)
    return result.returncode == 0


def stage_layout(
    file: str = "figma_node.json",
    node_id: Optional[str] = None,
    output: str = "layout_ast.json",
    tokens_file: str = "design_tokens.json",
    assets_file: str = "asset_registry.json",
    backend_mapping_file: str = "backend_mapping.json",
    components_registry_file: str = "component_registry.json",
    components_mapper_file: str = "figma_component_map.json",
    components_mapper_override_file: str = ".agent_loop/figma_overrides.json",
    data_models_file: str = "data_model.json",
    dry_run: bool = False,
) -> bool:
    """Этап 3b: детерминированная генерация Tailwind AST из Figma-ноды."""
    logger.info("=== STAGE: layout ===")
    command = [sys.executable, "layout_engine.py", "--file", file, "--output", output]
    if node_id:
        command.extend(["--node-id", node_id])
    if Path(tokens_file).exists():
        command.extend(["--tokens", tokens_file])
    if Path(assets_file).exists():
        command.extend(["--assets", assets_file])
    if Path(backend_mapping_file).exists():
        command.extend(["--backend-mapping", backend_mapping_file])
    if Path(components_registry_file).exists():
        command.extend(["--components", components_registry_file])
    if Path(components_mapper_file).exists():
        command.extend(["--components-mapper", components_mapper_file])
    if Path(components_mapper_override_file).exists():
        command.extend(["--components-mapper-override", components_mapper_override_file])
    if Path(data_models_file).exists():
        command.extend(["--data-models", data_models_file])

    if dry_run:
        logger.info(f"[DRY-RUN] Would run: {' '.join(command)}")
        return True

    result = _run_command(command, timeout=120)
    return result.returncode == 0


def stage_backend_bridge(
    layout_ast_file: str = "layout_ast.json",
    openapi_file: Optional[str] = None,
    prisma_file: Optional[str] = None,
    text_spec_file: Optional[str] = None,
    output_dir: str = "backend_bridge_output",
    mapping_file: str = "backend_mapping.json",
    dry_run: bool = False,
) -> bool:
    """Этап 3b-bridge: сопоставление backend-спецификации с UI и генерация route.ts / action.ts / schema.prisma."""
    logger.info("=== STAGE: backend_bridge ===")
    if not openapi_file and not prisma_file and not text_spec_file:
        logger.info("No backend spec provided. Skipping backend bridge.")
        return True

    command = [
        sys.executable,
        "backend_bridge.py",
        "--layout-ast",
        layout_ast_file,
        "--output-dir",
        output_dir,
        "--mapping-file",
        mapping_file,
    ]
    if openapi_file:
        command.extend(["--openapi", openapi_file])
    if prisma_file:
        command.extend(["--prisma", prisma_file])
    if text_spec_file:
        command.extend(["--text-spec", text_spec_file])

    if dry_run:
        logger.info(f"[DRY-RUN] Would run: {' '.join(command)}")
        return True

    result = _run_command(command, timeout=120)
    return result.returncode == 0


def stage_responsive(
    file: str = "figma_node.json",
    node_id: Optional[str] = None,
    layout_ast_file: str = "layout_ast.json",
    output: str = "responsive_ast.json",
    report: str = "responsive_report.json",
    tokens_file: str = "design_tokens.json",
    assets_file: str = "asset_registry.json",
    backend_mapping_file: str = "backend_mapping.json",
    dry_run: bool = False,
) -> bool:
    """Этап 3b-responsive: генерация breakpoint-вариантов и constraint-классов для Tailwind AST."""
    logger.info("=== STAGE: responsive ===")
    command = [
        sys.executable,
        "responsive_composer.py",
        "--layout-ast",
        layout_ast_file,
        "--figma-file",
        file,
        "--output",
        output,
        "--report",
        report,
    ]
    if node_id:
        command.extend(["--node-id", node_id])
    if Path(tokens_file).exists():
        command.extend(["--tokens", tokens_file])
    if Path(assets_file).exists():
        command.extend(["--assets", assets_file])
    if Path(backend_mapping_file).exists():
        command.extend(["--backend-mapping", backend_mapping_file])

    if dry_run:
        logger.info(f"[DRY-RUN] Would run: {' '.join(command)}")
        return True

    result = _run_command(command, timeout=120)
    return result.returncode == 0


def stage_extract_components(
    ast_file: str = "layout_ast.json",
    output_dir: str = "src/app/components",
    page_ast_output: str = "page_ast.json",
    component_map_output: str = "component_map.json",
    patterns: Optional[str] = None,
    min_duplicates: int = 2,
    dry_run: bool = False,
) -> bool:
    """Этап 3b-alt: извлечение повторяющихся/именованных нод в React-компоненты."""
    logger.info("=== STAGE: extract ===")
    command = [
        sys.executable,
        "component_extractor.py",
        "--ast",
        ast_file,
        "--output-dir",
        output_dir,
        "--page-ast-output",
        page_ast_output,
        "--component-map-output",
        component_map_output,
        "--min-duplicates",
        str(min_duplicates),
    ]
    if patterns:
        command.extend(["--patterns", patterns])

    if dry_run:
        logger.info(f"[DRY-RUN] Would run: {' '.join(command)}")
        return True

    result = _run_command(command, timeout=120)
    return result.returncode == 0


def stage_interactive(
    figma_file: str = "figma_node.json",
    ast_file: str = "page_ast.json",
    ast_output: str = "interactive_ast.json",
    registry_output: str = "interactive_registry.json",
    dry_run: bool = False,
) -> bool:
    """Этап 3c-interactive: маппинг Figma prototype interactions → React state/handlers."""
    logger.info("=== STAGE: interactive ===")
    command = [
        sys.executable,
        "interactive_layer_mapper.py",
        "--figma-file",
        figma_file,
        "--ast",
        ast_file,
        "--ast-output",
        ast_output,
        "--registry-output",
        registry_output,
    ]

    if dry_run:
        logger.info(f"[DRY-RUN] Would run: {' '.join(command)}")
        return True

    result = _run_command(command, timeout=120)
    return result.returncode == 0


def stage_compose(
    ast_file: str = "interactive_ast.json",
    fallback_ast_file: str = "page_ast.json",
    responsive_ast_file: str = "responsive_ast.json",
    output: str = "src/app/page.tsx",
    layout_output: str = "src/app/layout.tsx",
    title: Optional[str] = None,
    site_name: Optional[str] = None,
    base_url: Optional[str] = None,
    components_mapper_file: str = "figma_component_map.json",
    multi_page: bool = False,
    routing_artifacts: bool = False,
    output_dir: Optional[str] = None,
    dry_run: bool = False,
) -> bool:
    """Этап 3c: сборка Tailwind AST в Next.js page.tsx + layout.tsx."""
    logger.info("=== STAGE: compose ===")
    target_ast = responsive_ast_file
    if not Path(target_ast).exists():
        target_ast = ast_file
    if not Path(target_ast).exists():
        target_ast = fallback_ast_file
    command = [
        sys.executable,
        "page_composer.py",
        "--ast",
        target_ast,
        "--output",
        output,
        "--layout-output",
        layout_output,
    ]
    if title:
        command.extend(["--title", title])
    if site_name:
        command.extend(["--site-name", site_name])
    if base_url:
        command.extend(["--base-url", base_url])
    if Path(components_mapper_file).exists():
        command.extend(["--components-mapper", components_mapper_file])
    if multi_page:
        command.append("--multi-page")
    if routing_artifacts:
        command.append("--routing-artifacts")
    if output_dir:
        command.extend(["--output-dir", output_dir])

    if dry_run:
        logger.info(f"[DRY-RUN] Would run: {' '.join(command)}")
        return True

    result = _run_command(command, timeout=120)
    return result.returncode == 0


def stage_preview_workflow(
    site_dir: str = "generated-site",
    output_dir: str = ".tmp/browser/preview",
    page_url: Optional[str] = None,
    start_server: bool = True,
    dev_command: str = "pnpm dev",
    server_timeout: float = 60.0,
    feedback_file: Optional[str] = None,
    report_output: str = "preview_report.json",
    viewport: str = "1280x720",
    title: Optional[str] = None,
    allowed_domains: Optional[str] = None,
    dry_run: bool = False,
) -> bool:
    """Этап 5a: client preview & approval workflow — dev server, screenshot, QR, feedback."""
    logger.info("=== STAGE: preview_workflow ===")
    command = [
        sys.executable,
        "preview_workflow.py",
        "--site-dir",
        site_dir,
        "--output-dir",
        output_dir,
        "--report-output",
        report_output,
        "--dev-command",
        dev_command,
        "--server-timeout",
        str(server_timeout),
        "--viewport",
        viewport,
    ]
    if page_url:
        command.extend(["--page-url", page_url])
    if not start_server:
        command.append("--no-start-server")
    if feedback_file:
        command.extend(["--feedback-file", feedback_file])
    if title:
        command.extend(["--title", title])
    if allowed_domains:
        command.extend(["--allowed-domains", allowed_domains])

    if dry_run:
        logger.info(f"[DRY-RUN] Would run: {' '.join(command)}")
        return True

    result = _run_command(command, timeout=300)
    return result.returncode == 0


def stage_storybook(
    target_dir: str = ".",
    component_dirs: Optional[List[str]] = None,
    stories_dir: str = "src/stories",
    dry_run: bool = False,
) -> bool:
    """Этап 5b: генерация Storybook stories и конфигурации для UI-компонентов."""
    logger.info("=== STAGE: storybook ===")
    command = [
        sys.executable,
        "storybook_generator.py",
        "--target-dir",
        target_dir,
        "--stories-dir",
        stories_dir,
    ]
    if component_dirs:
        command.extend(["--component-dirs", ",".join(component_dirs)])

    if dry_run:
        logger.info(f"[DRY-RUN] Would run: {' '.join(command)}")
        return True

    result = _run_command(command, timeout=180)
    return result.returncode == 0


def stage_deploy(
    target_dir: str = ".",
    provider: str = "vercel",
    live: bool = False,
    build_command: str = "pnpm build",
    dist_dir: str = "dist",
    env: Optional[Dict[str, str]] = None,
    timeout: int = 300,
    dry_run: bool = False,
) -> bool:
    """Этап 5c: публикация сгенерированного сайта на Vercel/Netlify/generic."""
    logger.info("=== STAGE: deploy ===")
    command = [
        sys.executable,
        "deploy_executor.py",
        "--target-dir",
        target_dir,
        "--provider",
        provider,
        "--build-command",
        build_command,
        "--dist-dir",
        dist_dir,
        "--timeout",
        str(timeout),
    ]
    if live:
        command.append("--live")
    if env:
        command.extend(["--env", json.dumps(env)])

    if dry_run:
        logger.info(f"[DRY-RUN] Would run: {' '.join(command)}")
        return True

    result = _run_command(command, timeout=timeout + 30)
    return result.returncode == 0


def stage_content_model(
    ast_file: str = "interactive_ast.json",
    fallback_ast_file: str = "page_ast.json",
    responsive_ast_file: str = "responsive_ast.json",
    sections_dir: str = "src/app/sections",
    page_output: str = "src/app/page.tsx",
    data_output: str = "src/app/page.data.ts",
    content_model_output: str = "content_model.json",
    workspace_root: str = ".",
    components_mapper_file: str = "figma_component_map.json",
    data_models_file: str = "data_model.json",
    dry_run: bool = False,
) -> bool:
    """Этап 3c-alt: разделение страницы на Page + Section-компоненты + Data."""
    logger.info("=== STAGE: content_model ===")
    target_ast = responsive_ast_file
    if not Path(target_ast).exists():
        target_ast = ast_file
    if not Path(target_ast).exists():
        target_ast = fallback_ast_file
    command = [
        sys.executable,
        "content_model.py",
        "--ast",
        target_ast,
        "--output-dir",
        sections_dir,
        "--page-output",
        page_output,
        "--data-output",
        data_output,
        "--content-model-output",
        content_model_output,
        "--workspace-root",
        workspace_root,
    ]
    if Path(components_mapper_file).exists():
        command.extend(["--components-mapper", components_mapper_file])

    if dry_run:
        logger.info(f"[DRY-RUN] Would run: {' '.join(command)}")
        return True

    result = _run_command(command, timeout=120)
    return result.returncode == 0


def stage_visual_qa(
    url: str,
    ast_file: str = "layout_ast.json",
    reference_path: Optional[str] = None,
    output_dir: str = ".tmp/browser/visual_qa",
    viewport: Optional[str] = None,
    expected: Optional[str] = None,
    allowed_domains: Optional[str] = None,
    dry_run: bool = False,
) -> bool:
    """Этап 3d: визуальная QA через Playwright screenshot + DOM assertions."""
    logger.info("=== STAGE: visual_qa ===")
    command = [
        sys.executable,
        "visual_qa.py",
        "--url",
        url,
        "--ast",
        ast_file,
        "--output-dir",
        output_dir,
    ]
    if reference_path:
        command.extend(["--reference", reference_path])
    if viewport:
        command.extend(["--viewport", viewport])
    if expected:
        command.extend(["--expected", expected])
    if allowed_domains:
        command.extend(["--allowed-domains", allowed_domains])

    if dry_run:
        logger.info(f"[DRY-RUN] Would run: {' '.join(command)}")
        return True

    result = _run_command(command, timeout=300)
    return result.returncode == 0


def stage_compliance(
    files: List[str],
    rules_path: str = "project_rules.md",
    workspace_root: Optional[str] = None,
    output: str = "compliance_report.json",
    severity_threshold: str = "low",
    dry_run: bool = False,
) -> bool:
    """Этап 3e: проверка сгенерированного кода на соответствие project_rules.md и отсутствие placeholder-контента."""
    logger.info("=== STAGE: compliance ===")
    if not files:
        logger.warning("No files provided for compliance check. Skipping.")
        return True

    command = [
        sys.executable,
        "compliance_checker.py",
        "--files",
        *files,
        "--rules",
        rules_path,
        "--output",
        output,
        "--severity-threshold",
        severity_threshold,
    ]
    if workspace_root:
        command.extend(["--workspace-root", workspace_root])

    if dry_run:
        logger.info(f"[DRY-RUN] Would run: {' '.join(command)}")
        return True

    result = _run_command(command, timeout=120)
    return result.returncode == 0


def stage_refinement(
    url: str,
    ast_file: str = "layout_ast.json",
    compose_output: str = "src/app/page.tsx",
    reference_path: Optional[str] = None,
    visual_qa_output_dir: str = ".tmp/browser/visual_qa",
    max_iterations: int = 3,
    diff_threshold: float = 0.05,
    viewport: Optional[str] = None,
    expected: Optional[str] = None,
    allowed_domains: Optional[str] = None,
    compose_title: Optional[str] = None,
    report_output: str = "refinement_report.json",
    dry_run: bool = False,
) -> bool:
    """Этап 3f: refinement loop — перезапуск compose+visual QA до успеха или эскалации human."""
    logger.info("=== STAGE: refinement ===")
    command = [
        sys.executable,
        "refinement_loop.py",
        "--url",
        url,
        "--ast",
        ast_file,
        "--compose-output",
        compose_output,
        "--visual-qa-output-dir",
        visual_qa_output_dir,
        "--max-iterations",
        str(max_iterations),
        "--diff-threshold",
        str(diff_threshold),
        "--report-output",
        report_output,
    ]
    if reference_path:
        command.extend(["--reference", reference_path])
    if viewport:
        command.extend(["--viewport", viewport])
    if expected:
        command.extend(["--expected", expected])
    if allowed_domains:
        command.extend(["--allowed-domains", allowed_domains])
    if compose_title:
        command.extend(["--compose-title", compose_title])

    if dry_run:
        logger.info(f"[DRY-RUN] Would run: {' '.join(command)}")
        return True

    result = _run_command(command, timeout=600)
    return result.returncode == 0


def _to_pascal_case(name: str) -> str:
    """Превращает произвольное имя в PascalCase."""
    import re
    name = name.strip()
    name = re.sub(r"[^\w\s]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    words = name.split(" ")
    result = "".join(word[:1].upper() + word[1:] for word in words if word)
    result = re.sub(r"[^A-Za-z0-9_]+", "", result)
    if not result or not result[0].isalpha():
        result = "Figma" + result
    return result


def _collect_top_level_sections(file: str = "figma_node.json") -> List[Dict[str, str]]:
    """Собирает топ-уровневые секции из figma_node.json."""
    data = analyzer.load_figma_json(file)
    if not data:
        return []
    return analyzer.list_top_level_nodes(data)


def stage_components(
    file: str = "figma_node.json",
    node_id: Optional[str] = None,
    output_name: Optional[str] = None,
    skip_assets: bool = False,
    dry_run: bool = False,
) -> bool:
    """Этап 4: генерация React-компонента для одной ноды."""
    logger.info("=== STAGE: components ===")
    command = [sys.executable, "agent.py", "--file", file]
    if node_id:
        command.extend(["--node-id", node_id])
    if output_name:
        command.extend(["--output-name", output_name])
    if skip_assets:
        command.append("--skip-assets")

    if dry_run:
        logger.info(f"[DRY-RUN] Would run: {' '.join(command)}")
        return True

    result = _run_command(command, timeout=300)
    return result.returncode == 0


def stage_components_all(
    file: str = "figma_node.json",
    skip_assets: bool = False,
    dry_run: bool = False,
) -> List[Dict[str, Any]]:
    """Этап 4 (batch): генерация компонентов для всех топ-уровневых секций."""
    logger.info("=== STAGE: components (all sections) ===")
    sections = _collect_top_level_sections(file)
    if not sections:
        logger.warning("No top-level sections found. Nothing to generate.")
        return []

    results: List[Dict[str, Any]] = []
    for section in sections:
        node_id = section["id"]
        name = section["name"]
        output_name = _to_pascal_case(name)
        logger.info(f"Generating component for section: {name} ({node_id}) -> {output_name}")
        ok = stage_components(
            file=file,
            node_id=node_id,
            output_name=output_name,
            skip_assets=skip_assets,
            dry_run=dry_run,
        )
        results.append({
            "id": node_id,
            "name": name,
            "output_name": output_name,
            "success": ok,
        })
    return results


def stage_assets(
    file: str = "figma_node.json",
    public_dir: str = "public",
    assets_dir: str = "assets/figma",
    registry_file: str = "asset_registry.json",
    skip_download: bool = False,
    optimize: bool = True,
    asset_batch_size: int = 25,
    asset_request_delay: float = 0.0,
    asset_max_retries: int = 5,
    asset_max_workers: int = 4,
    skip_existing_assets: bool = True,
    dry_run: bool = False,
) -> bool:
    """Этап 5: скачивание, оптимизация и регистрация ассетов."""
    logger.info("=== STAGE: assets ===")
    command = [
        sys.executable,
        "asset_pipeline.py",
        "--file",
        file,
        "--public-dir",
        public_dir,
        "--assets-dir",
        assets_dir,
        "--registry",
        registry_file,
        "--asset-batch-size",
        str(asset_batch_size),
        "--asset-request-delay",
        str(asset_request_delay),
        "--asset-max-retries",
        str(asset_max_retries),
        "--asset-max-workers",
        str(asset_max_workers),
    ]
    if skip_download:
        command.append("--skip-download")
    if not optimize:
        command.append("--no-optimize")
    if not skip_existing_assets:
        command.append("--no-skip-existing-assets")

    if dry_run:
        logger.info(f"[DRY-RUN] Would run: {' '.join(command)}")
        return True

    result = _run_command(command, timeout=300)
    return result.returncode == 0


def stage_package_deployment(
    output_dir: str = "generated-site",
    site_name: Optional[str] = None,
    base_url: str = "/",
    target: str = "vercel",
    has_backend: bool = False,
    output_mode: str = "export",
    root_dir: Optional[str] = None,
    dry_run: bool = False,
) -> bool:
    """Этап 6: упаковка готовых артефактов для публикации (Vercel/Netlify)."""
    logger.info("=== STAGE: package_deployment ===")
    command = [
        sys.executable,
        "deployment_packager.py",
        "--output-dir",
        output_dir,
        "--target",
        target,
        "--output-mode",
        output_mode,
    ]
    if site_name:
        command.extend(["--site-name", site_name])
    if base_url:
        command.extend(["--base-url", base_url])
    if has_backend:
        command.append("--has-backend")
    if root_dir:
        command.extend(["--root-dir", root_dir])

    if dry_run:
        logger.info(f"[DRY-RUN] Would run: {' '.join(command)}")
        return True

    result = _run_command(command, timeout=120)
    return result.returncode == 0


def run_pipeline(config: Dict[str, Any]) -> Dict[str, Any]:
    """Главный дирижёр: запускает этапы по очереди."""
    start_time = time.time()
    report = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "stages": {},
        "config": config,
    }

    dry_run = config.get("dry_run", False)
    only = config.get("only")
    file = config.get("file", "figma_node.json")
    node_id = config.get("node_id")
    skip_assets = config.get("skip_assets", False)

    stages_to_run = ["bootstrap", "precise_mode_audit", "download_figma_reference", "component_registry", "data_model", "image_enrichment", "analyze", "spec", "tokens", "layout", "backend_bridge", "responsive", "generate_components", "extract", "interactive", "compose", "compliance", "visual_qa", "refinement", "components", "assets", "package_deployment", "preview_workflow", "storybook", "deploy"]
    if config.get("content_model"):
        stages_to_run = ["content_model" if s == "compose" else s for s in stages_to_run]
    if only:
        stages_to_run = [only] if isinstance(only, str) else only

    for stage in stages_to_run:
        if stage == "bootstrap":
            ok = stage_bootstrap(
                force_refresh=config.get("force_refresh", False),
                node_id=node_id,
                api_depth=config.get("api_depth", 2),
                dry_run=dry_run,
            )
            report["stages"]["bootstrap"] = {"success": ok}
            if not ok:
                logger.error("Bootstrap stage failed. Stopping pipeline.")
                break

        elif stage == "precise_mode_audit":
            audit_result = stage_precise_mode_audit(
                file=file,
                node_id=node_id,
                target_viewport=config.get("target_viewport"),
                dry_run=dry_run,
            )
            report["stages"]["precise_mode_audit"] = audit_result
            precise_status = audit_result.get("precise_mode", {}).get("status") if audit_result.get("success") else None
            if precise_status == "not_ready" and config.get("precise_mode_halt", True):
                logger.error("Precise Mode audit reports not_ready. Halting pipeline.")
                break
            if not audit_result.get("success"):
                logger.error("Precise Mode audit stage failed. Halting pipeline.")
                break

        elif stage == "download_figma_reference":
            reference_node_id = config.get("figma_reference_node_id")
            if not reference_node_id:
                logger.info("No --figma-reference-node-id provided; skipping automatic reference download.")
                report["stages"]["download_figma_reference"] = {"success": True, "skipped": True}
            else:
                ok = stage_download_figma_reference(
                    file_key=config.get("figma_file_key"),
                    url=config.get("figma_url"),
                    node_id=reference_node_id,
                    output=config.get("figma_reference_output", ".tmp/browser/figma_reference.png"),
                    scale=config.get("figma_reference_scale", 2.0),
                    dry_run=dry_run,
                )
                report["stages"]["download_figma_reference"] = {"success": ok}
                if not ok:
                    logger.warning("download_figma_reference failed; visual_qa will fall back to no reference.")

        elif stage == "component_registry":
            ok = stage_component_registry(
                file=file,
                output=config.get("component_registry_output", "component_registry.json"),
                mapper_output=config.get("component_mapper_output", "figma_component_map.json"),
                node_id=node_id,
                scan_dirs=[
                    config.get("components_ui_output_dir", "src/components/ui"),
                    config.get("components_output_dir", "src/app/components"),
                ],
                semantic_threshold=config.get("component_semantic_threshold", 0.5),
                override_path=config.get("component_mapper_override_path", ".agent_loop/figma_overrides.json"),
                dry_run=dry_run,
            )
            report["stages"]["component_registry"] = {"success": ok}

        elif stage == "data_model":
            ok = stage_data_model(
                file=file,
                node_id=node_id,
                output=config.get("data_model_output", "data_model.json"),
                min_occurrences=config.get("data_model_min_occurrences", 2),
                top_n=config.get("data_model_top_n", 10),
                dry_run=dry_run,
            )
            report["stages"]["data_model"] = {"success": ok}

        elif stage == "image_enrichment":
            if config.get("enable_image_enrichment"):
                ok = stage_image_enrichment(
                    data_model_file=config.get("data_model_output", "data_model.json"),
                    figma_file=file,
                    spec_file=config.get("spec_output", "spec.md"),
                    public_dir=config.get("public_dir", "public"),
                    assets_registry_file=config.get("assets_registry_file", "asset_registry.json"),
                    provider=config.get("image_provider", "unsplash"),
                    provider_api_key=config.get("image_provider_api_key"),
                    output_dir=config.get("image_enrichment_output_dir", "public/assets/enriched"),
                    max_images=config.get("image_enrichment_max_images", 20),
                    skip_existing=config.get("skip_existing_image_enrichment", True),
                    dry_run=dry_run,
                )
                report["stages"]["image_enrichment"] = {"success": ok}
            else:
                logger.info("Image enrichment disabled. Skipping.")
                report["stages"]["image_enrichment"] = {"success": True, "skipped": True}

        elif stage == "analyze":
            ok = stage_analyze(file=file, dry_run=dry_run)
            report["stages"]["analyze"] = {"success": ok}

        elif stage == "spec":
            ok = stage_spec(
                file=file,
                node_id=node_id,
                output=config.get("spec_output", "spec.md"),
                dry_run=dry_run,
            )
            report["stages"]["spec"] = {"success": ok}

        elif stage == "tokens":
            ok = stage_tokens(
                file=file,
                output_dir=config.get("tokens_output_dir", "."),
                registry_file=config.get("tokens_registry_file", "design_tokens.json"),
                tailwind_config=config.get("tokens_tailwind_config", "tailwind.config.ts"),
                globals_css=config.get("tokens_globals_css", "src/app/globals.css"),
                dry_run=dry_run,
            )
            report["stages"]["tokens"] = {"success": ok}
            if not ok:
                logger.error("Tokens stage failed. Stopping pipeline.")
                break

        elif stage == "layout":
            tokens_file = Path(config.get("tokens_output_dir", ".")) / config.get(
                "tokens_registry_file", "design_tokens.json"
            )
            assets_file = Path(config.get("public_dir", "public")) / config.get(
                "assets_registry_file", "asset_registry.json"
            )
            backend_mapping_file = config.get("backend_mapping_file", "backend_mapping.json")
            ok = stage_layout(
                file=file,
                node_id=node_id,
                output=config.get("layout_output", "layout_ast.json"),
                tokens_file=str(tokens_file),
                assets_file=str(assets_file),
                backend_mapping_file=backend_mapping_file,
                components_registry_file=config.get("component_registry_output", "component_registry.json"),
                components_mapper_file=config.get("component_mapper_output", "figma_component_map.json"),
                components_mapper_override_file=config.get("component_mapper_override_path", ".agent_loop/figma_overrides.json"),
                data_models_file=config.get("data_model_output", "data_model.json"),
                dry_run=dry_run,
            )
            report["stages"]["layout"] = {"success": ok}

        elif stage == "backend_bridge":
            ok = stage_backend_bridge(
                layout_ast_file=config.get("layout_output", "layout_ast.json"),
                openapi_file=config.get("openapi_file"),
                prisma_file=config.get("prisma_file"),
                text_spec_file=config.get("backend_spec_text_file"),
                output_dir=config.get("backend_output_dir", "backend_bridge_output"),
                mapping_file=config.get("backend_mapping_file", "backend_mapping.json"),
                dry_run=dry_run,
            )
            report["stages"]["backend_bridge"] = {"success": ok}

        elif stage == "responsive":
            tokens_file = Path(config.get("tokens_output_dir", ".")) / config.get(
                "tokens_registry_file", "design_tokens.json"
            )
            assets_file = Path(config.get("public_dir", "public")) / config.get(
                "assets_registry_file", "asset_registry.json"
            )
            ok = stage_responsive(
                file=file,
                node_id=node_id,
                layout_ast_file=config.get("layout_output", "layout_ast.json"),
                output=config.get("responsive_output", "responsive_ast.json"),
                report=config.get("responsive_report", "responsive_report.json"),
                tokens_file=str(tokens_file),
                assets_file=str(assets_file),
                backend_mapping_file=config.get("backend_mapping_file", "backend_mapping.json"),
                dry_run=dry_run,
            )
            report["stages"]["responsive"] = {"success": ok}

        elif stage == "generate_components":
            ok = stage_generate_components(
                figma_file=file,
                output_dir=config.get("components_ui_output_dir", "src/components/ui"),
                mapper_file=config.get("component_mapper_output", "figma_component_map.json"),
                dry_run=dry_run,
            )
            report["stages"]["generate_components"] = {"success": ok}

        elif stage == "extract":
            ok = stage_extract_components(
                ast_file=config.get("layout_output", "layout_ast.json"),
                output_dir=config.get("components_output_dir", "src/app/components"),
                page_ast_output=config.get("page_ast_output", "page_ast.json"),
                component_map_output=config.get("component_map_output", "component_map.json"),
                patterns=config.get("component_patterns"),
                min_duplicates=config.get("component_min_duplicates", 2),
                dry_run=dry_run,
            )
            report["stages"]["extract"] = {"success": ok}

        elif stage == "interactive":
            ok = stage_interactive(
                figma_file=config.get("file", "figma_node.json"),
                ast_file=config.get("page_ast_output", "page_ast.json"),
                ast_output=config.get("interactive_ast_output", "interactive_ast.json"),
                registry_output=config.get("interactive_registry_output", "interactive_registry.json"),
                dry_run=dry_run,
            )
            report["stages"]["interactive"] = {"success": ok}

        elif stage == "compose":
            ok = stage_compose(
                ast_file=config.get("interactive_ast_output", "interactive_ast.json"),
                fallback_ast_file=config.get("layout_output", "layout_ast.json"),
                responsive_ast_file=config.get("responsive_output", "responsive_ast.json"),
                output=config.get("compose_output", "src/app/page.tsx"),
                layout_output=config.get("compose_layout_output", "src/app/layout.tsx"),
                title=config.get("compose_title"),
                site_name=config.get("site_name"),
                base_url=config.get("base_url"),
                components_mapper_file=config.get("component_mapper_output", "figma_component_map.json"),
                multi_page=config.get("multi_page", False),
                routing_artifacts=config.get("routing_artifacts", False),
                output_dir=config.get("compose_output_dir"),
                dry_run=dry_run,
            )
            report["stages"]["compose"] = {"success": ok}

        elif stage == "content_model":
            ok = stage_content_model(
                ast_file=config.get("interactive_ast_output", "interactive_ast.json"),
                fallback_ast_file=config.get("layout_output", "layout_ast.json"),
                responsive_ast_file=config.get("responsive_output", "responsive_ast.json"),
                sections_dir=config.get("content_model_sections_dir", "src/app/sections"),
                page_output=config.get("content_model_page_output", "src/app/page.tsx"),
                data_output=config.get("content_model_data_output", "src/app/page.data.ts"),
                content_model_output=config.get("content_model_json_output", "content_model.json"),
                workspace_root=config.get("content_model_workspace_root", "."),
                components_mapper_file=config.get("component_mapper_output", "figma_component_map.json"),
                data_models_file=config.get("data_model_output", "data_model.json"),
                dry_run=dry_run,
            )
            report["stages"]["content_model"] = {"success": ok}

        elif stage == "compliance":
            files = config.get("compliance_files") or []
            if not files:
                files = [config.get("compose_output", "src/app/page.tsx")]
            ok = stage_compliance(
                files=files,
                rules_path=config.get("compliance_rules_path", "project_rules.md"),
                workspace_root=config.get("compliance_workspace_root"),
                output=config.get("compliance_output", "compliance_report.json"),
                severity_threshold=config.get("compliance_severity_threshold", "low"),
                dry_run=dry_run,
            )
            report["stages"]["compliance"] = {"success": ok}

        elif stage == "visual_qa":
            url = config.get("visual_qa_url")
            if not url:
                logger.warning("visual_qa stage requires --visual-qa-url. Skipping.")
                # In dry-run mode, a skipped optional stage is not a failure.
                report["stages"]["visual_qa"] = {
                    "success": dry_run,
                    "skipped": True,
                    "reason": "missing --visual-qa-url",
                }
            else:
                reference_path = config.get("visual_qa_reference")
                if not reference_path:
                    reference_path = config.get("figma_reference_output", ".tmp/browser/figma_reference.png")
                    if not Path(reference_path).exists():
                        reference_path = None
                ok = stage_visual_qa(
                    url=url,
                    ast_file=config.get("layout_output", "layout_ast.json"),
                    reference_path=reference_path,
                    output_dir=config.get("visual_qa_output_dir", ".tmp/browser/visual_qa"),
                    viewport=config.get("visual_qa_viewport"),
                    expected=config.get("visual_qa_expected"),
                    allowed_domains=config.get("visual_qa_allowed_domains"),
                    dry_run=dry_run,
                )
                report["stages"]["visual_qa"] = {"success": ok}

        elif stage == "refinement":
            url = config.get("visual_qa_url")
            if not url:
                logger.warning("refinement stage requires --visual-qa-url. Skipping.")
                # In dry-run mode, a skipped optional stage is not a failure.
                report["stages"]["refinement"] = {
                    "success": dry_run,
                    "skipped": True,
                    "reason": "missing --visual-qa-url",
                }
            else:
                ok = stage_refinement(
                    url=url,
                    ast_file=config.get("layout_output", "layout_ast.json"),
                    compose_output=config.get("compose_output", "src/app/page.tsx"),
                    reference_path=config.get("visual_qa_reference"),
                    visual_qa_output_dir=config.get("visual_qa_output_dir", ".tmp/browser/visual_qa"),
                    max_iterations=config.get("refinement_max_iterations", 3),
                    diff_threshold=config.get("refinement_diff_threshold", 0.05),
                    viewport=config.get("visual_qa_viewport"),
                    expected=config.get("visual_qa_expected"),
                    allowed_domains=config.get("visual_qa_allowed_domains"),
                    compose_title=config.get("compose_title"),
                    report_output=config.get("refinement_report_output", "refinement_report.json"),
                    dry_run=dry_run,
                )
                report["stages"]["refinement"] = {"success": ok}

        elif stage == "components":
            if config.get("all_sections", False):
                results = stage_components_all(
                    file=file,
                    skip_assets=skip_assets,
                    dry_run=dry_run,
                )
                report["stages"]["components"] = {
                    "success": all(r["success"] for r in results) if results else True,
                    "sections": results,
                }
            else:
                output_name = config.get("output_name")
                if node_id and not output_name:
                    target = analyzer.find_node_by_id(analyzer.load_figma_json(file), node_id)
                    if target:
                        output_name = _to_pascal_case(target.get("name", "Component"))
                ok = stage_components(
                    file=file,
                    node_id=node_id,
                    output_name=output_name,
                    skip_assets=skip_assets,
                    dry_run=dry_run,
                )
                report["stages"]["components"] = {"success": ok}

        elif stage == "assets":
            ok = stage_assets(
                file=file,
                public_dir=config.get("public_dir", "public"),
                assets_dir=config.get("assets_dir", "assets/figma"),
                registry_file=config.get("assets_registry_file", "asset_registry.json"),
                skip_download=config.get("skip_assets_download", False),
                optimize=config.get("optimize_assets", True),
                asset_batch_size=config.get("asset_batch_size", 25),
                asset_request_delay=config.get("asset_request_delay", 0.0),
                asset_max_retries=config.get("asset_max_retries", 5),
                asset_max_workers=config.get("asset_max_workers", 4),
                skip_existing_assets=config.get("skip_existing_assets", True),
                dry_run=dry_run,
            )
            report["stages"]["assets"] = {"success": ok}

        elif stage == "package_deployment":
            if not config.get("package_deployment"):
                logger.info("Deployment packaging disabled. Skipping.")
                report["stages"]["package_deployment"] = {
                    "success": True,
                    "skipped": True,
                    "reason": "disabled",
                }
            else:
                ok = stage_package_deployment(
                    output_dir=config.get("package_deployment_output_dir", "generated-site"),
                    site_name=config.get("site_name"),
                    base_url=config.get("base_url", "/"),
                    target=config.get("package_deployment_target", "vercel"),
                    has_backend=config.get("package_deployment_has_backend", False),
                    output_mode=config.get("package_deployment_output_mode", "export"),
                    root_dir=config.get("package_deployment_root_dir"),
                    dry_run=dry_run,
                )
                report["stages"]["package_deployment"] = {"success": ok}

        elif stage == "preview_workflow":
            if not config.get("preview_workflow"):
                logger.info("Preview workflow disabled. Skipping.")
                report["stages"]["preview_workflow"] = {
                    "success": True,
                    "skipped": True,
                    "reason": "disabled",
                }
            else:
                ok = stage_preview_workflow(
                    site_dir=config.get("preview_workflow_site_dir", "generated-site"),
                    output_dir=config.get("preview_workflow_output_dir", ".tmp/browser/preview"),
                    page_url=config.get("preview_workflow_page_url"),
                    start_server=config.get("preview_workflow_start_server", True),
                    dev_command=config.get("preview_workflow_dev_command", "pnpm dev"),
                    server_timeout=config.get("preview_workflow_server_timeout", 60.0),
                    feedback_file=config.get("preview_workflow_feedback_file"),
                    report_output=config.get("preview_workflow_report_output", "preview_report.json"),
                    viewport=config.get("preview_workflow_viewport", "1280x720"),
                    title=config.get("preview_workflow_title") or config.get("site_name"),
                    allowed_domains=config.get("preview_workflow_allowed_domains"),
                    dry_run=dry_run,
                )
                report["stages"]["preview_workflow"] = {"success": ok}

        elif stage == "storybook":
            if not config.get("storybook"):
                logger.info("Storybook generation disabled. Skipping.")
                report["stages"]["storybook"] = {
                    "success": True,
                    "skipped": True,
                    "reason": "disabled",
                }
            else:
                ok = stage_storybook(
                    target_dir=config.get("storybook_target_dir", "."),
                    component_dirs=config.get("storybook_component_dirs"),
                    stories_dir=config.get("storybook_stories_dir", "src/stories"),
                    dry_run=dry_run,
                )
                report["stages"]["storybook"] = {"success": ok}

        elif stage == "deploy":
            if not config.get("deploy"):
                logger.info("Deploy execution disabled. Skipping.")
                report["stages"]["deploy"] = {
                    "success": True,
                    "skipped": True,
                    "reason": "disabled",
                }
            else:
                ok = stage_deploy(
                    target_dir=config.get("deploy_cwd") or config.get("deploy_target_dir", "."),
                    provider=config.get("deploy_target", "vercel"),
                    live=config.get("deploy_live", False),
                    build_command=config.get("deploy_build_command", "pnpm build"),
                    dist_dir=config.get("deploy_dist_dir", "dist"),
                    env=config.get("deploy_env"),
                    timeout=config.get("deploy_timeout", 300),
                    dry_run=dry_run,
                )
                report["stages"]["deploy"] = {"success": ok}

        else:
            logger.warning(f"Unknown stage: {stage}. Skipping.")

    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["duration_seconds"] = round(time.time() - start_time, 2)
    return report


def save_report(report: Dict[str, Any], path: str = "conductor_report.json") -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    logger.info(f"Report saved to {path}")


def main():
    parser = argparse.ArgumentParser(
        description="Главный дирижёр пайплайна Figma-to-Code. Запускает bootstrap, analyze, spec, tokens, layout, extract, compose, components, assets, package_deployment.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Запустить полный пайплайн: bootstrap, download_figma_reference, component_registry, analyze, spec, tokens, layout, backend_bridge, responsive, generate_components, extract, interactive, compose, compliance, visual_qa, refinement, components, assets, package_deployment.",
    )
    parser.add_argument(
        "--only",
        default=None,
        help="Запустить только один этап: bootstrap, download_figma_reference, component_registry, analyze, spec, tokens, layout, backend_bridge, responsive, generate_components, extract, interactive, compose, compliance, visual_qa, refinement, components, assets, package_deployment."
    )
    parser.add_argument(
        "--node-id",
        default=os.environ.get("FIGMA_NODE_ID"),
        help="ID конкретной ноды Figma. По умолчанию из FIGMA_NODE_ID."
    )
    parser.add_argument(
        "--output-name",
        default=None,
        help="Имя компонента для single-section режима."
    )
    parser.add_argument(
        "--all-sections",
        action="store_true",
        help="Сгенерировать компонент для каждой топ-уровневой секции."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Принудительно обновить данные из Figma API."
    )
    parser.add_argument(
        "--api-depth",
        type=int,
        default=2,
        help="Параметр depth для Figma API (по умолчанию 2)."
    )
    parser.add_argument(
        "--skip-assets",
        action="store_true",
        help="Не скачивать ассеты."
    )
    parser.add_argument(
        "--skip-assets-download",
        action="store_true",
        help="Asset Pipeline: построить реестр без реального скачивания (synthetic publicPath)."
    )
    parser.add_argument(
        "--enable-image-enrichment",
        action="store_true",
        help="Включить подбор внешних изображений для data_model-карточек.",
    )
    parser.add_argument(
        "--image-provider",
        default="unsplash",
        choices=["unsplash", "mock"],
        help="Провайдер внешних изображений (по умолчанию unsplash).",
    )
    parser.add_argument(
        "--image-provider-api-key",
        default=None,
        help="API-ключ провайдера изображений (или env UNSPLASH_ACCESS_KEY).",
    )
    parser.add_argument(
        "--image-enrichment-output-dir",
        default="public/assets/enriched",
        help="Директория для скачанных enriched-изображений.",
    )
    parser.add_argument(
        "--image-enrichment-max-images",
        type=int,
        default=20,
        help="Максимальное число внешних изображений для скачивания.",
    )
    parser.add_argument(
        "--no-skip-existing-image-enrichment",
        action="store_true",
        help="Перезагружать enriched-изображения даже если локальный файл уже есть.",
    )
    parser.add_argument(
        "--optimize-assets",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Asset Pipeline: включить/отключить svgo/sharp оптимизацию (по умолчанию включено)."
    )
    parser.add_argument(
        "--public-dir",
        default="public",
        help="Корневая public-директория для ассетов (по умолчанию public)."
    )
    parser.add_argument(
        "--assets-dir",
        default="assets/figma",
        help="Поддиректория в public-dir для Figma-ассетов (по умолчанию assets/figma)."
    )
    parser.add_argument(
        "--assets-registry-file",
        default="asset_registry.json",
        help="Имя JSON-реестра ассетов (по умолчанию asset_registry.json)."
    )
    parser.add_argument(
        "--asset-batch-size",
        type=int,
        default=25,
        help="Максимальное число ID в одном batch-запросе к Figma Images API (по умолчанию 25)."
    )
    parser.add_argument(
        "--asset-request-delay",
        type=float,
        default=0.0,
        help="Искусственная задержка в секундах между запросами к Figma Images API (по умолчанию 0.0; rate-limit обрабатывается через 429/Retry-After)."
    )
    parser.add_argument(
        "--asset-max-retries",
        type=int,
        default=5,
        help="Максимальное число retry при 429/транзиентных ошибках Figma API (по умолчанию 5)."
    )
    parser.add_argument(
        "--asset-max-workers",
        type=int,
        default=4,
        help="Число параллельных worker для batch-запросов URL и скачивания ассетов (по умолчанию 4)."
    )
    parser.add_argument(
        "--skip-existing-assets",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Пропускать уже скачанные локальные ассеты (по умолчанию True)."
    )
    parser.add_argument(
        "--spec-output",
        default="spec.md",
        help="Путь для сохранения технического задания."
    )
    parser.add_argument(
        "--tokens-output-dir",
        default=".",
        help="Директория для записи design_tokens.json, tailwind.config.ts и globals.css."
    )
    parser.add_argument(
        "--tokens-registry-file",
        default="design_tokens.json",
        help="Имя JSON-реестра дизайн-токенов."
    )
    parser.add_argument(
        "--tokens-tailwind-config",
        default="tailwind.config.ts",
        help="Имя Tailwind-конфига."
    )
    parser.add_argument(
        "--tokens-globals-css",
        default="src/app/globals.css",
        help="Относительный путь к globals.css внутри --tokens-output-dir."
    )
    parser.add_argument(
        "--layout-output",
        default="layout_ast.json",
        help="Путь для сохранения Tailwind AST от Layout Engine."
    )
    parser.add_argument(
        "--component-registry-output",
        default="component_registry.json",
        help="Путь для сохранения Component Registry."
    )
    parser.add_argument(
        "--component-semantic-threshold",
        type=float,
        default=0.5,
        help="Minimum semantic similarity score (0-1) for matching Figma components to local components."
    )
    parser.add_argument(
        "--component-mapper-override-path",
        default=".agent_loop/figma_overrides.json",
        help="Path to manual component mapping override file."
    )
    parser.add_argument(
        "--components-ui-output-dir",
        default="src/components/ui",
        help="Директория для компонентов, сгенерированных из Figma Component Sets."
    )
    parser.add_argument(
        "--responsive-output",
        default="responsive_ast.json",
        help="Путь для сохранения enriched responsive AST от Responsive Composer."
    )
    parser.add_argument(
        "--responsive-report",
        default="responsive_report.json",
        help="Путь для сохранения отчёта Responsive Composer."
    )
    parser.add_argument(
        "--compose-output",
        default="src/app/page.tsx",
        help="Путь для сохранения Next.js-страницы от Section Composer."
    )
    parser.add_argument(
        "--compose-layout-output",
        default="src/app/layout.tsx",
        help="Путь для сохранения Next.js layout.tsx от Section Composer."
    )
    parser.add_argument(
        "--compose-title",
        default=None,
        help="Заголовок страницы для Section Composer."
    )
    parser.add_argument(
        "--site-name",
        default=None,
        help="Название сайта для Open Graph / structured data / deployment package."
    )
    parser.add_argument(
        "--base-url",
        default="/",
        help="Базовый URL сайта для canonical / OG URLs / deployment package."
    )
    parser.add_argument(
        "--package-deployment",
        action="store_true",
        help="Включить этап упаковки артефактов для публикации (Vercel/Netlify)."
    )
    parser.add_argument(
        "--package-deployment-output-dir",
        default="generated-site",
        help="Директория для deployment-пакета (по умолчанию generated-site)."
    )
    parser.add_argument(
        "--package-deployment-target",
        default="vercel",
        choices=["vercel", "netlify", "both"],
        help="Целевая платформа для README и deploy.sh (по умолчанию vercel)."
    )
    parser.add_argument(
        "--package-deployment-has-backend",
        action="store_true",
        help="Включить backend/database зависимости и переменные в .env.example."
    )
    parser.add_argument(
        "--package-deployment-output-mode",
        default="export",
        choices=["export", "standalone"],
        help="Next.js output mode для next.config.ts (по умолчанию export)."
    )
    parser.add_argument(
        "--preview-workflow",
        action="store_true",
        help="Включить этап client preview & approval workflow (dev server, screenshot, QR, feedback).")
    parser.add_argument(
        "--preview-workflow-site-dir",
        default="generated-site",
        help="Директория сгенерированного сайта для preview workflow.")
    parser.add_argument(
        "--preview-workflow-page-url",
        default=None,
        help="URL уже запущенного сайта (иначе поднимается pnpm dev).")
    parser.add_argument(
        "--preview-workflow-output-dir",
        default=".tmp/browser/preview",
        help="Директория для артефактов preview workflow.")
    parser.add_argument(
        "--preview-workflow-feedback-file",
        default=None,
        help="JSON-файл с feedback клиента (approved, notes, reject_reason).")
    parser.add_argument(
        "--preview-workflow-viewport",
        default="1280x720",
        help="Viewport для скриншота preview.")
    parser.add_argument(
        "--preview-workflow-allowed-domains",
        default=None,
        help="Разрешённые внешние домены для preview screenshot через запятую.")
    parser.add_argument(
        "--multi-page",
        action="store_true",
        help="Включить генерацию многостраничного Next.js App Router маршрутизации."
    )
    parser.add_argument(
        "--routing-artifacts",
        action="store_true",
        help="Сгенерировать только артефакты маршрутизации (sitemap/robots/Navigation) без перезаписи страниц."
    )
    parser.add_argument(
        "--storybook",
        action="store_true",
        help="Включить генерацию Storybook stories и конфигурации .storybook."
    )
    parser.add_argument(
        "--deploy",
        action="store_true",
        help="Включить этап публикации (dry-run по умолчанию)."
    )
    parser.add_argument(
        "--deploy-live",
        action="store_true",
        help="Отключить dry-run для deploy и запустить реальную публикацию."
    )
    parser.add_argument(
        "--deploy-target",
        default="vercel",
        choices=["vercel", "netlify", "generic"],
        help="Целевая платформа для deploy (по умолчанию vercel)."
    )
    parser.add_argument(
        "--deploy-cwd",
        default=None,
        help="Рабочая директория для команды deploy (по умолчанию site_dir)."
    )
    parser.add_argument(
        "--deploy-timeout",
        type=int,
        default=300,
        help="Таймаут deploy команды в секундах (по умолчанию 300)."
    )
    parser.add_argument(
        "--components-output-dir",
        default="src/app/components",
        help="Директория для извлечённых React-компонентов."
    )
    parser.add_argument(
        "--page-ast-output",
        default="page_ast.json",
        help="Путь для урезанного AST страницы после извлечения компонентов."
    )
    parser.add_argument(
        "--interactive-ast-output",
        default="interactive_ast.json",
        help="Путь для AST с маппингом интерактивных слоёв."
    )
    parser.add_argument(
        "--interactive-registry-output",
        default="interactive_registry.json",
        help="Путь для реестра интерактивных слоёв."
    )
    parser.add_argument(
        "--component-map-output",
        default="component_map.json",
        help="Путь для реестра извлечённых компонентов."
    )
    parser.add_argument(
        "--component-patterns",
        default=None,
        help='JSON-список паттернов имён для извлечения, например ["card","hero"].'
    )
    parser.add_argument(
        "--component-min-duplicates",
        type=int,
        default=2,
        help="Минимальное число структурных дубликатов для извлечения компонента."
    )
    parser.add_argument(
        "--visual-qa-url",
        default=None,
        help="URL сгенерированного лендинга для Visual QA (этап visual_qa)."
    )
    parser.add_argument(
        "--visual-qa-reference",
        default=None,
        help="Путь к референсному скриншоту Figma для сравнения."
    )
    parser.add_argument(
        "--visual-qa-output-dir",
        default=".tmp/browser/visual_qa",
        help="Директория для скриншотов и отчёта Visual QA."
    )
    parser.add_argument(
        "--visual-qa-viewport",
        default=None,
        help="Viewport для Visual QA, например 1280x720."
    )
    parser.add_argument(
        "--visual-qa-expected",
        default=None,
        help='JSON-строка DOM-assertions, например [{"selector":"h1","expected_text":"Hero"}].'
    )
    parser.add_argument(
        "--visual-qa-allowed-domains",
        default=None,
        help="Список разрешённых внешних доменов через запятую для URL-гарда Visual QA."
    )
    parser.add_argument(
        "--compliance-files",
        nargs="+",
        default=None,
        help="Список сгенерированных файлов для проверки соответствия project_rules.md (по умолчанию --compose-output)."
    )
    parser.add_argument(
        "--compliance-rules-path",
        default="project_rules.md",
        help="Путь к project_rules.md для compliance checker."
    )
    parser.add_argument(
        "--compliance-output",
        default="compliance_report.json",
        help="Путь для сохранения отчёта compliance checker."
    )
    parser.add_argument(
        "--compliance-severity-threshold",
        default="low",
        choices=["low", "medium", "high", "critical"],
        help="Минимальный уровень severity, который блокирует compliance."
    )
    parser.add_argument(
        "--refinement-max-iterations",
        type=int,
        default=3,
        help="Максимальное число итераций refinement loop (по умолчанию 3)."
    )
    parser.add_argument(
        "--refinement-diff-threshold",
        type=float,
        default=0.05,
        help="Порог diff score, выше которого visual QA требует корректировки."
    )
    parser.add_argument(
        "--refinement-report-output",
        default="refinement_report.json",
        help="Путь для сохранения отчёта refinement loop."
    )
    parser.add_argument(
        "--openapi",
        default=None,
        help="Путь к OpenAPI JSON/YAML спецификации backend."
    )
    parser.add_argument(
        "--prisma",
        default=None,
        help="Путь к Prisma schema файлу."
    )
    parser.add_argument(
        "--backend-spec-text",
        default=None,
        help="Путь к структурированному JSON-брифу backend."
    )
    parser.add_argument(
        "--backend-output-dir",
        default="backend_bridge_output",
        help="Директория для сгенерированных backend артефактов."
    )
    parser.add_argument(
        "--backend-mapping-file",
        default="backend_mapping.json",
        help="Путь для backend_mapping.json."
    )
    parser.add_argument(
        "--figma-file",
        default=None,
        help="Figma-URL или file key для скачивания референсного скриншота."
    )
    parser.add_argument(
        "--figma-reference-node-id",
        default=None,
        help="Figma node id фрейма/страницы для референсного скриншота."
    )
    parser.add_argument(
        "--figma-reference-scale",
        type=float,
        default=2.0,
        help="Масштаб референсного скриншота (по умолчанию 2.0)."
    )
    parser.add_argument(
        "--figma-reference-output",
        default=".tmp/browser/figma_reference.png",
        help="Путь для сохранения референсного скриншота."
    )
    parser.add_argument(
        "--file",
        default="figma_node.json",
        help="Путь к JSON-файлу Figma-структуры."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Показать план выполнения без реального запуска агентов."
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Подробный вывод в лог."
    )
    args = parser.parse_args()

    _setup_logging(verbose=args.verbose)

    if not args.all and not args.only:
        # Обходим проблему кодировки Windows в argparse print_help.
        try:
            parser.print_help()
        except UnicodeEncodeError:
            help_text = parser.format_help()
            sys.stdout.buffer.write(help_text.encode("utf-8"))
            print()
        sys.exit(0)

    config = {
        "all": args.all,
        "only": args.only,
        "node_id": args.node_id,
        "output_name": args.output_name,
        "all_sections": args.all_sections,
        "interactive_ast_output": args.interactive_ast_output,
        "interactive_registry_output": args.interactive_registry_output,
        "force_refresh": args.force,
        "api_depth": args.api_depth,
        "skip_assets": args.skip_assets,
        "skip_assets_download": args.skip_assets_download,
        "enable_image_enrichment": args.enable_image_enrichment,
        "image_provider": args.image_provider,
        "image_provider_api_key": args.image_provider_api_key,
        "image_enrichment_output_dir": args.image_enrichment_output_dir,
        "image_enrichment_max_images": args.image_enrichment_max_images,
        "skip_existing_image_enrichment": not args.no_skip_existing_image_enrichment,
        "optimize_assets": args.optimize_assets,
        "public_dir": args.public_dir,
        "assets_dir": args.assets_dir,
        "assets_registry_file": args.assets_registry_file,
        "asset_batch_size": args.asset_batch_size,
        "asset_request_delay": args.asset_request_delay,
        "asset_max_retries": args.asset_max_retries,
        "asset_max_workers": args.asset_max_workers,
        "skip_existing_assets": args.skip_existing_assets,
        "spec_output": args.spec_output,
        "tokens_output_dir": args.tokens_output_dir,
        "tokens_registry_file": args.tokens_registry_file,
        "tokens_tailwind_config": args.tokens_tailwind_config,
        "tokens_globals_css": args.tokens_globals_css,
        "layout_output": args.layout_output,
        "component_registry_output": args.component_registry_output,
        "component_semantic_threshold": args.component_semantic_threshold,
        "component_mapper_override_path": args.component_mapper_override_path,
        "components_ui_output_dir": args.components_ui_output_dir,
        "responsive_output": args.responsive_output,
        "responsive_report": args.responsive_report,
        "compose_output": args.compose_output,
        "compose_layout_output": args.compose_layout_output,
        "compose_title": args.compose_title,
        "site_name": args.site_name,
        "base_url": args.base_url,
        "package_deployment": args.package_deployment,
        "package_deployment_output_dir": args.package_deployment_output_dir,
        "package_deployment_target": args.package_deployment_target,
        "package_deployment_has_backend": args.package_deployment_has_backend,
        "package_deployment_output_mode": args.package_deployment_output_mode,
        "preview_workflow": args.preview_workflow,
        "preview_workflow_site_dir": args.preview_workflow_site_dir,
        "preview_workflow_page_url": args.preview_workflow_page_url,
        "preview_workflow_output_dir": args.preview_workflow_output_dir,
        "preview_workflow_feedback_file": args.preview_workflow_feedback_file,
        "preview_workflow_viewport": args.preview_workflow_viewport,
        "preview_workflow_allowed_domains": args.preview_workflow_allowed_domains,
        "multi_page": args.multi_page,
        "routing_artifacts": args.routing_artifacts,
        "storybook": args.storybook,
        "deploy": args.deploy,
        "deploy_live": args.deploy_live,
        "deploy_target": args.deploy_target,
        "deploy_cwd": args.deploy_cwd,
        "deploy_timeout": args.deploy_timeout,
        "components_output_dir": args.components_output_dir,
        "page_ast_output": args.page_ast_output,
        "component_map_output": args.component_map_output,
        "component_patterns": args.component_patterns,
        "component_min_duplicates": args.component_min_duplicates,
        "visual_qa_url": args.visual_qa_url,
        "visual_qa_reference": args.visual_qa_reference,
        "visual_qa_output_dir": args.visual_qa_output_dir,
        "visual_qa_viewport": args.visual_qa_viewport,
        "visual_qa_expected": args.visual_qa_expected,
        "visual_qa_allowed_domains": args.visual_qa_allowed_domains,
        "compliance_files": args.compliance_files,
        "compliance_rules_path": args.compliance_rules_path,
        "compliance_output": args.compliance_output,
        "compliance_severity_threshold": args.compliance_severity_threshold,
        "refinement_max_iterations": args.refinement_max_iterations,
        "refinement_diff_threshold": args.refinement_diff_threshold,
        "refinement_report_output": args.refinement_report_output,
        "openapi_file": args.openapi,
        "prisma_file": args.prisma,
        "backend_spec_text_file": args.backend_spec_text,
        "backend_output_dir": args.backend_output_dir,
        "backend_mapping_file": args.backend_mapping_file,
        "figma_file_key": args.figma_file or os.environ.get("FIGMA_URL"),
        "figma_url": args.figma_file or os.environ.get("FIGMA_URL"),
        "figma_reference_node_id": args.figma_reference_node_id,
        "figma_reference_scale": args.figma_reference_scale,
        "figma_reference_output": args.figma_reference_output,
        "file": args.file,
        "dry_run": args.dry_run,
        "verbose": args.verbose,
    }

    if args.dry_run:
        logger.info("=== DRY RUN ===")

    report = run_pipeline(config)
    save_report(report)

    if args.dry_run:
        # In dry-run mode, skipped optional stages (e.g., visual_qa/refinement without URL)
        # must not be treated as hard failures. Only actual stage failures count.
        real_failures = [
            name
            for name, stage in report["stages"].items()
            if not stage.get("success", False) and not stage.get("skipped", False)
        ]
        success = len(real_failures) == 0
    else:
        success = all(stage.get("success", False) for stage in report["stages"].values())
    logger.info(f"Pipeline finished in {report['duration_seconds']}s. Overall success: {success}")
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
