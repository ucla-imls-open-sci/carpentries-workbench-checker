"""Editor integration: SARIF and `file:line:col` output from `wbcheck report`,
`fix --annotate` / `--clean-annotations`, and the WB115 leftover-note rule."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
from typer.testing import CliRunner

from checker.annotate import annotate, blank_notes, clean_annotations, find_notes, strip_notes
from checker.app import app
from checker.editors import editor_lines, to_sarif
from checker.lesson_check import run_checks
from checker.results import default_results_path, load
from tests.test_fix import make_lesson

runner = CliRunner()

LINE_RE = re.compile(
    r"^(?P<file>.+):(?P<line>\d+):(?P<col>\d+): (?P<sev>error|warning|info) (?P<code>\S+) (?P<msg>.+)$"
)


def _checked(tmp_path: Path, **kwargs) -> Path:
    lesson = make_lesson(tmp_path, **kwargs)
    assert runner.invoke(app, ["check", str(lesson), "--quiet"]).exit_code in (0, 1)
    return lesson


# -- layer 1: output formats ----------------------------------------------------------------


def test_report_lines_to_stdout_matches_the_problem_matcher_pattern(tmp_path):
    lesson = _checked(tmp_path)
    result = runner.invoke(app, ["report", str(lesson), "--lines", "-"])
    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    assert lines
    for line in lines:
        match = LINE_RE.match(line)
        assert match, line
        assert Path(match["file"]).is_absolute() and Path(match["file"]).exists()
    assert any(" warning WB213 " in x for x in lines)


def test_lines_are_one_per_finding_and_skip_fileless_findings(tmp_path):
    lesson = _checked(tmp_path)
    findings = load(default_results_path(lesson)).findings
    out = editor_lines(findings, lesson)
    assert len(out) == len([f for f in findings if f.location])
    assert all("\n" not in x for x in out)


def test_report_sarif_is_valid_shape(tmp_path):
    lesson = _checked(tmp_path)
    target = tmp_path / "out.sarif"
    result = runner.invoke(app, ["report", str(lesson), "--sarif", str(target)])
    assert result.exit_code == 0
    log = json.loads(target.read_text())
    assert log["version"] == "2.1.0" and log["$schema"].endswith("sarif-2.1.0.json")
    [run] = log["runs"]
    assert run["tool"]["driver"]["name"] == "wbcheck"
    rule_ids = [r["id"] for r in run["tool"]["driver"]["rules"]]
    assert rule_ids == sorted(set(rule_ids))
    saved = load(default_results_path(lesson)).findings
    assert len(run["results"]) == len(saved)
    for res in run["results"]:
        assert res["level"] in ("error", "warning", "note")
        assert res["message"]["text"]
        assert res["partialFingerprints"]["wbcheckFindingId/v1"]
        if "ruleIndex" in res:
            assert run["tool"]["driver"]["rules"][res["ruleIndex"]]["id"] == res["ruleId"]
        for loc in res.get("locations", []):
            phys = loc["physicalLocation"]
            assert not phys["artifactLocation"]["uri"].startswith("/")
            assert phys["region"]["startLine"] >= 1


def test_sarif_maps_severity_and_carries_the_ai_quote(tmp_path):
    lesson = _checked(tmp_path)
    results = load(default_results_path(lesson))
    results.findings[0].quote = "quoted text"
    log = to_sarif(results, results.findings[:1])
    [res] = log["runs"][0]["results"]
    assert res["locations"][0]["physicalLocation"]["region"]["snippet"]["text"] == "quoted text"
    assert res["level"] == {"error": "error", "warning": "warning", "info": "note"}[results.findings[0].severity]


def test_report_with_only_sarif_prints_no_terminal_report(tmp_path):
    lesson = _checked(tmp_path)
    result = runner.invoke(app, ["report", str(lesson), "--sarif", "-"])
    assert result.exit_code == 0
    json.loads(result.stdout)  # stdout is the SARIF document and nothing else


def test_existing_quickfix_output_is_unchanged(tmp_path):
    lesson = make_lesson(tmp_path)
    result = runner.invoke(app, ["fix", str(lesson), "--print", "--code", "WB213"])
    assert re.search(r"01\.md:16:1: \[WB213\] heading", result.stdout)


# -- layer 2: annotations -------------------------------------------------------------------


def _episode(lesson: Path) -> Path:
    return lesson / "episodes" / "01.md"


def _annotate(lesson: Path, *extra: str):
    return runner.invoke(app, ["fix", str(lesson), "--annotate", "--min-severity", "info", *extra])


def test_annotate_adds_a_note_above_the_flagged_line_and_clean_restores_the_file(tmp_path):
    lesson = make_lesson(tmp_path)
    before = _episode(lesson).read_bytes()
    result = _annotate(lesson)
    assert result.exit_code == 0, result.output
    lines = _episode(lesson).read_text().splitlines()
    at = lines.index("#### Too deep")
    # the note, then a blank line (Pandoc needs one before a heading or list), then the flagged line
    assert lines[at - 2].startswith("<!-- wbcheck WB213: ") and lines[at - 2].endswith(" -->")
    assert lines[at - 1] == ""
    assert _episode(lesson).read_bytes() != before
    removed = runner.invoke(app, ["fix", str(lesson), "--clean-annotations"])
    assert removed.exit_code == 0
    assert _episode(lesson).read_bytes() == before


def test_annotate_is_idempotent(tmp_path):
    lesson = make_lesson(tmp_path)
    _annotate(lesson)
    once = _episode(lesson).read_bytes()
    second = _annotate(lesson)
    assert second.exit_code == 0
    assert _episode(lesson).read_bytes() == once
    assert "Added 0 note(s)" in second.output


def test_annotate_changes_no_check_result_except_wb115(tmp_path):
    lesson = make_lesson(tmp_path)
    def shape(findings):  # messages quote line numbers, which notes legitimately shift
        return sorted((f.code, re.sub(r"line \d+", "line N", f.message)) for f in findings if f.code != "WB115")

    plain = shape(run_checks(lesson))
    _annotate(lesson)
    noted = run_checks(lesson)
    assert shape(noted) == plain
    assert [f.code for f in noted].count("WB115") == len(find_notes(lesson))


def test_notes_do_not_move_later_findings_off_their_lines(tmp_path):
    lesson = make_lesson(tmp_path)
    _annotate(lesson)
    for f in run_checks(lesson):
        if f.code == "WB213":
            assert f.line is not None
            assert _episode(lesson).read_text().splitlines()[f.line - 1] == "#### Too deep"


def test_annotate_puts_front_matter_notes_in_yaml_and_keeps_it_parsing(tmp_path):
    lesson = make_lesson(tmp_path, front="teaching: soon\nexercises: 15")
    values = yaml.safe_load(_episode(lesson).read_text().split("---")[1])
    result = _annotate(lesson)
    assert result.exit_code == 0, result.output
    text = _episode(lesson).read_text()
    assert text.startswith("---\n")
    front = text.split("---")[1]
    assert re.search(r"^# wbcheck WB104: ", front, re.M)
    assert "<!--" not in front
    assert yaml.safe_load(front) == values
    assert not [f for f in run_checks(lesson) if f.code == "WB101"]


def test_annotate_puts_a_note_for_a_fenced_block_above_the_fence(tmp_path):
    lesson = make_lesson(tmp_path)
    ep = _episode(lesson)
    ep.write_text(ep.read_text().replace("#### Too deep", "```\ncode\n```\n\n#### Too deep"))
    from checker.report import Finding

    start = ep.read_text().splitlines().index("code") + 1
    finding = Finding("warning", "x", "points into a code block", location="episodes/01.md", line=start, code="WB404")
    outcome = annotate([finding], lesson)
    assert outcome.added == 1
    lines = ep.read_text().splitlines()
    fence = lines.index("```")
    assert lines[fence - 2].startswith("<!-- wbcheck WB404: ")
    assert lines[fence + 1] == "code"  # nothing was inserted inside the block


def test_annotate_goes_above_the_list_not_between_its_items(tmp_path):
    lesson = make_lesson(tmp_path)
    ep = _episode(lesson)
    ep.write_text(ep.read_text().replace("- Understand the difference between copy and sync.",
                                         "- First objective.\n- Understand the difference between copy and sync."))
    _annotate(lesson)
    lines = ep.read_text().splitlines()
    note = next(i for i, x in enumerate(lines) if "wbcheck WB401" in x)
    assert lines[note - 1] == ":::: objectives"
    assert lines[note + 1] == "" and lines[note + 2] == "- First objective."


def test_annotate_text_never_breaks_the_comment(tmp_path):
    from checker.report import Finding

    lesson = make_lesson(tmp_path)
    finding = Finding("warning", "x", "has --> and -- and <!-- inside\nand a newline", location="episodes/01.md",
                      line=16, code="WB404")
    annotate([finding], lesson)
    [note] = [x for x in _episode(lesson).read_text().splitlines() if "wbcheck WB404" in x]
    assert note.count("-->") == 1 and note.endswith("-->") and "--" not in note[4:-3]


def test_clean_removes_only_notes_wbcheck_wrote(tmp_path):
    lesson = make_lesson(tmp_path)
    ep = _episode(lesson)
    ep.write_text(ep.read_text() + "\n<!-- my own comment -->\n```\n<!-- wbcheck WB213: in a code block -->\n```\n")
    _annotate(lesson)
    removed, files = clean_annotations(lesson)
    assert removed >= 1 and files == ["episodes/01.md"]
    text = ep.read_text()
    assert "<!-- my own comment -->" in text
    assert "<!-- wbcheck WB213: in a code block -->" in text  # inside a fence: not ours to remove
    assert not find_notes(lesson)


def test_blank_notes_keeps_line_numbers():
    text = "a\n<!-- wbcheck WB213: m -->\nb\n"
    assert blank_notes(text) == "a\n\nb\n"
    assert strip_notes(text) == "a\nb\n"


def test_annotate_skips_findings_that_cannot_take_a_note(tmp_path):
    from checker.report import Finding

    lesson = make_lesson(tmp_path)
    outcome = annotate([Finding("error", "config", "config problem", location="config.yaml", line=1, code="WB004"),
                        Finding("error", "x", "no line", location="episodes/01.md", code="WB404")], lesson)
    assert outcome.added == 0 and len(outcome.skipped) == 2


def test_annotate_flags_conflict_with_other_modes(tmp_path):
    lesson = make_lesson(tmp_path)
    result = runner.invoke(app, ["fix", str(lesson), "--annotate", "--apply"])
    assert result.exit_code == 2


# -- WB115 and --fail-on annotations -------------------------------------------------------


def test_leftover_notes_warn_and_fail_only_under_fail_on_annotations(tmp_path):
    lesson = make_lesson(tmp_path, front="teaching: 15\nexercises: 15")
    ep = _episode(lesson)
    ep.write_text(ep.read_text().replace("#### Too deep", "### Fine"))
    assert runner.invoke(app, ["check", str(lesson), "--quiet"]).exit_code == 0
    ep.write_text(ep.read_text().replace("### Fine", "<!-- wbcheck WB213: left behind -->\n### Fine"))
    findings = [f for f in run_checks(lesson) if f.code == "WB115"]
    assert len(findings) == 1 and findings[0].severity == "warning" and findings[0].line == 16
    assert runner.invoke(app, ["check", str(lesson), "--quiet"]).exit_code == 0
    assert runner.invoke(app, ["check", str(lesson), "--quiet", "--fail-on", "warning"]).exit_code == 1
    assert runner.invoke(app, ["check", str(lesson), "--quiet", "--fail-on", "annotations"]).exit_code == 1
    runner.invoke(app, ["fix", str(lesson), "--clean-annotations"])
    assert runner.invoke(app, ["check", str(lesson), "--quiet", "--fail-on", "annotations"]).exit_code == 0


def test_fail_on_annotations_ignores_other_warnings(tmp_path):
    lesson = make_lesson(tmp_path)  # has warnings (WB213) but no notes
    assert runner.invoke(app, ["check", str(lesson), "--quiet", "--fail-on", "annotations"]).exit_code == 0


def test_documented_notes_inside_code_are_not_leftovers(tmp_path):
    lesson = make_lesson(tmp_path)
    ep = _episode(lesson)
    ep.write_text(ep.read_text() + "\n```\n<!-- wbcheck WB213: an example -->\n```\n")
    assert not [f for f in run_checks(lesson) if f.code == "WB115"]


def test_annotate_stays_outside_a_div_whose_first_child_is_the_flagged_heading(tmp_path):
    from checker.report import Finding

    lesson = make_lesson(tmp_path)
    ep = _episode(lesson)
    ep.write_text(ep.read_text() + "\n:::::: prereq\n\n### Buoyant Barnacle\n\ntext\n::::::\n")
    heading = ep.read_text().splitlines().index("### Buoyant Barnacle") + 1
    annotate([Finding("warning", "x", "scaffold text", location="episodes/01.md", line=heading, code="WB111")], lesson)
    lines = ep.read_text().splitlines()
    div = lines.index(":::::: prereq")
    assert lines[div - 2].startswith("<!-- wbcheck WB111: ")
    assert lines[div + 1] == "" and lines[div + 2] == "### Buoyant Barnacle"  # the title is still first in the div


def test_annotate_does_not_indent_a_note_by_one_to_three_spaces(tmp_path):
    from checker.report import Finding

    lesson = make_lesson(tmp_path)
    ep = _episode(lesson)
    ep.write_text(ep.read_text() + "\n:::::: keypoints\n - one\n - two\n::::::\n")
    line = ep.read_text().splitlines().index(" - one") + 1
    annotate([Finding("warning", "x", "placeholder", location="episodes/01.md", line=line, code="WB112")], lesson)
    assert "\n<!-- wbcheck WB112: placeholder -->\n\n - one\n" in ep.read_text()
