"""Findings model and report renderers (terminal / markdown / json / html)."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}
SEVERITY_ICON = {"error": "\033[31m❌\033[0m", "warning": "\033[33m⚠️\033[0m", "info": "ℹ️"}
SEVERITY_ICON_PLAIN = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}

# One authoritative Workbench/Carpentries doc per check category, appended to
# a finding's hint (or standing in when there is no instance-specific hint)
# so "what's wrong" always has a "here's the rule" to go read. `boilerplate`
# has no external entry deliberately -- it's a check this tool invented, not
# something sandpaper/pegboard document, so there's no canonical page to
# point at; its instance-specific hints already carry the explanation.
CATEGORY_GUIDE_LINKS: dict[str, tuple[str, str]] = {
    "config": ("Episodes and lesson structure", "https://carpentries.github.io/sandpaper-docs/episodes.html"),
    "front-matter": ("Episode front matter", "https://carpentries.github.io/sandpaper-docs/episodes.html"),
    "divs": ("Workbench Component Guide", "https://carpentries.github.io/sandpaper-docs/component-guide.html"),
    "headings": ("Episodes and lesson structure", "https://carpentries.github.io/sandpaper-docs/episodes.html"),
    "links": ("Episodes and lesson structure", "https://carpentries.github.io/sandpaper-docs/episodes.html"),
    "objectives": (
        "CLDT: SMART objectives",
        "https://carpentries.github.io/lesson-development-training/aio.html",
    ),
    "style": (
        "Carpentries Lab reviewer checklist",
        "https://github.com/carpentries-lab/reviews/blob/main/docs/reviewer_guide.md",
    ),
}


@dataclass
class Finding:
    """One check result: a severity/category/message, where it applies, and
    optionally how to fix it."""

    severity: str  # "error" | "warning" | "info"
    category: str  # "config" | "front-matter" | "divs" | "headings" | "links"
    message: str
    location: str | None = None  # e.g. "episodes/01-intro.md" or "config.yaml"
    hint: str | None = None
    line: int | None = None  # 1-indexed source line, when the check knows one

    def sort_key(self):
        """Sort errors before warnings before info, then group by location,
        then by line within a location."""
        return (
            SEVERITY_ORDER.get(self.severity, 9),
            self.location or "",
            self.line if self.line is not None else -1,
            self.category,
        )


def summarize(findings: list[Finding]) -> dict[str, int]:
    """Count findings per severity."""
    counts = {"error": 0, "warning": 0, "info": 0}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    return counts


def _blame_suffix(location: str, blame: dict[str, str] | None) -> str:
    if not blame:
        return ""
    author = blame.get(location)
    return f" (last change authored by: {author})" if author else ""


def _guide_suffix(category: str) -> str:
    """Appendable ' (See: Label)' text for terminal/markdown, empty if the
    category has no canonical external doc."""
    entry = CATEGORY_GUIDE_LINKS.get(category)
    return f" (see: {entry[0]}, {entry[1]})" if entry else ""


def _guide_link_markdown(category: str) -> str:
    entry = CATEGORY_GUIDE_LINKS.get(category)
    return f" [{entry[0]}]({entry[1]})" if entry else ""


def _terminal_location_prefix(location: str, line: int | None) -> str:
    """`path:line` token, left plain (no ANSI) so terminals that recognize
    that pattern (VS Code's integrated terminal, several others) can turn it
    into a clickable jump-to-line link."""
    return f"{location}:{line} " if line is not None else ""


def _markdown_location_link(location: str, line: int | None, github_base: str | None) -> str:
    """A clickable `path:line` reference for the markdown report. Prefers a
    real GitHub blob URL anchored to the line (works when pasted into a PR,
    an issue, or opened in a browser); falls back to plain `path:line` text
    when the lesson isn't a GitHub repo or has no clean remote."""
    label = f"{location}:{line}" if line is not None else location
    if github_base:
        anchor = f"#L{line}" if line is not None else ""
        return f"[{label}]({github_base}/{location}{anchor})"
    return f"`{label}`"


def render_terminal(
    findings: list[Finding], title: str, blame: dict[str, str] | None = None
) -> str:
    """Colored, grouped-by-location report for a terminal."""
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
        lines.append(f"\n\033[1m{location}\033[0m{_blame_suffix(location, blame)}")
        for f in items:
            icon = SEVERITY_ICON.get(f.severity, "")
            prefix = _terminal_location_prefix(location, f.line)
            lines.append(f"  {icon} {prefix}[{f.category}] {f.message}")
            if f.hint:
                lines.append(f"     → {f.hint}{_guide_suffix(f.category)}")
            elif f.category in CATEGORY_GUIDE_LINKS:
                lines.append(f"     →{_guide_suffix(f.category)}")
    return "\n".join(lines)


def render_markdown(
    findings: list[Finding],
    title: str,
    blame: dict[str, str] | None = None,
    github_base: str | None = None,
) -> str:
    """Checkbox-list report per location, ready to paste into a PR/issue.

    `github_base` (e.g. `https://github.com/org/repo/blob/<sha>`), when
    given, turns every location:line reference into a real clickable GitHub
    link instead of plain text -- see `cli._github_blob_base`.
    """
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

    # File-level overview: one checkbox per location so progress is visible
    # at a glance before scrolling into per-finding detail.
    lines.append("## Files")
    lines.append("")
    for location, items in by_location.items():
        actionable = sum(1 for f in items if f.severity in ("error", "warning"))
        box = "- [ ]" if actionable else "-"
        count_label = f"{actionable} issue(s)" if actionable else f"{len(items)} note(s) only"
        lines.append(f"{box} [{location}](#{_anchor(location)}) — {count_label}")
    lines.append("")

    for location, items in by_location.items():
        lines.append(f"## {location}{_blame_suffix(location, blame)}")
        lines.append("")
        for f in items:
            icon = SEVERITY_ICON_PLAIN.get(f.severity, "")
            box = "- [ ]" if f.severity in ("error", "warning") else "-"
            where = _markdown_location_link(location, f.line, github_base)
            entry = f"{box} {icon} {where} **{f.category}** — {f.message}"
            lines.append(entry)
            if f.hint:
                lines.append(f"      *Fix:* {f.hint}{_guide_link_markdown(f.category)}")
            elif f.category in CATEGORY_GUIDE_LINKS:
                lines.append(f"      *Guide:*{_guide_link_markdown(f.category)}")
        lines.append("")
    return "\n".join(lines)


def _anchor(location: str) -> str:
    """Best-effort GitHub-flavored-markdown heading anchor for a `## location`
    heading, used by the file-overview checklist's links. GFM lowercases,
    strips non-word/non-hyphen/non-space characters, and turns spaces into
    hyphens; this covers lesson-path headings (letters, digits, `/`, `.`,
    `-`, `_`), which is everything that actually appears here."""
    slug = location.lower().replace("/", "").replace(".", "").replace("_", "-")
    return slug.replace(" ", "-")


def render_json(findings: list[Finding], title: str) -> str:
    """Machine-readable report, e.g. for a caller's own CI step."""
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
        # Resolve symlinks (macOS puts TemporaryDirectory() under /var, which
        # is itself a symlink to /private/var) before handing the path to
        # quarto -- otherwise quarto resolves cwd internally, computes the
        # output path relative to that resolved directory, and produces a
        # "../../../../private/..." path that doesn't match the unresolved
        # cwd we gave it, failing with a permission error on /private.
        tmp_dir = Path(tmp).resolve()
        qmd_path = tmp_dir / "report.qmd"
        qmd_path.write_text(
            "---\ntitle: Lesson Check Report\nformat:\n  html:\n    toc: true\n    "
            "embed-resources: true\n---\n\n" + markdown_text
        )
        result = subprocess.run(
            ["quarto", "render", str(qmd_path), "--to", "html", "-o", out_path.name],
            cwd=tmp_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"quarto render failed: {result.stderr.strip()}")
        rendered = tmp_dir / out_path.name
        out_path.write_bytes(rendered.read_bytes())
    return out_path
