"""Findings in the formats editors read: a plain `file:line:col: severity
code message` line per finding (VS Code / Positron problem matchers, grep-style
tools), and SARIF 2.1.0 (the VS Code SARIF Viewer, GitHub code scanning).

Both read a saved Results, so they work from `.wbcheck/results.json` without
re-checking. The vim/nvim quickfix lines live in checker/fix.py and are
unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path

from checker import __version__
from checker.report import Finding
from checker.results import Results
from checker.rules import RULES

SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
TOOL_URI = "https://github.com/ucla-imls-open-sci/carpentries-workbench-checker"
_SARIF_LEVEL = {"error": "error", "warning": "warning", "info": "note"}


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _sorted(findings: list[Finding]) -> list[Finding]:
    return sorted(findings, key=lambda f: (f.location or "", f.line or 0, f.code or ""))


def editor_lines(findings: list[Finding], lesson_dir: Path | None) -> list[str]:
    """`path:line:col: severity CODE message`, one per finding that has a
    file, in file/line order. The path is absolute when the lesson directory
    is known (so a matcher works from any working directory), else
    lesson-relative. The column is always 1: checks know lines, not columns.
    The fix hint is left out; `wbcheck explain CODE` has it."""
    lines = []
    for f in _sorted(findings):
        if not f.location:
            continue
        path = lesson_dir / f.location if lesson_dir else Path(f.location)
        lines.append(f"{path}:{f.line or 1}:1: {f.severity} {f.code or f.category} {_one_line(f.message)}")
    return lines


def _sarif_rules(findings: list[Finding]) -> list[dict]:
    """Descriptors for the rules the findings use, in code order."""
    descriptors = []
    for code in sorted({f.code for f in findings if f.code in RULES}):
        rule = RULES[code]
        descriptors.append({
            "id": rule.code,
            "name": rule.name,
            "shortDescription": {"text": rule.title},
            "fullDescription": {"text": f"{rule.checks} {rule.why}"},
            "help": {"text": rule.response},
            "defaultConfiguration": {"level": _SARIF_LEVEL[rule.default_severity]},
            "properties": {"topic": rule.topic, "authority": rule.authority, "detection": rule.detection},
        })
    return descriptors


def to_sarif(results: Results, findings: list[Finding] | None = None) -> dict:
    """A SARIF 2.1.0 log of `findings` (default: all of `results`). File
    locations are lesson-relative URIs against %SRCROOT%, so a viewer opened
    on the lesson folder resolves them."""
    findings = _sorted(results.findings if findings is None else findings)
    descriptors = _sarif_rules(findings)
    index = {d["id"]: i for i, d in enumerate(descriptors)}
    sarif_results = []
    for f in findings:
        rule_id = f.code or f.category
        message = _one_line(f.message)
        if f.hint:
            message += f" Fix: {_one_line(f.hint)}"
        result: dict = {
            "ruleId": rule_id,
            "level": _SARIF_LEVEL.get(f.severity, "note"),
            "message": {"text": message},
            "partialFingerprints": {"wbcheckFindingId/v1": f.id},
        }
        if f.code in index:
            result["ruleIndex"] = index[f.code]
        if f.location:
            region: dict = {"startLine": f.line or 1}
            if f.quote:
                region["snippet"] = {"text": f.quote}
            result["locations"] = [{
                "physicalLocation": {
                    "artifactLocation": {"uri": Path(f.location).as_posix(), "uriBaseId": "%SRCROOT%"},
                    "region": region,
                }
            }]
        sarif_results.append(result)
    run: dict = {
        "tool": {"driver": {
            "name": "wbcheck",
            "fullName": "carpentries-workbench-checker",
            "version": __version__,
            "informationUri": TOOL_URI,
            "rules": descriptors,
        }},
        "results": sarif_results,
    }
    if results.lesson_dir:
        run["originalUriBaseIds"] = {"%SRCROOT%": {"uri": Path(results.lesson_dir).as_uri() + "/"}}
    return {"$schema": SARIF_SCHEMA, "version": "2.1.0", "runs": [run]}


def sarif_text(results: Results, findings: list[Finding] | None = None) -> str:
    """`to_sarif` as indented JSON with a trailing newline."""
    return json.dumps(to_sarif(results, findings), indent=2) + "\n"
