"""Findings model and report renderers (terminal / markdown / json / html)."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}
SEVERITY_ICON = {"error": "\033[31m❌\033[0m", "warning": "\033[33m⚠️\033[0m", "info": "ℹ️"}
SEVERITY_ICON_PLAIN = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}


@dataclass
class Finding:
    severity: str  # "error" | "warning" | "info"
    category: str  # "config" | "front-matter" | "divs" | "headings" | "links"
    message: str
    location: str | None = None  # e.g. "episodes/01-intro.md" or "config.yaml"
    hint: str | None = None

    def sort_key(self):
        return (SEVERITY_ORDER.get(self.severity, 9), self.location or "", self.category)


def summarize(findings: list[Finding]) -> dict[str, int]:
    counts = {"error": 0, "warning": 0, "info": 0}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    return counts


def render_terminal(findings: list[Finding], title: str) -> str:
    lines = [f"\033[1m{title}\033[0m"]
    counts = summarize(findings)
    lines.append(
        f"{counts['error']} error(s), {counts['warning']} warning(s), {counts['info']} note(s)"
    )
    if not findings:
        lines.append("\033[32m✅ No issues found\033[0m")
        return "\n".join(lines)

    by_location: dict[str, list[Finding]] = {}
    for f in sorted(findings, key=Finding.sort_key):
        by_location.setdefault(f.location or "general", []).append(f)

    for location, items in by_location.items():
        lines.append(f"\n\033[1m{location}\033[0m")
        for f in items:
            icon = SEVERITY_ICON.get(f.severity, "")
            lines.append(f"  {icon} [{f.category}] {f.message}")
            if f.hint:
                lines.append(f"     → {f.hint}")
    return "\n".join(lines)


def render_markdown(findings: list[Finding], title: str) -> str:
    counts = summarize(findings)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# {title}",
        "",
        f"Generated {generated} · {counts['error']} error(s), "
        f"{counts['warning']} warning(s), {counts['info']} note(s)",
        "",
    ]
    if not findings:
        lines.append("All checks passed. Nothing to address before opening a PR.")
        return "\n".join(lines) + "\n"

    by_location: dict[str, list[Finding]] = {}
    for f in sorted(findings, key=Finding.sort_key):
        by_location.setdefault(f.location or "General", []).append(f)

    for location, items in by_location.items():
        lines.append(f"## {location}")
        lines.append("")
        for f in items:
            icon = SEVERITY_ICON_PLAIN.get(f.severity, "")
            box = "- [ ]" if f.severity in ("error", "warning") else "-"
            entry = f"{box} {icon} **{f.category}** — {f.message}"
            lines.append(entry)
            if f.hint:
                lines.append(f"      *Fix:* {f.hint}")
        lines.append("")
    return "\n".join(lines)


def render_json(findings: list[Finding], title: str) -> str:
    payload = {
        "title": title,
        "generated": datetime.now(timezone.utc).isoformat(),
        "summary": summarize(findings),
        "findings": [asdict(f) for f in findings],
    }
    return json.dumps(payload, indent=2)


def render_html_via_quarto(markdown_text: str, out_path: Path) -> Path | None:
    """Render a markdown report to HTML with Quarto, if it's installed. Returns
    the output path on success, or None if quarto isn't on PATH at all (caller
    should fall back to the plain markdown/terminal report, not fail). Raises
    RuntimeError if quarto is present but the render itself fails, so that
    error doesn't get silently swallowed and mistaken for "quarto missing"."""
    if shutil.which("quarto") is None:
        return None

    with tempfile.TemporaryDirectory() as tmp:
        qmd_path = Path(tmp) / "report.qmd"
        qmd_path.write_text(
            "---\ntitle: Lesson Check Report\nformat: html\n---\n\n" + markdown_text
        )
        result = subprocess.run(
            ["quarto", "render", str(qmd_path), "--to", "html", "-o", out_path.name],
            cwd=tmp,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"quarto render failed: {result.stderr.strip()}")
        rendered = Path(tmp) / out_path.name
        out_path.write_bytes(rendered.read_bytes())
    return out_path
