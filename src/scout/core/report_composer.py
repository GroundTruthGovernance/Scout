"""Session report composer.

This exists to stop the manual work shown in the planning conversation —
screenshot, caption, screenshot, caption, then a final overview map and a
coordinates table, all assembled by hand in a document editor. Everything
here already lives in the project database; this just stitches it into
one Markdown file that feeds the existing Obsidian bridge (or any other
Markdown-reading tool) directly.

Deliberately scoped down for this first pass: it assembles whatever
Figures have already been saved (in order) plus a real locations table
for every active sample and pin in the project. It does **not** render an
overview map image — that needs a figure-capture pipeline (screenshotting
the map, or an EE getThumbURL-style render) that does not exist yet. That
gap is called out explicitly in the generated Markdown rather than
silently omitted, so nobody mistakes "not built yet" for "forgot."
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from scout.core import repository as repo
from scout.core.util import utc_now_iso


def _locations_table(conn: sqlite3.Connection, project_key: str) -> str:
    samples = repo.list_samples(conn, project_key)
    pins = repo.list_pins(conn, project_key)

    if not samples and not pins:
        return "_No saved samples or pins in this project yet._"

    rows = ["| ID | Type | Lon | Lat | Role / Note | Created |",
            "|---|---|---|---|---|---|"]
    for sample in samples:
        rows.append(
            f"| {sample['sample_id']} | sample | {sample['centroid_lon']} | "
            f"{sample['centroid_lat']} | {sample['sample_role'] or ''} | {sample['created_utc']} |"
        )
    for pin in pins:
        rows.append(
            f"| {pin['pin_id']} | {pin['pin_type']} | {pin['lon']} | {pin['lat']} | "
            f"{(pin['note'] or '').replace('|', '/')} | {pin['created_utc']} |"
        )
    return "\n".join(rows)


def compose_session_report(
    conn: sqlite3.Connection,
    project_key: str,
    output_path: str | Path,
    figure_ids: list[str] | None = None,
    title: str | None = None,
) -> str:
    """Builds the report Markdown, writes it to output_path, and returns
    the text (so a caller — a test, or a UI status message — doesn't have
    to re-read the file to know what was produced)."""
    figures = repo.list_figures(conn, project_key, figure_ids)
    report_title = title or f"{project_key} — session report"

    lines = [f"# {report_title}", "", f"_Generated {utc_now_iso()}_", ""]

    if not figures:
        lines.append("_No figures saved yet — this report currently only carries the locations table below._")
        lines.append("")
    for figure in figures:
        lines.append(f"## {figure['figure_title'] or figure['figure_id']}")
        if figure["image_path"]:
            lines.append(f"![{figure['figure_title'] or figure['figure_id']}]({figure['image_path']})")
        if figure["caption"]:
            lines.append("")
            lines.append(figure["caption"])
        lines.append("")

    lines.append("## Overview")
    lines.append(
        "_An overview map image is not yet generated automatically — this needs a figure-capture "
        "pipeline that does not exist in this build. The locations below are real._"
    )
    lines.append("")
    lines.append(_locations_table(conn, project_key))
    lines.append("")

    markdown = "\n".join(lines)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")

    return markdown
