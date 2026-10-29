"""Inline notes: `wbcheck fix --annotate` writes each finding into the lesson
file as a comment above the flagged block, and `--clean-annotations` removes
exactly those lines again.

    <!-- wbcheck WB213: heading skips a level (h2 to h4) -->      in Markdown
    # wbcheck WB104: teaching is not a number of minutes           in YAML front matter

A note is one whole line that starts with the `wbcheck CODE:` marker, so
cleaning is the exact inverse of annotating: annotate then clean gives back
the same bytes. Notes are comments, so Workbench doesn't render them.

Where a note goes, so it can't change what the lesson says or builds:
  - never inside a fenced code block: above the opening fence instead
  - in front matter, a YAML comment above the field's key line, and only if
    the front matter still parses to the same values
  - above the first line of the paragraph or list the finding is in, because
    a comment between list items splits the list in some renderers
  - followed by one blank line, because Pandoc doesn't see a list or heading
    that starts right after a comment (found by building a real lesson)
  - above the div instead of between the div's opening fence and its heading,
    because Workbench takes a callout's first heading as its title (found by
    building a real lesson)
  - at column 0 unless the block is indented 4+ columns: a short indent
    makes some renderers emit an empty paragraph
Findings with no line, and files that aren't .md/.Rmd, are skipped and counted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from checker.report import Finding

MARKDOWN_SUFFIXES = (".md", ".Rmd")
LESSON_DIRS = ("episodes", "learners", "instructors", "profiles")
MAX_NOTE_TEXT = 200

_HTML_NOTE_RE = re.compile(r"^(?P<indent>\s*)<!-- wbcheck (?P<code>[A-Z]+\d+): (?P<text>.*) -->\s*$")
_CODES = r"(?P<codes>[A-Z]+\d+(?:\s*,\s*[A-Z]+\d+)*)"
_REASON = r"(?:\s*:\s*(?P<reason>.*?))?"
# `<!-- wbcheck-ignore WB404: quoted data -->`, or `# wbcheck-ignore WB104: ...` in front matter
_HTML_IGNORE_RE = re.compile(rf"^\s*<!--\s*wbcheck-ignore(?P<file>-file)?\s+{_CODES}{_REASON}\s*-->\s*$")
_YAML_IGNORE_RE = re.compile(rf"^#\s*wbcheck-ignore(?P<file>-file)?\s+{_CODES}{_REASON}\s*$")
_YAML_NOTE_RE = re.compile(r"^# wbcheck (?P<code>[A-Z]+\d+): (?P<text>.*?)\s*$")
_DIV_FENCE_RE = re.compile(r"^\s*:{3,}")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}(\s|$)")
_DIV_OPEN_RE = re.compile(r"^\s*:{3,}[ \t]*[^:\s]")  # an opening fence has attributes; a closing one is bare colons
_TOP_KEY_RE = re.compile(r"^[A-Za-z_][\w-]*\s*:")


# -- finding and reading notes ---------------------------------------------------


def _front_matter_end(lines: list[str]) -> int | None:
    """0-based index of the closing `---`, or None if there's no front matter."""
    if not lines or lines[0].rstrip("\r") != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r") == "---":
            return i
    return None


def _note_match(lines: list[str], i: int, fm_end: int | None, starts: list[int | None]):
    """The note regex match for line `i`, or None. A YAML-form note counts
    only inside front matter, an HTML-form one only outside it and outside
    code fences, so a lesson that documents wbcheck isn't touched."""
    if fm_end is not None and i <= fm_end:
        return _YAML_NOTE_RE.match(lines[i].rstrip("\r")) if i > 0 else None
    if starts[i] is not None:
        return None
    return _HTML_NOTE_RE.match(lines[i].rstrip("\r"))


def _directive_match(lines: list[str], i: int, fm_end: int | None, starts: list[int | None]):
    """The inline-ignore regex match for line `i`, or None (same placement
    rules as `_note_match`)."""
    if fm_end is not None and i <= fm_end:
        return _YAML_IGNORE_RE.match(lines[i].rstrip("\r")) if i > 0 else None
    if starts[i] is not None:
        return None
    return _HTML_IGNORE_RE.match(lines[i].rstrip("\r"))


def inline_ignores(text: str) -> tuple[set[str], dict[int, set[str]]]:
    """Inline `wbcheck-ignore` directives in one file: the codes ignored for
    the whole file (`wbcheck-ignore-file`), and codes ignored on a given
    1-indexed line (the next non-blank line after the directive)."""
    if "wbcheck-ignore" not in text:
        return set(), {}
    lines, fm_end, starts = _scan(text)
    file_codes: set[str] = set()
    by_line: dict[int, set[str]] = {}
    for i in range(len(lines)):
        match = _directive_match(lines, i, fm_end, starts)
        if not match:
            continue
        codes = {c.strip() for c in match["codes"].split(",")}
        if match["file"]:
            file_codes |= codes
            continue
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        by_line.setdefault(j + 1, set()).update(codes)
    return file_codes, by_line


