# Regression corpus

Each folder holds a small `lesson/` and an `expected.json`: the findings
`run_checks()` must return, as `[code, severity, location, line, id]`.

- `clean` and `tricky-valid` must report nothing. `tricky-valid` is content that
  looks wrong but is fine (fenced `:::`, decorative images, ordered objectives,
  the same heading under different parents), so a false positive shows up here.
- Every other folder triggers one family of rules. `test_corpus.py` checks that
  every content rule (all `WB` codes except WB012) appears in some case.
- `id` is the finding ID. If it changes, a message was reworded: existing
  ignores and filed issues would no longer match. Keep the ID with
  `identity_anchor` (see `legacy_anchor` in `checker/report.py`), or accept the change on purpose.

To add a case, make `tests/corpus/<name>/lesson/` and run
`WBCHECK_UPDATE_CORPUS=1 pixi run pytest tests/test_corpus.py`. Read the new
`expected.json` before committing: it records what wbcheck does now, not what
is right.

The CI job `pixi run test` runs all of this.
