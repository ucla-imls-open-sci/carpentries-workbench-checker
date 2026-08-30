"""Unit tests for report rendering, including --blame annotation."""

from __future__ import annotations

from checker.report import Finding, render_markdown, render_terminal


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
