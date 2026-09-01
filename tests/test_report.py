"""Unit tests for report rendering, including --blame annotation."""

from __future__ import annotations

import json

import yaml

from checker import __version__
from checker.report import (
    _EXTENSION_SRC,
    Finding,
    LessonMetadata,
    _anchor,
    _grouped_sections,
    render_json,
    render_markdown,
    render_terminal,
)


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
    assert "episodes/ep.md" in text
    assert "last change authored by" not in text


def test_render_markdown_blame_missing_location_is_silent():
    findings = [Finding("error", "boilerplate", "still scaffold", location="episodes/ep.md")]
    text = render_markdown(findings, "Report", blame={"episodes/other.md": "Someone Else"})
    assert "episodes/ep.md" in text
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


def test_render_markdown_files_section_links_match_detail_section_heading():
    # File-first grouping means a file corresponds to exactly one detail
    # section again -- the checklist's anchor link must match what GitHub
    # would slugify that section's `## episodes/01-intro.md` heading to.
    findings = [Finding("error", "headings", "bad heading", location="episodes/01-intro.md")]
    text = render_markdown(findings, "Report")
    assert "(#episodes01-intromd)" in text
    assert "## episodes/01-intro.md" in text


# -- severity/category/shared-fix grouping ------------------------------------
#
# The core of this round: 14 findings sharing one root cause should read as
# one change applied in 14 places, not 14 visually-identical scattered
# lines. See design/validation-prompt-report-scannability-2026-08-31.md.


def test_grouped_sections_merges_findings_sharing_identical_hint():
    findings = [
        Finding("warning", "headings", "dup A", location="ep.md", hint="Use a unique heading."),
        Finding("warning", "headings", "dup B", location="ep.md", hint="Use a unique heading."),
        Finding("warning", "headings", "dup C", location="ep2.md", hint="Use a unique heading."),
    ]
    sections = _grouped_sections(findings)
    assert len(sections) == 1
    severity, category, hint, items = sections[0]
    assert (severity, category, hint) == ("warning", "headings", "Use a unique heading.")
    assert len(items) == 3


def test_grouped_sections_does_not_merge_different_hints_in_same_category():
    findings = [
        Finding("warning", "headings", "a", location="ep.md", hint="Fix A"),
        Finding("warning", "headings", "b", location="ep.md", hint="Fix B"),
    ]
    sections = _grouped_sections(findings)
    assert len(sections) == 2
    assert {hint for _, _, hint, _ in sections} == {"Fix A", "Fix B"}


def test_grouped_sections_never_merges_hint_less_findings():
    # Two unrelated problems that both happen to lack a hint are not the
    # same fix -- each must stay its own singleton, not collapse into one
    # group just because hint is None for both.
    findings = [
        Finding("warning", "headings", "unrelated problem one", location="ep.md"),
        Finding("warning", "headings", "unrelated problem two", location="ep.md"),
    ]
    sections = _grouped_sections(findings)
    assert len(sections) == 2
    assert all(hint is None for _, _, hint, _ in sections)
    assert {items[0].message for _, _, _, items in sections} == {
        "unrelated problem one",
        "unrelated problem two",
    }


def test_grouped_sections_orders_severity_errors_before_warnings_before_info():
    findings = [
        Finding("info", "style", "note", location="ep.md"),
        Finding("error", "config", "bad config", location="config.yaml"),
        Finding("warning", "links", "bad link", location="ep.md"),
    ]
    sections = _grouped_sections(findings)
    assert [severity for severity, _, _, _ in sections] == ["error", "warning", "info"]


def test_render_markdown_shared_hint_group_shows_guide_once_not_per_occurrence():
    findings = [
        Finding("warning", "headings", "dup A", location="ep.md", line=1, hint="Use a unique heading."),
        Finding("warning", "headings", "dup B", location="ep.md", line=2, hint="Use a unique heading."),
    ]
    text = render_markdown(findings, "Report")
    assert text.count("**Guide:**") == 1
    assert text.count("**Change:** Use a unique heading.") == 1
    # occurrence checklist still present, one line per finding (plus the
    # unrelated Files-section checkbox for this same file, hence 3 not 2)
    assert text.count("> - [ ]") == 2
    assert text.count("- [ ]") == 3


