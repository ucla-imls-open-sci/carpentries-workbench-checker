"""Unit tests for report rendering, including --blame annotation."""

from __future__ import annotations

import json

from checker import __version__
from checker.report import Finding, LessonMetadata, render_json, render_markdown, render_terminal


def test_render_markdown_blame_annotates_heading():
    findings = [Finding("error", "boilerplate", "still scaffold", location="episodes/ep.md")]
    text = render_markdown(
        findings, "Report", blame={"episodes/ep.md": "Jose Niño, 2026-08-28, a1b2c3d"}
    )
    assert (
        "## episodes/ep.md (last change authored by: Jose Niño, 2026-08-28, a1b2c3d)" in text
    )


def test_render_markdown_no_blame_arg_is_unchanged():
    findings = [Finding("error", "boilerplate", "still scaffold", location="episodes/ep.md")]
    text = render_markdown(findings, "Report")
    assert "## episodes/ep.md\n" in text
    assert "last change authored by" not in text


def test_render_markdown_blame_missing_location_is_silent():
    findings = [Finding("error", "boilerplate", "still scaffold", location="episodes/ep.md")]
    text = render_markdown(findings, "Report", blame={"episodes/other.md": "Someone Else"})
    assert "## episodes/ep.md\n" in text
    assert "last change authored by" not in text


def test_render_terminal_blame_annotates_heading():
    findings = [Finding("error", "boilerplate", "still scaffold", location="episodes/ep.md")]
    text = render_terminal(
        findings, "Report", blame={"episodes/ep.md": "Karla Padilla, 2026-08-28, deadbee"}
    )
    assert "(last change authored by: Karla Padilla, 2026-08-28, deadbee)" in text


# -- structured line numbers + clickable links -------------------------------


def test_render_terminal_includes_path_colon_line_token():
    findings = [Finding("error", "headings", "bad heading", location="episodes/ep.md", line=12)]
    text = render_terminal(findings, "Report")
    assert "episodes/ep.md:12 " in text


def test_render_terminal_no_line_omits_token():
    findings = [Finding("error", "headings", "bad heading", location="episodes/ep.md")]
    text = render_terminal(findings, "Report")
    assert "episodes/ep.md:" not in text


def test_render_markdown_no_github_base_uses_plain_code_span():
    findings = [Finding("error", "headings", "bad heading", location="episodes/ep.md", line=12)]
    text = render_markdown(findings, "Report")
    assert "`episodes/ep.md:12`" in text


def test_render_markdown_github_base_makes_blob_link_with_line_anchor():
    findings = [Finding("error", "headings", "bad heading", location="episodes/ep.md", line=12)]
    text = render_markdown(
        findings, "Report", github_base="https://github.com/org/repo/blob/abc123"
    )
    assert (
        "[episodes/ep.md:12](https://github.com/org/repo/blob/abc123/episodes/ep.md#L12)" in text
    )


def test_render_markdown_github_base_no_line_omits_anchor():
    findings = [Finding("error", "config", "bad config", location="config.yaml")]
    text = render_markdown(
        findings, "Report", github_base="https://github.com/org/repo/blob/abc123"
    )
    assert "[config.yaml](https://github.com/org/repo/blob/abc123/config.yaml)" in text


# -- category guide links -----------------------------------------------------


def test_render_terminal_appends_guide_link_when_no_hint():
    findings = [Finding("warning", "divs", "unrecognized div", location="episodes/ep.md")]
    text = render_terminal(findings, "Report")
    assert "Workbench Component Guide" in text
    assert "https://carpentries.github.io/sandpaper-docs/component-guide.html" in text


def test_render_terminal_appends_guide_link_after_hint():
    findings = [
        Finding("warning", "divs", "unrecognized div", location="episodes/ep.md", hint="fix it")
    ]
    text = render_terminal(findings, "Report")
    assert "fix it (see: Workbench Component Guide" in text


def test_render_terminal_boilerplate_has_no_guide_link():
    # boilerplate is a tool-invented check with no canonical external doc --
    # see the comment on CATEGORY_GUIDE_LINKS in report.py.
    findings = [Finding("warning", "boilerplate", "still scaffold", location="episodes/ep.md")]
    text = render_terminal(findings, "Report")
    assert "carpentries.github.io" not in text
    assert "github.com" not in text


