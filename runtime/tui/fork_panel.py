"""Status panel for fork workers."""

from __future__ import annotations

from typing import Any

from rich.panel import Panel
from rich.table import Table

from runtime.engine.fork_pool import ForkPool, WorkerStatus


def build_fork_panel(pool: ForkPool | None) -> Panel:
    """Build a Rich panel showing fork worker statuses."""
    table = Table(
        title="Fork Workers",
        show_header=True,
        header_style="bold cyan",
        expand=True,
    )
    table.add_column("Worker ID", style="dim", no_wrap=True)
    table.add_column("Task", no_wrap=False)
    table.add_column("Status", justify="center")
    table.add_column("Elapsed (s)", justify="right")

    if pool is None:
        table.add_row("—", "No active fork pool", "—", "—")
        return Panel(table, title="[bold]/agents[/bold]", border_style="blue")

    rows = pool.status_table()
    if not rows:
        table.add_row("—", "No workers in pool", "—", "—")
    for row in rows:
        status = row.get("status", WorkerStatus.PENDING)
        color = _status_color(status)
        table.add_row(
            row.get("worker_id", "?"),
            row.get("description", "")[:40],
            f"[{color}]{status}[/{color}]",
            f"{row.get('elapsed', 0.0):.2f}",
        )

    return Panel(table, title="[bold]/agents[/bold]", border_style="blue")


def _status_color(status: Any) -> str:
    if status == WorkerStatus.DONE:
        return "green"
    if status == WorkerStatus.RUNNING:
        return "yellow"
    if status in (WorkerStatus.ERROR, WorkerStatus.CANCELLED):
        return "red"
    return "dim"
