"""Unit tests for report rendering, including --blame annotation."""

from __future__ import annotations

from checker.report import Finding, render_markdown, render_terminal


def test_render_markdown_blame_annotates_heading():
    findings = [Finding("error", "boilerplate", "still scaffold", location="episodes/ep.md")]
    text = render_markdown(findings, "Report", blame={"episodes/ep.md": "Jose Niño"})
    assert "## episodes/ep.md (last touched by: Jose Niño)" in text


def test_render_markdown_no_blame_arg_is_unchanged():
    findings = [Finding("error", "boilerplate", "still scaffold", location="episodes/ep.md")]
    text = render_markdown(findings, "Report")
    assert "## episodes/ep.md\n" in text
    assert "last touched by" not in text


def test_render_markdown_blame_missing_location_is_silent():
    findings = [Finding("error", "boilerplate", "still scaffold", location="episodes/ep.md")]
    text = render_markdown(findings, "Report", blame={"episodes/other.md": "Someone Else"})
    assert "## episodes/ep.md\n" in text
    assert "last touched by" not in text


def test_render_terminal_blame_annotates_heading():
    findings = [Finding("error", "boilerplate", "still scaffold", location="episodes/ep.md")]
    text = render_terminal(findings, "Report", blame={"episodes/ep.md": "Karla Padilla"})
    assert "(last touched by: Karla Padilla)" in text