def _scan(text: str) -> tuple[list[str], int | None, list[int | None]]:
    from checker.lesson_check import _code_fence_starts

    lines = text.split("\n")
    fm_end = _front_matter_end(lines)
    body_from = (fm_end + 1) if fm_end is not None else 0
    starts: list[int | None] = [None] * body_from
    starts += [None if s is None else s + body_from for s in _code_fence_starts(lines[body_from:])]
    return lines, fm_end, starts


def blank_notes(text: str) -> str:
    """`text` with each note and inline-ignore line emptied (not removed), so
    checks never see them and every line number is unchanged."""
    if "wbcheck" not in text:
        return text
    lines, fm_end, starts = _scan(text)
    for i in range(len(lines)):
        if _note_match(lines, i, fm_end, starts) or _directive_match(lines, i, fm_end, starts):
            lines[i] = ""
    return "\n".join(lines)


def _strip(text: str) -> tuple[str, int]:
    """`text` without notes, and how many were removed. A Markdown note
    takes the blank line written after it with it (see `annotate_file`)."""
    if "wbcheck " not in text:
        return text, 0
    lines, fm_end, starts = _scan(text)
    kept, removed, skip_blank = [], 0, False
    for i, ln in enumerate(lines):
        if skip_blank:
            skip_blank = False
            if not ln.strip():
                continue
        if _note_match(lines, i, fm_end, starts):
            removed += 1
            skip_blank = fm_end is None or i > fm_end
            continue
        kept.append(ln)
    return "\n".join(kept), removed


def strip_notes(text: str) -> str:
    """`text` with note lines removed: what a person or model should read."""
    return _strip(text)[0]


def lesson_markdown_files(lesson_dir: Path) -> list[Path]:
    """The .md/.Rmd files wbcheck reads or annotates: the lesson's root files
    and episodes/, learners/, instructors/, profiles/ (not their subfolders)."""
    folders = [lesson_dir, *(lesson_dir / d for d in LESSON_DIRS)]
    found = (p for d in folders if d.is_dir() for p in d.iterdir())
    return sorted(p for p in found if p.is_file() and p.suffix in MARKDOWN_SUFFIXES)


@dataclass(frozen=True)
class Note:
    """One note found in a file."""

    location: str  # lesson-relative path
    line: int  # 1-indexed
    code: str
    text: str


def find_notes(lesson_dir: Path) -> list[Note]:
    """Every wbcheck note in the lesson's Markdown files, in file/line order."""
    notes = []
    for path in lesson_markdown_files(lesson_dir):
        text = path.read_text(errors="replace")
        if "wbcheck " not in text:
            continue
        lines, fm_end, starts = _scan(text)
        for i in range(len(lines)):
            match = _note_match(lines, i, fm_end, starts)
            if match:
                notes.append(Note(str(path.relative_to(lesson_dir)), i + 1, match["code"], match["text"]))
    return notes


# -- writing notes ---------------------------------------------------------------


def note_text(finding: Finding) -> str:
    """The message as a note body: one line, no `--` (illegal inside an HTML
    comment), capped in length. `wbcheck explain CODE` has the rest."""
    text = " ".join(finding.message.split())
    text = re.sub(r" on line \d+", "", text)  # later notes shift lines; the note's position says where
    text = re.sub(r"-{2,}", "-", text).replace("<!", "<")
    if len(text) > MAX_NOTE_TEXT:
        text = text[: MAX_NOTE_TEXT - 3].rstrip() + "..."
    return text


@dataclass
class AnnotateResult:
    """What `annotate` did, by outcome."""

    added: int = 0
    present: int = 0  # the rule already has a note at that spot
    skipped: list[str] = field(default_factory=list)  # human-readable reasons
    files: list[str] = field(default_factory=list)  # lesson-relative paths changed


def _front_matter_insert(lines: list[str], idx: int, fm_end: int) -> int:
    """Where a YAML comment for a finding on line `idx` goes: above the
    nearest top-level key at or above it, never inside a multi-line value."""
    if idx == 0:
        return 1
    p = min(idx, fm_end)
    while p > 1 and not _TOP_KEY_RE.match(lines[p]):
        p -= 1
    return p


