"""Shared fixtures. CliRunner has no terminal, so tests of interactive modes
(prompts, the editor, the TUI) run as if there were one; the tests of the
no-terminal guard turn it back off."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _pretend_terminal(monkeypatch):
    monkeypatch.setattr("checker.app._has_terminal", lambda: True)
