"""Regression corpus: small lessons under tests/corpus/, each with the exact
findings wbcheck must report (expected.json), and two lessons that must
report nothing. A check that starts or stops firing, moves a line, or has its
message reworded (which changes the finding ID, see STD-06) fails here.

Update after a deliberate change:  WBCHECK_UPDATE_CORPUS=1 pixi run pytest tests/test_corpus.py
then read the diff of the expected.json files before committing.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from checker.lesson_check import run_checks
from checker.rules import RULES

CORPUS = Path(__file__).parent / "corpus"
CASES = sorted(p.name for p in CORPUS.iterdir() if (p / "lesson").is_dir())
MUST_BE_CLEAN = ("clean", "tricky-valid")
# WB012 is raised only for `--episode` naming a missing file, not by a lesson's content.
NOT_FROM_CONTENT = {"WB012"}


def _actual(case: str) -> list[list]:
    lesson = CORPUS / case / "lesson"
    rows = []
    for f in run_checks(lesson):
        # WB011's location is the lesson directory itself, and so is machine-specific, as is its ID
        local = f.location == str(lesson)
        rows.append([f.code, f.severity, "." if local else f.location, f.line, None if local else f.id])
    return sorted(rows, key=lambda r: (r[2] or "", r[3] or 0, r[0], r[4] or ""))


@pytest.mark.parametrize("case", CASES)
def test_findings_match_expected(case):
    expected_path = CORPUS / case / "expected.json"
    actual = _actual(case)
    if os.environ.get("WBCHECK_UPDATE_CORPUS"):
        expected_path.write_text(json.dumps(actual, indent=1) + "\n")
    expected = json.loads(expected_path.read_text())
    assert actual == expected, f"{case}: findings changed; if that is intended, see this file's docstring"


@pytest.mark.parametrize("case", MUST_BE_CLEAN)
def test_clean_lessons_stay_clean(case):
    assert _actual(case) == [], f"{case} must report nothing: it guards against false positives"


def test_every_content_rule_is_exercised_by_some_case():
    seen = {row[0] for case in CASES for row in json.loads((CORPUS / case / "expected.json").read_text())}
    wanted = {c for c in RULES if c.startswith("WB")} - NOT_FROM_CONTENT
    assert wanted - seen == set(), "add a corpus case that triggers these rules"


# -- no command hangs without a terminal ---------------------------------------------------

ENTRY = "from checker.app import main; main()"
# (arguments, exit codes that count as "ran and finished")
NON_INTERACTIVE = [
    (["check", "LESSON", "--quiet"], {0, 1}),
    (["report", "LESSON", "--json", "-"], {0}),
    (["report", "LESSON", "--sarif", "-"], {0}),
    (["report", "LESSON", "--lines", "-"], {0}),
    (["explain", "WB213"], {0}),
    (["rules"], {0}),
    (["issues", "LESSON"], {0, 2}),
    (["fix", "LESSON", "--print"], {0}),
    (["fix", "LESSON", "--apply", "--yes"], {0}),
    (["fix", "LESSON", "--annotate"], {0}),
    (["fix", "LESSON"], {2}),
    (["fix", "LESSON", "--apply"], {2}),
    (["tui", "LESSON"], {2}),
]


@pytest.mark.parametrize("args,codes", NON_INTERACTIVE, ids=lambda v: " ".join(v) if isinstance(v, list) else "")
def test_command_finishes_with_stdin_closed(args, codes, tmp_path):
    import shutil

    lesson = tmp_path / "lesson"
    shutil.copytree(CORPUS / "front-matter" / "lesson", lesson)
    argv = [sys.executable, "-c", ENTRY, *[str(lesson) if a == "LESSON" else a for a in args]]
    if args[0] != "check":
        subprocess.run([sys.executable, "-c", ENTRY, "check", str(lesson), "--quiet"], check=False,
                       stdin=subprocess.DEVNULL, capture_output=True, timeout=30)
    try:
        done = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=20, text=True)
    except subprocess.TimeoutExpired:
        pytest.fail(f"`wbcheck {' '.join(args)}` was still running after 20 s with no terminal")
    assert done.returncode in codes, done.stderr[-400:]
