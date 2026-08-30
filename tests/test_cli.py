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
    assert blame == {"episodes/ep.md": "Test Author"}


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
