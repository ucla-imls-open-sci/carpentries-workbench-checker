"""Unit tests for the CLI's --blame support."""

from __future__ import annotations

import subprocess
from pathlib import Path

from checker import cli
from checker.cli import _blame_map, _github_blob_base, _read_glossary, main
from checker.report import Finding


def _init_git_repo(path: Path):
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test Author"], cwd=path, check=True)


def test_blame_map_reads_last_commit_author(tmp_path):
    _init_git_repo(tmp_path)
    (tmp_path / "episodes").mkdir()
    ep = tmp_path / "episodes" / "ep.md"
    ep.write_text("content\n")
    subprocess.run(["git", "add", "episodes/ep.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add episode"], cwd=tmp_path, check=True)

    findings = [Finding("error", "boilerplate", "msg", location="episodes/ep.md")]
    blame = _blame_map(tmp_path, findings)
    assert "episodes/ep.md" in blame
    author, date, short_sha = blame["episodes/ep.md"].split(", ")
    assert author == "Test Author"
    assert len(date) == 10  # YYYY-MM-DD
    assert len(short_sha) >= 7


def test_blame_map_respects_mailmap_canonical_name(tmp_path):
    # %aN (used here) canonicalizes via .mailmap; %an (the old format) would
    # not. Two commits under different names for the same mapped identity
    # should both attribute to the canonical name.
    _init_git_repo(tmp_path)
    (tmp_path / ".mailmap").write_text("Canonical Name <test@example.com> <test@example.com>\n")
    subprocess.run(["git", "add", ".mailmap"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add mailmap"], cwd=tmp_path, check=True)
    (tmp_path / "episodes").mkdir()
    (tmp_path / "episodes" / "ep.md").write_text("content\n")
    subprocess.run(["git", "add", "episodes/ep.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add episode"], cwd=tmp_path, check=True)

    findings = [Finding("error", "boilerplate", "msg", location="episodes/ep.md")]
    blame = _blame_map(tmp_path, findings)
    assert blame["episodes/ep.md"].startswith("Canonical Name, ")


def test_blame_map_not_a_git_repo_is_empty(tmp_path):
    # No git init -- must not raise, just return nothing to annotate with.
    (tmp_path / "episodes").mkdir()
    (tmp_path / "episodes" / "ep.md").write_text("content\n")
    findings = [Finding("error", "boilerplate", "msg", location="episodes/ep.md")]
    assert _blame_map(tmp_path, findings) == {}


def test_blame_map_ignores_findings_without_location(tmp_path):
    _init_git_repo(tmp_path)
    findings = [Finding("info", "config", "general note", location=None)]
    assert _blame_map(tmp_path, findings) == {}


# -- glossary reading for the --ai review's glossary-gap prompt -------------


def test_read_glossary_missing_file_is_empty(tmp_path):
    assert _read_glossary(tmp_path) == ""


def test_read_glossary_placeholder_is_empty(tmp_path):
    (tmp_path / "learners").mkdir()
    (tmp_path / "learners" / "reference.md").write_text(
        "---\ntitle: 'Reference'\n---\n\n## Glossary\n\nThis is a placeholder file. Please add content here.\n"
    )
    assert _read_glossary(tmp_path) == ""


def test_read_glossary_real_content_is_returned(tmp_path):
    (tmp_path / "learners").mkdir()
    content = "---\ntitle: 'Reference'\n---\n\nPermissive license\n: Allows reuse.\n"
    (tmp_path / "learners" / "reference.md").write_text(content)
    assert _read_glossary(tmp_path) == content


def test_read_glossary_falls_back_to_legacy_root_path(tmp_path):
    # Real bug fixed by the shared resolve_glossary_path(): this used to
    # hardcode learners/reference.md only, so a legacy-layout lesson's real
    # glossary would read as "missing" here even though check_config()'s
    # existence check (which already checked both paths) correctly found it.
    content = "# Reference\n\nCopyleft\n: Requires derivative works stay open.\n"
    (tmp_path / "reference.md").write_text(content)
    assert _read_glossary(tmp_path) == content


# -- GitHub blob base URL, for clickable line links in the markdown report --


def _commit_something(path: Path):
    (path / "episodes").mkdir()
    (path / "episodes" / "ep.md").write_text("content\n")
    subprocess.run(["git", "add", "episodes/ep.md"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add episode"], cwd=path, check=True)


def test_github_blob_base_https_remote(tmp_path):
    _init_git_repo(tmp_path)
    _commit_something(tmp_path)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/org/repo.git"],
        cwd=tmp_path,
        check=True,
    )
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert _github_blob_base(tmp_path) == f"https://github.com/org/repo/blob/{sha}"


def test_github_blob_base_ssh_remote(tmp_path):
    _init_git_repo(tmp_path)
    _commit_something(tmp_path)
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:org/repo.git"],
        cwd=tmp_path,
        check=True,
    )
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert _github_blob_base(tmp_path) == f"https://github.com/org/repo/blob/{sha}"


def test_github_blob_base_not_a_git_repo_is_none(tmp_path):
    assert _github_blob_base(tmp_path) is None


def test_github_blob_base_no_remote_is_none(tmp_path):
    _init_git_repo(tmp_path)
    _commit_something(tmp_path)
    assert _github_blob_base(tmp_path) is None


def test_github_blob_base_non_github_remote_is_none(tmp_path):
    _init_git_repo(tmp_path)
    _commit_something(tmp_path)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://gitlab.com/org/repo.git"],
        cwd=tmp_path,
        check=True,
    )
    assert _github_blob_base(tmp_path) is None


# -- --open flag ---------------------------------------------------------------


def test_open_flag_launches_browser_on_successful_render(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(cli, "render_html_via_quarto", lambda _md_text, out_path, **_kw: out_path)
    monkeypatch.setattr(cli.webbrowser, "open", lambda uri: opened.append(uri))
    out = tmp_path / "report.html"
    out.write_text("<html></html>")
    main([str(tmp_path), "--html", "--open", "--output", str(tmp_path / "report.md")])
    assert opened == [out.resolve().as_uri()]


def test_open_flag_without_html_prints_notice(tmp_path, capsys):
    main([str(tmp_path), "--open", "--output", str(tmp_path / "report.md")])
    assert "--open has no effect without --html" in capsys.readouterr().err


def test_open_flag_when_quarto_missing_prints_nothing_to_open(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "render_html_via_quarto", lambda _md_text, _out_path, **_kw: None)
    main([str(tmp_path), "--html", "--open", "--output", str(tmp_path / "report.md")])
    assert "no HTML file was rendered" in capsys.readouterr().err


# -- --pdf flag ------------------------------------------------------------


def test_pdf_flag_writes_rendered_pdf(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "render_pdf_via_quarto", lambda _md_text, out_path, **_kw: out_path)
    main([str(tmp_path), "--pdf", "--output", str(tmp_path / "report.md")])
    assert f"wrote {tmp_path / 'report.pdf'}" in capsys.readouterr().err


def test_pdf_flag_default_output_name_has_no_markdown_output(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "render_pdf_via_quarto", lambda _md_text, out_path, **_kw: out_path)
    main([str(tmp_path), "--pdf"])
    assert "wrote report.pdf" in capsys.readouterr().err


def test_pdf_flag_when_quarto_missing_prints_notice(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "render_pdf_via_quarto", lambda _md_text, _out_path, **_kw: None)
    main([str(tmp_path), "--pdf", "--output", str(tmp_path / "report.md")])
    assert "quarto not found on PATH -- skipping PDF render" in capsys.readouterr().err


def test_pdf_flag_when_render_fails_prints_error(tmp_path, monkeypatch, capsys):
    def _raise(_md_text, _out_path, **_kw):
        raise RuntimeError("no LaTeX installation found")

    monkeypatch.setattr(cli, "render_pdf_via_quarto", _raise)
    main([str(tmp_path), "--pdf", "--output", str(tmp_path / "report.md")])
    err = capsys.readouterr().err
    assert "quarto render failed, skipping PDF output" in err
    assert "no LaTeX installation found" in err


def test_html_and_pdf_flags_together_both_render(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "render_html_via_quarto", lambda _md_text, out_path, **_kw: out_path)
    monkeypatch.setattr(cli, "render_pdf_via_quarto", lambda _md_text, out_path, **_kw: out_path)
    main([str(tmp_path), "--html", "--pdf", "--output", str(tmp_path / "report.md")])
    err = capsys.readouterr().err
    assert f"wrote {tmp_path / 'report.html'}" in err
    assert f"wrote {tmp_path / 'report.pdf'}" in err


def test_html_render_receives_lesson_title_as_report_title(tmp_path, monkeypatch):
    (tmp_path / "config.yaml").write_text("title: 'Python Intro'\n")
    captured = {}

    def _capture(_md_text, out_path, **kw):
        captured.update(kw)
        return out_path

    monkeypatch.setattr(cli, "render_html_via_quarto", _capture)
    main([str(tmp_path), "--html", "--output", str(tmp_path / "report.md")])
    assert captured["report_title"] == "Python Intro — Lesson Check Report"


def test_html_render_falls_back_to_default_title_when_no_lesson_title(tmp_path, monkeypatch):
    captured = {}

    def _capture(_md_text, out_path, **kw):
        captured.update(kw)
        return out_path

    monkeypatch.setattr(cli, "render_html_via_quarto", _capture)
    main([str(tmp_path), "--html", "--output", str(tmp_path / "report.md")])
    assert captured["report_title"].startswith("Lesson Check Report")
    assert "Python Intro" not in captured["report_title"]