def test_render_markdown_hint_less_finding_has_no_change_line():
    findings = [Finding("warning", "headings", "some problem", location="ep.md")]
    text = render_markdown(findings, "Report")
    assert "**Change:**" not in text


def test_render_markdown_boilerplate_group_has_no_guide_line():
    findings = [Finding("warning", "boilerplate", "still scaffold", location="ep.md")]
    text = render_markdown(findings, "Report")
    assert "**Guide:**" not in text


def test_render_markdown_action_summary_has_one_row_per_shared_fix():
    # Repeated problem: 3 occurrences of the same fix in different files
    # should be one Action Summary row with Occurrences=3, Files=2 -- not
    # 3 separate rows.
    findings = [
        Finding("warning", "headings", "dup A", location="ep.md", hint="Use a unique heading."),
        Finding("warning", "headings", "dup B", location="ep.md", hint="Use a unique heading."),
        Finding("warning", "headings", "dup C", location="ep2.md", hint="Use a unique heading."),
    ]
    text = render_markdown(findings, "Report")
    assert "| ⚠️ Warning | Use a unique heading. | 3 | 2 |" in text


def test_render_markdown_action_summary_hint_less_row_uses_message():
    findings = [Finding("error", "config", "bad config value", location="config.yaml")]
    text = render_markdown(findings, "Report")
    assert "| ❌ Error | bad config value | 1 | 1 |" in text


def test_render_markdown_detail_section_is_file_first():
    # Two files, each with one finding of a different category -- the
    # detail section must group by file (one `## location` heading each),
    # not by category, so someone editing one file sees everything about
    # that file in one place.
    findings = [
        Finding("warning", "headings", "dup", location="a.md", hint="Fix headings"),
        Finding("warning", "links", "bad link", location="b.md", hint="Fix links"),
    ]
    text = render_markdown(findings, "Report")
    a_pos = text.index("## a.md")
    b_pos = text.index("## b.md")
    fix_headings_pos = text.index("**Change:** Fix headings")
    fix_links_pos = text.index("**Change:** Fix links")
    assert a_pos < fix_headings_pos < b_pos < fix_links_pos


def test_render_markdown_file_section_collapses_same_fix_within_file():
    findings = [
        Finding("warning", "headings", "dup A", location="ep.md", line=1, hint="Use a unique heading."),
        Finding("warning", "headings", "dup B", location="ep.md", line=2, hint="Use a unique heading."),
        Finding("error", "links", "bad link", location="ep.md", line=3, hint="Fix the link."),
    ]
    text = render_markdown(findings, "Report")
    # one file section, containing two Change groups (mixed severities)
    assert text.count("## ep.md") == 1
    assert text.count("**Change:** Use a unique heading.") == 1
    assert text.count("**Change:** Fix the link.") == 1
    assert "❌" in text  # the error occurrence's own icon, since severity
    assert "⚠️" in text  # is no longer implied by an enclosing heading


def test_anchor_handles_prose_headings_with_punctuation():
    assert _anchor("Headings — 14 warning(s)") == "headings-14-warnings"


def test_anchor_matches_old_path_slugification():
    # Regression: the generalized _anchor() must still slugify a bare file
    # path the same way GitHub does, since this behavior predates the
    # prose-heading use case and other code may still rely on it.
    assert _anchor("episodes/01-intro.md") == "episodes01-intromd"


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


# -- checker-report Quarto format extension -----------------------------------
#
# These don't invoke quarto itself (no automated test does, consistent with
# the rest of this file -- see README's Testing section); they guard against
# the extension directory being accidentally deleted, renamed, or shipping
# invalid YAML, which _render_via_quarto would otherwise only surface as a
# runtime failure the next time someone actually runs --html/--pdf.


def test_extension_directory_exists():
    assert _EXTENSION_SRC.is_dir()
    assert (_EXTENSION_SRC / "_extension.yml").is_file()
    assert (_EXTENSION_SRC / "checker-report.scss").is_file()


def test_extension_yml_is_valid_and_declares_html_and_pdf_formats():
    manifest = yaml.safe_load((_EXTENSION_SRC / "_extension.yml").read_text())
    formats = manifest["contributes"]["formats"]
    assert "html" in formats
    assert "pdf" in formats
