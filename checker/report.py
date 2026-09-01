"""Findings model and report renderers (terminal / markdown / json / html)."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

from checker import __version__

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


@dataclass
class LessonMetadata:
    """Lesson identity for the report header, read from config.yaml and (if
    present) CITATION.cff -- see lesson_check.read_lesson_metadata(). Purely
    descriptive context for whoever reads the report, not a check result;
    every field is optional since not every lesson has all of this filled
    in (or a CITATION.cff at all)."""

    title: str | None = None
    carpentry: str | None = None  # friendly name, e.g. "Library Carpentry"
    life_cycle: str | None = None
    license: str | None = None
    source: str | None = None
    contact: str | None = None
    created: str | None = None
    authors: list[str] = field(default_factory=list)

    def has_content(self) -> bool:
        """Whether there's anything worth rendering -- false when config.yaml
        itself was missing or empty, so the header block can be skipped
        entirely rather than printed blank."""
        return bool(self.title or self.carpentry or self.source or self.authors)


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


def _lesson_metadata_lines(
    metadata: LessonMetadata | None, bold_open: str = "", bold_close: str = ""
) -> list[str]:
    """Plain-text lesson-identity lines shared by terminal/markdown: title
    (wrapped in the caller's own bold markup), carpentry/life cycle/license
    tags, source repo, authors, contact. Empty list if there's nothing to
    show -- e.g. config.yaml was missing or empty."""
    if metadata is None or not metadata.has_content():
        return []
    lines = []
    header_bits = []
    if metadata.title:
        header_bits.append(f"{bold_open}{metadata.title}{bold_close}")
    tags = [t for t in (metadata.carpentry,) if t]
    if metadata.life_cycle:
        tags.append(f"life cycle: {metadata.life_cycle}")
    if metadata.license:
        tags.append(f"license: {metadata.license}")
    if tags:
        header_bits.append(f"({', '.join(tags)})")
    if header_bits:
        lines.append(" ".join(header_bits))
    if metadata.source:
        lines.append(f"Source: {metadata.source}")
    if metadata.authors:
        lines.append(f"Authors: {', '.join(metadata.authors)}")
    if metadata.contact:
        lines.append(f"Contact: {metadata.contact}")
    return lines


def render_terminal(
    findings: list[Finding],
    title: str,
    blame: dict[str, str] | None = None,
    metadata: LessonMetadata | None = None,
) -> str:
    """Colored, grouped-by-location report for a terminal."""
    lines = [f"\033[1m{title}\033[0m"]
    lines.extend(_lesson_metadata_lines(metadata, bold_open="\033[1m", bold_close="\033[0m"))
    if metadata is not None and metadata.has_content():
        lines.append("")
    counts = summarize(findings)
    lines.append(
        f"carpentries-workbench-checker v{__version__} · {counts['error']} error(s), "
        f"{counts['warning']} warning(s), {counts['info']} note(s)"
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
    metadata: LessonMetadata | None = None,
) -> str:
    """Checkbox-list report per location, ready to paste into a PR/issue.

    `github_base` (e.g. `https://github.com/org/repo/blob/<sha>`), when
    given, turns every location:line reference into a real clickable GitHub
    link instead of plain text -- see `cli._github_blob_base`. `metadata`
    (see `LessonMetadata`), when given, adds a lesson-identity block (title,
    carpentry, authors, ...) below the report title.
    """
    counts = summarize(findings)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"# {title}", ""]
    metadata_lines = _lesson_metadata_lines(metadata, bold_open="**", bold_close="**")
    if metadata_lines:
        # Trailing double-space = a CommonMark/GFM hard line break, so these
        # render as separate lines instead of collapsing into one reflowed
        # paragraph (Markdown treats consecutive non-blank lines as the same
        # paragraph otherwise).
        lines.extend(f"{line}  " for line in metadata_lines)
        lines.append("")
    lines.append(
        f"Generated {generated} by carpentries-workbench-checker v{__version__} · "
        f"{counts['error']} error(s), {counts['warning']} warning(s), {counts['info']} note(s)"
    )
    lines.append("")
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


def render_json(
    findings: list[Finding], title: str, metadata: LessonMetadata | None = None
) -> str:
    """Machine-readable report, e.g. for a caller's own CI step."""
    payload = {
        "title": title,
        "generated": datetime.now(timezone.utc).isoformat(),
        "generated_by": {"name": "carpentries-workbench-checker", "version": __version__},
        "lesson": asdict(metadata) if metadata is not None else None,
        "summary": summarize(findings),
        "findings": [asdict(f) for f in findings],
    }
    return json.dumps(payload, indent=2)


# Pandoc format options per target, keyed the same as quarto's own `--to`.
_QUARTO_FORMAT_OPTIONS: dict[str, dict] = {
    "html": {"toc": True, "embed-resources": True},
    "pdf": {"toc": True},
}


def _render_via_quarto(
    markdown_text: str, out_path: Path, to: str, report_title: str
) -> Path | None:
    """Shared by render_html_via_quarto/render_pdf_via_quarto: write the report
    as a .qmd with the given pandoc `format:` block, render it to `to`
    ("html"/"pdf"), and copy the result to out_path. Returns None if quarto
    isn't on PATH at all (caller should fall back to the plain markdown/
    terminal report, not fail). Raises RuntimeError if quarto is present but
    the render itself fails -- e.g. no LaTeX distribution for a PDF render --
    so that doesn't get silently swallowed and mistaken for "quarto missing"."""
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
        # yaml.safe_dump, not an f-string, because report_title is a lesson's
        # actual title -- arbitrary text that can contain colons, quotes, or
        # unicode that would otherwise break the YAML front matter.
        front_matter = yaml.safe_dump(
            {"title": report_title, "format": {to: _QUARTO_FORMAT_OPTIONS[to]}},
            sort_keys=False,
            allow_unicode=True,
        )
        qmd_path.write_text(f"---\n{front_matter}---\n\n" + markdown_text)
        result = subprocess.run(
            ["quarto", "render", str(qmd_path), "--to", to, "-o", out_path.name],
            cwd=tmp_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"quarto render failed: {result.stderr.strip()}")
        rendered = tmp_dir / out_path.name
        out_path.write_bytes(rendered.read_bytes())
    return out_path


def render_html_via_quarto(
    markdown_text: str, out_path: Path, report_title: str = "Lesson Check Report"
) -> Path | None:
    """Render a markdown report to HTML with Quarto, if it's installed. See
    `_render_via_quarto` for the None/RuntimeError contract."""
    return _render_via_quarto(markdown_text, out_path, "html", report_title)


def render_pdf_via_quarto(
    markdown_text: str, out_path: Path, report_title: str = "Lesson Check Report"
) -> Path | None:
    """Render a markdown report to PDF with Quarto, if it's installed and a
    LaTeX distribution is available (`quarto install tinytex`, or an existing
    MacTeX/TeX Live install on PATH). See `_render_via_quarto` for the
    None/RuntimeError contract -- a missing LaTeX engine surfaces as a
    RuntimeError with quarto's own error text, not a silent None, since
    quarto being on PATH doesn't guarantee PDF rendering works."""
    return _render_via_quarto(markdown_text, out_path, "pdf", report_title)
