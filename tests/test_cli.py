"""Unit tests for the CLI's --blame support."""

from __future__ import annotations

import subprocess
from pathlib import Path

from checker.cli import _blame_map, _read_glossary
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