def test_render_markdown_guide_link_is_markdown_formatted():
    findings = [Finding("warning", "divs", "unrecognized div", location="episodes/ep.md")]
    text = render_markdown(findings, "Report")
    assert (
        "[Workbench Component Guide]"
        "(https://carpentries.github.io/sandpaper-docs/component-guide.html)" in text
    )


# -- file-level checklist overview --------------------------------------------


def test_render_markdown_files_section_lists_each_location_with_issue_count():
    findings = [
        Finding("error", "headings", "bad heading", location="episodes/01-intro.md"),
        Finding("warning", "links", "bad link", location="episodes/01-intro.md"),
        Finding("info", "style", "note only", location="episodes/02-more.md"),
    ]
    text = render_markdown(findings, "Report")
    assert "## Files" in text
    assert "- [ ] [episodes/01-intro.md](#episodes01-intromd) — 2 issue(s)" in text
    assert "- [episodes/02-more.md](#episodes02-moremd) — 1 note(s) only" in text


def test_render_markdown_files_section_links_match_heading_anchors():
    # GFM would slugify "## episodes/01-intro.md" to this anchor -- the
    # checklist's link target must actually match what GitHub renders.
    findings = [Finding("error", "headings", "bad heading", location="episodes/01-intro.md")]
    text = render_markdown(findings, "Report")
    assert "(#episodes01-intromd)" in text
    assert "## episodes/01-intro.md" in text


# -- tool version + lesson metadata in the report header ---------------------


def _sample_metadata() -> LessonMetadata:
    return LessonMetadata(
        title="Python Intro for Libraries",
        carpentry="Library Carpentry",
        life_cycle="beta",
        license="CC-BY 4.0",
        source="https://github.com/org/repo",
        contact="team@example.org",
        created="2020-01-01",
        authors=["Cody Hennesy", "Tim Dennis"],
    )


def test_render_markdown_includes_tool_version():
    text = render_markdown([], "Report")
    assert f"carpentries-workbench-checker v{__version__}" in text


def test_render_terminal_includes_tool_version():
    text = render_terminal([], "Report")
    assert f"carpentries-workbench-checker v{__version__}" in text


def test_render_markdown_no_metadata_omits_lesson_block():
    text = render_markdown([], "Report")
    assert "Authors:" not in text
    assert "Source:" not in text


def test_render_markdown_empty_metadata_omits_lesson_block():
    text = render_markdown([], "Report", metadata=LessonMetadata())
    assert "Authors:" not in text
    assert "Source:" not in text


def test_render_markdown_metadata_includes_lesson_identity():
    text = render_markdown([], "Report", metadata=_sample_metadata())
    assert "**Python Intro for Libraries**" in text
    assert "Library Carpentry" in text
    assert "life cycle: beta" in text
    assert "license: CC-BY 4.0" in text
    assert "Source: https://github.com/org/repo" in text
    assert "Authors: Cody Hennesy, Tim Dennis" in text
    assert "Contact: team@example.org" in text


def test_render_terminal_metadata_includes_lesson_identity():
    text = render_terminal([], "Report", metadata=_sample_metadata())
    assert "Python Intro for Libraries" in text
    assert "Authors: Cody Hennesy, Tim Dennis" in text


def test_render_markdown_metadata_partial_fields_only_shows_present_ones():
    metadata = LessonMetadata(title="Some Lesson")
    text = render_markdown([], "Report", metadata=metadata)
    assert "**Some Lesson**" in text
    assert "Authors:" not in text
    assert "Source:" not in text
    assert "Contact:" not in text


def test_render_json_includes_generated_by_and_lesson():
    payload = json.loads(render_json([], "Report", metadata=_sample_metadata()))
    assert payload["generated_by"] == {
        "name": "carpentries-workbench-checker",
        "version": __version__,
    }
    assert payload["lesson"]["title"] == "Python Intro for Libraries"
    assert payload["lesson"]["authors"] == ["Cody Hennesy", "Tim Dennis"]


def test_render_json_no_metadata_lesson_is_none():
    payload = json.loads(render_json([], "Report"))
    assert payload["lesson"] is None
