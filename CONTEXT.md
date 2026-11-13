# Carpentries Workbench Checker (`wbcheck`) — AI & Contributor Context

`wbcheck` is a fast local checker and optional AI pedagogical reviewer for Carpentries Workbench (Sandpaper) lessons.

## Architecture & State Model

- **CLI Entry Point**: `checker/app.py` (Typer subcommands: `check`, `review`, `report`, `issues`, `tui`, `fix`, `update`, `explain`, `rules`, `doctor`).
- **Saved Results State**: `<lesson>/.wbcheck/results.json` (version 3, managed by `checker/results.py` and `checker/refresh.py`).
  - Mechanical findings (`WB0xx`–`WB4xx`) are recomputed on every `check` / `fix` / `review`.
  - AI findings (`AI2xx`, `source="ai"`) are preserved across mechanical checks and marked `stale=True` only when the underlying Markdown content (excluding `wbcheck` annotations) changes.
  - Finding IDs (`Finding.id`) are 12-character SHA-1 hashes of `code|location|normalized_anchor(#occurrence)` — line numbers and counts are excluded so IDs survive edits elsewhere in the file.
- **Mechanical Checks**: `checker/lesson_check.py` (`check_config`, `check_support_files`, `check_episode`, `check_leftover_notes`).
- **Safe & Editorial Autofixes**: `checker/fix.py` (`SAFE_FIX_CODES = ("WB103", "WB213")`, `SUGGESTION_CODES = ("WB401", "WB009")`).
- **Inline Notes & Ignores**: `checker/annotate.py` (`<!-- wbcheck CODE: ... -->`, `<!-- wbcheck-ignore CODE: reason -->`, `<!-- wbcheck-ignore-file CODE -->`) and `checker/ignore.py` (`.wbcheck.toml`).

## AI Coding Agent CLI Workflow

When using `wbcheck` as an AI agent to inspect and fix a Carpentries Workbench lesson:

1. **Run mechanical checks and get structured JSON in one call**:
   ```bash
   wbcheck check <lesson> --json
   wbcheck check <lesson> --episode <episode.md> --json
   wbcheck check <lesson> --changed --json
   ```
   - `stdout` is strictly valid JSON; diagnostics go to `stderr`.
   - Exit codes: `0` = clean (below `--fail-on`), `1` = findings at/above `--fail-on`, `2` = usage/target error.

2. **Query or filter saved results with minimal token overhead**:
   ```bash
   wbcheck report <lesson> --lines -
   wbcheck report <lesson> --code WB213 --episode 01-intro.md --json -
   wbcheck report <lesson> --min-severity warning --source mechanical --lines -
   ```

3. **Preview and apply deterministic fixes non-interactively**:
   ```bash
   wbcheck fix <lesson> --apply --dry-run
   wbcheck fix <lesson> --suggest --dry-run
   wbcheck fix <lesson> --apply --yes --no-input
   ```

4. **Lookup rule documentation and environment status as JSON**:
   ```bash
   wbcheck rules --json
   wbcheck explain WB401 --json
   wbcheck doctor --json
   ```

## Development & Verification

- Run linter: `.pixi/envs/default/bin/ruff check .` (or `pixi run lint`)
- Run tests: `.pixi/envs/default/bin/pytest -q` (or `pixi run test`)
- Update regression corpus (`tests/corpus/*/expected.json`) after intentional rule/line changes:
  `WBCHECK_UPDATE_CORPUS=1 .pixi/envs/default/bin/pytest tests/test_corpus.py`
