"""CLI behavior from the 2026-10-29 best-practices assessment: `-h`, exit
codes, no hanging without a terminal, stdout for `report -`, `--show-source`,
and inline `wbcheck-ignore` comments."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from checker.annotate import inline_ignores
from checker.app import app
from checker.lesson_check import run_checks
from tests.test_fix import make_lesson

runner = CliRunner()
COMMANDS = ["check", "review", "report", "issues", "tui", "fix", "update", "explain", "rules", "doctor"]


def _no_terminal(monkeypatch):
    monkeypatch.setattr("checker.app._has_terminal", lambda: False)


def _episode(lesson: Path) -> Path:
    return lesson / "episodes" / "01.md"


# -- help ---------------------------------------------------------------------------------


@pytest.mark.parametrize("command", COMMANDS)
def test_short_h_is_help_like_long_help(command):
    short, long = runner.invoke(app, [command, "-h"]), runner.invoke(app, [command, "--help"])
    assert short.exit_code == 0 and "Usage" in short.output
    assert short.output == long.output


def test_top_level_help_has_exit_codes_and_where_to_report_problems():
    out = runner.invoke(app, ["-h"]).output
    assert "Exit codes" in out and "/issues" in out


@pytest.mark.parametrize("command", ["check", "fix", "report"])
def test_main_commands_show_examples(command):
    assert "Examples:" in runner.invoke(app, [command, "-h"]).output


# -- exit codes ---------------------------------------------------------------------------


def test_missing_path_is_could_not_run_not_findings(tmp_path):
    result = runner.invoke(app, ["check", str(tmp_path / "nope")])
    assert result.exit_code == 2


def test_folder_that_is_not_a_lesson_exits_2_and_writes_nothing(tmp_path):
    folder = tmp_path / "plain"
    folder.mkdir()
    (folder / "a.txt").write_text("x")
    result = runner.invoke(app, ["check", str(folder)])
    assert result.exit_code == 2 and "doesn't look like a Workbench lesson" in result.output
    assert not (folder / ".wbcheck").exists()


def test_unknown_episode_exits_2(tmp_path):
    lesson = make_lesson(tmp_path)
    assert runner.invoke(app, ["check", str(lesson), "--episode", "nope.md", "--quiet"]).exit_code == 2


def test_findings_are_still_exit_1_and_clean_is_0(tmp_path):
    lesson = make_lesson(tmp_path, front="teaching: soon\nexercises: 15")
    assert runner.invoke(app, ["check", str(lesson), "--quiet", "--fail-on", "warning"]).exit_code == 1
    assert runner.invoke(app, ["check", str(lesson), "--quiet", "--fail-on", "never"]).exit_code == 0


# -- no hanging without a terminal -------------------------------------------------------


def test_tui_without_a_terminal_exits_2(tmp_path, monkeypatch):
    _no_terminal(monkeypatch)
    result = runner.invoke(app, ["tui", str(make_lesson(tmp_path))])
    assert result.exit_code == 2 and "needs a terminal" in result.output


def test_fix_editor_mode_without_a_terminal_exits_2_before_opening_an_editor(tmp_path, monkeypatch):
    _no_terminal(monkeypatch)
    monkeypatch.setattr("subprocess.run", lambda *a, **k: pytest.fail("opened an editor"))
    result = runner.invoke(app, ["fix", str(make_lesson(tmp_path))])
    assert result.exit_code == 2 and "needs a terminal" in result.output


def test_fix_no_input_refuses_prompting_modes_even_with_a_terminal(tmp_path):
    lesson = make_lesson(tmp_path)
    for extra in ([], ["--apply"], ["--suggest", "--yes"]):
        result = runner.invoke(app, ["fix", str(lesson), "--no-input", *extra])
        assert result.exit_code == 2 and "--no-input was passed" in result.output


def test_fix_modes_that_never_prompt_work_without_a_terminal(tmp_path, monkeypatch):
    _no_terminal(monkeypatch)
    lesson = make_lesson(tmp_path)
    assert runner.invoke(app, ["fix", str(lesson), "--print"]).exit_code == 0
    assert runner.invoke(app, ["fix", str(lesson), "--annotate"]).exit_code == 0
    assert runner.invoke(app, ["fix", str(lesson), "--clean-annotations"]).exit_code == 0
    assert runner.invoke(app, ["fix", str(lesson), "--apply", "--yes", "--no-input"]).exit_code == 0


def test_fix_apply_without_yes_needs_a_terminal(tmp_path, monkeypatch):
    _no_terminal(monkeypatch)
    assert runner.invoke(app, ["fix", str(make_lesson(tmp_path)), "--apply"]).exit_code == 2


# -- report to stdout ---------------------------------------------------------------------


def test_report_json_and_md_dash_go_to_stdout_not_a_file_named_dash(tmp_path, monkeypatch):
    lesson = make_lesson(tmp_path)
    runner.invoke(app, ["check", str(lesson), "--quiet"])
    monkeypatch.chdir(tmp_path)
    as_json = runner.invoke(app, ["report", str(lesson), "--json", "-"])
    assert json.loads(as_json.stdout)["findings"]
    as_md = runner.invoke(app, ["report", str(lesson), "--md", "-"])
    assert as_md.stdout.startswith("#") or "Lesson Check Report" in as_md.stdout
    assert not (tmp_path / "-").exists()


def test_report_html_and_pdf_reject_dash(tmp_path):
    lesson = make_lesson(tmp_path)
    runner.invoke(app, ["check", str(lesson), "--quiet"])
    assert runner.invoke(app, ["report", str(lesson), "--html", "-"]).exit_code == 2
    assert runner.invoke(app, ["report", str(lesson), "--pdf", "-"]).exit_code == 2


# -- --show-source ------------------------------------------------------------------------


def test_show_source_replaces_source_and_the_old_name_still_works(tmp_path):
    lesson = make_lesson(tmp_path)
    new = runner.invoke(app, ["check", str(lesson), "--show-source"])
    old = runner.invoke(app, ["check", str(lesson), "--source"])
    assert "--source is now --show-source" in old.output
    assert "--source is now" not in new.output
    assert "Too deep" in new.stdout and "Too deep" in old.stdout
    assert "--source" not in runner.invoke(app, ["check", "-h"]).output.replace("--show-source", "")


# -- inline ignore ------------------------------------------------------------------------


def _wb213(lesson: Path):
    return [f for f in run_checks(lesson) if f.code == "WB213"]


def test_ignore_comment_suppresses_the_code_on_the_next_line_only(tmp_path):
    lesson = make_lesson(tmp_path)
    assert _wb213(lesson)
    ep = _episode(lesson)
    ep.write_text(ep.read_text().replace("#### Too deep", "<!-- wbcheck-ignore WB213: on purpose -->\n#### Too deep"))
    from checker.ignore import load_ignore

    kept, ignored = load_ignore(lesson).apply(run_checks(lesson))
    assert ignored == 1 and not [f for f in kept if f.code == "WB213"]


def test_ignore_comment_for_another_code_or_line_does_nothing(tmp_path):
    lesson = make_lesson(tmp_path)
    ep = _episode(lesson)
    ep.write_text(ep.read_text().replace("#### Too deep", "<!-- wbcheck-ignore WB404 -->\n#### Too deep"))
    from checker.ignore import load_ignore

    kept, _ = load_ignore(lesson).apply(run_checks(lesson))
    assert [f for f in kept if f.code == "WB213"]


def test_ignore_file_comment_covers_the_whole_file_and_takes_several_codes(tmp_path):
    lesson = make_lesson(tmp_path)
    ep = _episode(lesson)
    ep.write_text(ep.read_text() + "\n<!-- wbcheck-ignore-file WB213, WB401: draft episode -->\n")
    from checker.ignore import load_ignore

    kept, ignored = load_ignore(lesson).apply(run_checks(lesson))
    assert ignored >= 2 and not [f for f in kept if f.code in ("WB213", "WB401")]


def test_front_matter_ignore_uses_a_yaml_comment(tmp_path):
    text = "---\n# wbcheck-ignore WB104: minutes are approximate\nteaching: soon\n---\nbody\n"
    assert inline_ignores(text) == (set(), {3: {"WB104"}})


def test_ignore_comment_inside_a_code_block_is_not_a_directive():
    assert inline_ignores("```\n<!-- wbcheck-ignore-file WB213 -->\n```\n") == (set(), {})


def test_check_command_counts_and_hides_inline_ignored_findings(tmp_path):
    lesson = make_lesson(tmp_path)
    ep = _episode(lesson)
    ep.write_text(ep.read_text().replace("#### Too deep", "<!-- wbcheck-ignore WB213: on purpose -->\n#### Too deep"))
    result = runner.invoke(app, ["check", str(lesson), "--fail-on", "never"])
    assert "WB213" not in result.stdout


def test_ignore_comments_do_not_create_findings_of_their_own(tmp_path):
    lesson = make_lesson(tmp_path)
    before = sorted((f.code, f.location) for f in run_checks(lesson))
    ep = _episode(lesson)
    ep.write_text(ep.read_text() + "\n<!-- wbcheck-ignore WB404: it's what they're saying, isn't it, don't -->\n")
    assert sorted((f.code, f.location) for f in run_checks(lesson)) == before
