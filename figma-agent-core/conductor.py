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
import asset_downloader


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
    """Запускает subprocess и логирует результат."""
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


def stage_analyze(file: str = "figma_node.json", dry_run: bool = False) -> bool:
    """Этап 2: анализ структуры Figma."""
    logger.info("=== STAGE: analyze ===")
    command = [sys.executable, "analyzer.py", "--file", file]

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


def stage_layout(
    file: str = "figma_node.json",
    node_id: Optional[str] = None,
    output: str = "layout_ast.json",
    dry_run: bool = False,
) -> bool:
    """Этап 3b: детерминированная генерация Tailwind AST из Figma-ноды."""
    logger.info("=== STAGE: layout ===")
    command = [sys.executable, "layout_engine.py", "--file", file, "--output", output]
    if node_id:
        command.extend(["--node-id", node_id])

    if dry_run:
        logger.info(f"[DRY-RUN] Would run: {' '.join(command)}")
        return True

    result = _run_command(command, timeout=120)
    return result.returncode == 0


def stage_compose(
    ast_file: str = "layout_ast.json",
    output: str = "src/app/page.tsx",
    title: Optional[str] = None,
    dry_run: bool = False,
) -> bool:
    """Этап 3c: сборка Tailwind AST в Next.js page.tsx."""
    logger.info("=== STAGE: compose ===")
    command = [sys.executable, "page_composer.py", "--ast", ast_file, "--output", output]
    if title:
        command.extend(["--title", title])

    if dry_run:
        logger.info(f"[DRY-RUN] Would run: {' '.join(command)}")
        return True

    result = _run_command(command, timeout=120)
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


def stage_assets(file: str = "figma_node.json", dry_run: bool = False) -> bool:
    """Этап 5: скачивание ассетов."""
    logger.info("=== STAGE: assets ===")
    data = analyzer.load_figma_json(file)
    if not data:
        logger.warning("No figma_node.json found; skipping asset download.")
        return False

    assets = asset_downloader.collect_assets_from_tree(data)
    if not assets:
        logger.info("No assets found in design tree.")
        return True

    if dry_run:
        logger.info(f"[DRY-RUN] Would download {len(assets)} asset(s)")
        return True

    token = os.environ.get("FIGMA_TOKEN")
    url = os.environ.get("FIGMA_URL")
    if not token or not url:
        logger.warning("FIGMA_TOKEN/FIGMA_URL not set; skipping asset download.")
        return False

    file_key_match = re.search(r"/file/([^/]+)", url) or re.search(r"/design/([^/]+)", url)
    if not file_key_match:
        logger.warning("Could not parse Figma file key from FIGMA_URL; skipping asset download.")
        return False
    file_key = file_key_match.group(1)

    svg_ids = [a["id"] for a in assets if a.get("assetFormat") == "svg"]
    raster_ids = [a["id"] for a in assets if a.get("assetFormat") != "svg"]

    urls: Dict[str, str] = {}
    if raster_ids:
        urls.update(asset_downloader.get_image_urls_from_figma(file_key, raster_ids, token, format="png"))
    if svg_ids:
        urls.update(asset_downloader.get_image_urls_from_figma(file_key, svg_ids, token, format="svg"))

    downloaded = 0
    for asset in assets:
        node_id = asset["id"]
        image_url = urls.get(node_id)
        if not image_url:
            logger.warning(f"No image URL for asset {node_id} ({asset.get('name')}).")
            continue
        fmt = asset.get("assetFormat", "png")
        public_path = asset_downloader.save_asset(node_id, asset.get("name", "asset"), fmt, image_url)
        if public_path:
            logger.info(f"Saved asset {node_id} -> {public_path}")
            downloaded += 1
        else:
            logger.warning(f"Failed to download asset {node_id}.")

    logger.info(f"Downloaded {downloaded}/{len(assets)} assets.")
    return downloaded > 0 or len(assets) == 0


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

    stages_to_run = ["bootstrap", "analyze", "spec", "layout", "compose", "components", "assets"]
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

        elif stage == "layout":
            ok = stage_layout(
                file=file,
                node_id=node_id,
                output=config.get("layout_output", "layout_ast.json"),
                dry_run=dry_run,
            )
            report["stages"]["layout"] = {"success": ok}

        elif stage == "compose":
            ok = stage_compose(
                ast_file=config.get("layout_output", "layout_ast.json"),
                output=config.get("compose_output", "src/app/page.tsx"),
                title=config.get("compose_title"),
                dry_run=dry_run,
            )
            report["stages"]["compose"] = {"success": ok}

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
            ok = stage_assets(file=file, dry_run=dry_run)
            report["stages"]["assets"] = {"success": ok}

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
        description="Главный дирижёр пайплайна Figma-to-Code. Запускает bootstrap, analyze, spec, components, assets.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Запустить полный пайплайн: bootstrap, analyze, spec, layout, compose, components, assets.",
    )
    parser.add_argument(
        "--only",
        default=None,
        help="Запустить только один этап: bootstrap, analyze, spec, layout, compose, components, assets."
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
        "--spec-output",
        default="spec.md",
        help="Путь для сохранения технического задания."
    )
    parser.add_argument(
        "--layout-output",
        default="layout_ast.json",
        help="Путь для сохранения Tailwind AST от Layout Engine."
    )
    parser.add_argument(
        "--compose-output",
        default="src/app/page.tsx",
        help="Путь для сохранения Next.js-страницы от Section Composer."
    )
    parser.add_argument(
        "--compose-title",
        default=None,
        help="Заголовок страницы для Section Composer."
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
        "force_refresh": args.force,
        "api_depth": args.api_depth,
        "skip_assets": args.skip_assets,
        "spec_output": args.spec_output,
        "layout_output": args.layout_output,
        "compose_output": args.compose_output,
        "compose_title": args.compose_title,
        "file": args.file,
        "dry_run": args.dry_run,
        "verbose": args.verbose,
    }

    if args.dry_run:
        logger.info("=== DRY RUN ===")

    report = run_pipeline(config)
    save_report(report)

    success = all(stage.get("success", False) for stage in report["stages"].values())
    logger.info(f"Pipeline finished in {report['duration_seconds']}s. Overall success: {success}")
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