def _body_insert(lines: list[str], idx: int, fm_end: int | None, starts: list[int | None]) -> int:
    """Where an HTML comment for a finding on line `idx` goes."""
    fence_start = starts[idx]
    if fence_start is not None:
        return fence_start  # above the opening fence, never inside the block
    p = idx
    if not lines[p].strip():
        return p
    lo = (fm_end + 1) if fm_end is not None else 0
    while p > lo:
        prev = lines[p - 1]
        if (
            not prev.strip()
            or starts[p - 1] is not None
            or _DIV_FENCE_RE.match(prev)
            or _HEADING_RE.match(prev)
            or _HTML_NOTE_RE.match(prev.rstrip("\r"))
        ):
            break
        p -= 1
    if _HEADING_RE.match(lines[p]):
        # the heading is a div's title if it comes first in the div: stay outside the div
        while True:
            k = p - 1
            while k >= lo and not lines[k].strip():
                k -= 1
            if k < lo or starts[k] is not None or not _DIV_OPEN_RE.match(lines[k]):
                break
            p = k
    return p


def _front_matter_values(lines: list[str], fm_end: int):
    try:
        return yaml.safe_load("\n".join(lines[1:fm_end]))
    except yaml.YAMLError:
        return None


def annotate_file(path: Path, findings: list[Finding], result: AnnotateResult, rel: str) -> None:
    """Insert notes for `findings` (all located in `path`) and record the outcome."""
    text = path.read_text()
    lines, fm_end, starts = _scan(text)
    eol = "\r" if lines and lines[0].endswith("\r") else ""
    inserts: dict[int, list[str]] = {}
    count = 0
    for f in findings:
        label = f"{rel}:{f.line or '?'} {f.code}"
        if f.line is None or not 1 <= f.line <= len(lines):
            result.skipped.append(f"{label} has no line to annotate")
            continue
        if fm_end is not None and f.line - 1 <= fm_end:
            p = _front_matter_insert(lines, f.line - 1, fm_end)
            new = [f"# wbcheck {f.code}: {note_text(f)}{eol}"]
        else:
            p = _body_insert(lines, f.line - 1, fm_end, starts)
            indent = re.match(r"[ \t]*", lines[p])[0]
            indent = indent if len(indent.expandtabs(4)) >= 4 else ""
            new = [f"{indent}<!-- wbcheck {f.code}: {note_text(f)} -->{eol}", eol]
        # already noted: a note for this rule in the run of notes above p
        # (a Markdown note is followed by its blank line)
        above, j = [], p - 1
        while j >= 0:
            if not lines[j].strip() and j > 0 and _note_match(lines, j - 1, fm_end, starts):
                j -= 1
            if not (found := _note_match(lines, j, fm_end, starts)):
                break
            above.append(found["code"])
            j -= 1
        if f.code in above or any(f"wbcheck {f.code}:" in x for x in inserts.get(p, [])):
            result.present += 1
            continue
        inserts.setdefault(p, []).extend(new)
        count += 1
    if not inserts:
        return
    out = list(lines)
    for p in sorted(inserts, reverse=True):
        out[p:p] = inserts[p]
    if fm_end is not None:
        new_end = _front_matter_end(out)
        if new_end is None or _front_matter_values(out, new_end) != _front_matter_values(lines, fm_end):
            result.skipped.append(f"{rel}: a front-matter note would change how the YAML parses; file left alone")
            return
    path.write_text("\n".join(out))
    result.added += count
    result.files.append(rel)


def annotate(findings: list[Finding], lesson_dir: Path) -> AnnotateResult:
    """Write a note for each finding that can take one. Safe to repeat: a
    rule that already has a note at that spot is counted, not added again."""
    result = AnnotateResult()
    by_file: dict[str, list[Finding]] = {}
    for f in findings:
        # WB115 is the note itself, and a stale AI finding's line may have moved
        if f.code == "WB115" or f.stale or not f.location:
            continue
        path = lesson_dir / f.location
        if path.suffix not in MARKDOWN_SUFFIXES or not path.is_file():
            result.skipped.append(f"{f.location} {f.code} is not in a .md/.Rmd file")
            continue
        by_file.setdefault(f.location, []).append(f)
    for rel, group in sorted(by_file.items()):
        annotate_file(lesson_dir / rel, group, result, rel)
    return result


def clean_annotations(lesson_dir: Path) -> tuple[int, list[str]]:
    """Remove every wbcheck note from the lesson's Markdown files. Returns
    the count removed and the lesson-relative paths changed."""
    removed, changed = 0, []
    for path in lesson_markdown_files(lesson_dir):
        text = path.read_text()
        if "wbcheck " not in text:
            continue
        stripped, count = _strip(text)
        if count:
            removed += count
            path.write_text(stripped)
            changed.append(str(path.relative_to(lesson_dir)))
    return removed, changed
