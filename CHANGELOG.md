# Changelog

## Unreleased

Editor integration (design/2026-10-29-editor-integration-prompt.md). No change to existing commands unless you pass a new flag.

### Added
- **`wbcheck report --sarif FILE`** writes SARIF 2.1.0 (rules, levels, finding IDs as fingerprints) for the VS Code and Positron SARIF Viewer. **`--lines FILE`** writes `file:line:col: severity CODE message` for editor problem matchers. `-` means stdout for both.
- **`editors/wbcheck-markers.R`** loads saved results into RStudio's Markers pane with `rstudioapi::sourceMarkers()`. **`editors/README.md`** documents RStudio, a `tasks.json` problem matcher for Positron and VS Code, and SARIF.
- **`wbcheck fix --annotate`** writes `<!-- wbcheck CODE: message -->` above the flagged block (a YAML comment in front matter). It is idempotent, stays out of code fences, hoists above a list or a div title so rendering doesn't change, and skips a front-matter note that would change the parsed YAML. **`--clean-annotations`** removes only those notes and restores the file byte for byte.
- **WB115**: a leftover wbcheck note is a warning in `wbcheck check`. **`--fail-on annotations`** exits 1 on errors and leftover notes.

### Fixed (from design/2026-10-29-cli-best-practices-assessment.md)
- `wbcheck fix` and `wbcheck tui` no longer hang without a terminal. They exit 2 and say what to use instead. `fix --no-input` refuses any mode that would prompt or open an editor. `--print`, `--annotate`, `--clean-annotations` and `--apply --yes` still work in scripts. `issues --create` without `--yes` needs a terminal too.
- `report --json -` and `--md -` write to stdout. They used to create a file named `-`. `--html -` and `--pdf -` are rejected.
- Exit code 2 now means "could not run" for a missing path, a failed clone, a folder with no `episodes/` or `config.yaml` (nothing is written into it), and `--episode` naming a missing file. These were 1, the same as "findings". The codes are in the README and the top-level help.
- `-h` works on every command. Top-level help links to the docs and the issue tracker. `check`, `fix` and `report` help show examples.

### Added
- Regression corpus (`tests/corpus/`): 15 small lessons with the exact findings expected (code, severity, file, line, finding ID), covering every content rule, plus `clean` and `tricky-valid` lessons that must report nothing. A check that starts or stops firing, moves, or has its message reworded fails the test. See `tests/corpus/README.md`.
- Test that 13 command forms finish with stdin closed instead of hanging.
- `scripts/render_safety.py LESSON`: builds a lesson with sandpaper with and without `fix --annotate` notes and compares the HTML (needs R and sandpaper; not part of `pixi run test`).
- Inline ignore: `<!-- wbcheck-ignore WB404: reason -->` ignores a code on the next non-blank line, `wbcheck-ignore-file CODE` for the whole file (a `#` comment in front matter). Counted as ignored; never read by the checks.

### Changed
- `check` and `report` `--source` is now `--show-source`, so it no longer clashes with `fix` and `issues --source all|mechanical|ai`. `--source` still works on those two, hidden, with a warning.
- Checks and the AI review now ignore wbcheck notes, so a note never creates a finding or reaches a model.
- Internal: `_code_fence_mask` is built on a new `_code_fence_starts`; its output is unchanged.

## 0.3.1 (2026-10-12)

Credits and citation only. No behavior changes.

### Changed
- `CITATION.cff` lists all eight program contributors as authors, with version and release date, so Zenodo records carry them.
- New `CREDITS.md` records contributor roles with the CRediT taxonomy.
- README Credits section describes how wbcheck began with UCLA DataSquad students in 2023 and evolved with the UCLA-IMLS program.
- `pyproject.toml` authors now include Lawrence Lee and Eric Huang.
- `pixi.lock` refreshed.

## 0.3.0 (2026-09-30)

From the 2026-09-30 standards review (`design/2026-09-30-standards-audit.md`,
`-rule-schema-help-proposal.md`, `-claude-standards-handoff.md`; review IDs
in brackets). The theme: say no more than the check can see.

### Added
- **`wbcheck explain CODE`** and **`wbcheck rules [--search] [--topic]`**:
  offline rule help showing what each check observes, why it matters, what to
  do, when keeping the content is reasonable, the check's limits, whether
  `wbcheck fix` can help, and the exact source sections with URLs and
  check dates (DES-01).
- Rule metadata for all 48 rules: topic, authority (technical requirement,
  review criterion, recommendation, or wbcheck policy), detection
  (deterministic, heuristic, AI-assisted), default severity with a reason,
  and a shared, dated `REFERENCES` table. Tests check it's complete and that
  each default matches what the check emits.
- The same explanation in every view (DES-02): the TUI detail pane (with
  visible source URLs), a "Rule explanations" appendix in markdown/HTML/PDF
  reports, and issue drafts' "Why these matter". CLI and report output show
  the severity word, not only an icon, and point to `wbcheck explain`. AI
  findings carry a note that a matched quote isn't a verified judgment.

### Changed
- Source links point at the specific section: config rules now cite the
  config.yaml page (it pointed at the wrong page), CLDT citations use the
  focused pages, WB212 cites pegboard's heading validation, WB205 the Lab
  editor notes on solutions [STD-09].
- Rationale and hints no longer overstate the evidence: WB403 reports zero
  exercise time without saying nothing assesses the objectives [STD-02];
  WB205 says it compares totals [STD-04]; WB010/WB114 accept a linked
  external glossary and WB009 treats unlisted drafts as legitimate [STD-05];
  WB404 says its threshold is wbcheck's own [STD-08]; WB203's hint no longer
  asks for a closing fence at least as long as the opener [STD-09]; AI rules
  say what the model can't see [STD-11].
- AI review prompt: states that the model sees source text only (no rendered
  figures, no execution, no learner profiles), that a missing local glossary
  doesn't mean no glossary, and no longer claims lesson-wide items are
  "reviewed separately" [STD-05, STD-11]. Checked against 0.2.1 on real
  episodes with the Claude backend (`design/2026-09-30-ai-prompt-eval.md`):
  same volume and reliability, better-hedged glossary and accessibility
  findings; accuracy findings unchanged.
- **Results file format version 3** adds `identity_anchor`. Versions 1-3 are
  read; wbcheck 0.2.1 and earlier refuse a v3 file ("not supported... re-run
  `wbcheck check`"), which rebuilds it in their format [STD-06].

### Fixed
- WB301 no longer flags images with an explicit `{alt='...'}` (including
  multi-line) or the decorative `{alt=""}` marker [STD-01].
- WB212 judges duplicate headings within their hierarchy, as pegboard does;
  the same subheading under different sections is no longer flagged [STD-03].
- Objectives are counted as top-level list items with any marker (`+` and
  numbered lists were missed; nested bullets were counted) [STD-07].
- WB404 skips blockquoted text (quoted interviews, data values) [STD-08].
- WB104 rejects YAML `true`/`false`, `.nan`, `.inf`, and negative timings;
  WB105 and WB403 skip invalid timings, so `exercises: false` no longer reads
  as zero minutes [STD-12].

### Compatibility
- Finding IDs are preserved: where a message's wording changed, or a
  corrected check drops a false positive between two repeats, surviving
  findings keep their 0.2.1 IDs, so `.wbcheck.toml` ignores and issues
  already filed (open or closed) still match. Tested against 0.2.1 golden IDs
  and on five real lessons, where every remaining finding kept its ID.
- Coverage changes can move an explicit `--fail-on warning` exit: `+` and
  numbered objectives now get WB401/WB402/WB403, invalid timings now get
  WB104, and some WB212, WB301, WB404, and nested-bullet WB401 findings go
  away. Default severities, selected rules, issue grouping, and
  `--fail-on error` behaviour are unchanged.

### Known issues
- Local Ollama reviews silently truncate the prompt, because no context size
  is set (#66). Use the Claude backend until that's fixed.

### Deferred
- WB213's automatic fix moving to an editorial suggestion [STD-10] (#58); WB012
  becoming a command error (exit 2) instead of a finding [DES-03] (#59); a TUI
  help modal (F1) [DES-02] (#60); per-challenge WB205, which needs an ID
  transition plan first [STD-04, OPEN-02] (#61); which div class orders
  Workbench accepts [OPEN-01] (#62); whether `created` feeds citation metadata
  [OPEN-05] (#63).

## 0.2.1 (2026-09-30)

### Changed
- README reorganized around tasks (check, fix, review, TUI, issues,
  reports), with internals moved to a Reference section. It now spells out
  the vim/nvim loop for `wbcheck fix` (fix, `:w`, `]q`, refresh with
  `:cexpr system('wbcheck fix . --print')`) and is more careful about what
  quote verification proves for AI findings (#46).
- The TUI's issue confirmation lists each issue's findings and says how
  many selected findings a filter is hiding and how many stale ones were
  left out (#47).

### Fixed
From a second external review (`design/2026-09-30-codex-review-wbcheck.md`):
- The TUI could file a stale AI finding if you selected it by hand, and
  could offer findings you ignored while it was checking GitHub. One filing
  rule now covers every path, and the TUI plans issues from the current
  results (#47).
- `check --episode` showed and failed on other episodes' saved findings.
  It now reports on the episode you asked for; the saved results still keep
  the rest. Partial results are labelled in terminal and file reports and
  the TUI, instead of reading as "No issues found" (#48).
- Ignoring one of two AI findings with the same rule, file, and quote could
  give its ID to the other, which then disappeared on the next check.
  Saved AI findings now keep their IDs (#49).
- A damaged `results.json` (e.g. `[]`) crashed `check` instead of being
  rebuilt; `report` and `issues` showed a traceback. `check` now warns and
  rebuilds, read-only commands say how to recover, and results are written
  atomically (#50).
- A missing or failing `$EDITOR` crashed the TUI; it now shows a
  notification and keeps running (#50).

## 0.2.0 (2026-09-29)

A rebuild around a saved results file, structured AI findings, and GitHub
issue filing. Tracked in #21 to #28; the design is in
`design/modernization-assessment-2026-09-29.md`.

### Added
- **`wbcheck` CLI** with `check`, `review`, `report`, `issues`, `tui`, `doctor`, and `update`
  subcommands sharing `<lesson>/.wbcheck/results.json` (#24). Rich terminal
  output, tab completion (`wbcheck --install-completion`), and `check
  --fail-on error|warning|info|never` for CI and pre-commit use.
- **Rule codes** `WB001` to `WB404` and `AI201` to `AI208`, each with a
  rationale and a link to the specific guide section; stable finding IDs
  that survive line shifts (#23).
- **`wbcheck issues`**: files findings as pull-request-sized GitHub issues,
  grouped per file, per rule when a rule spans 3+ files, or per AI scope.
  Skips findings already filed, including in closed issues (#21).
- **`wbcheck tui`**: Textual app to browse, filter, ignore, open in
  `$EDITOR`, and file findings as issues (#28).
- **`.wbcheck.toml`** to ignore findings by code, path glob, or ID.
- **WB213**: headings that skip a level (h2 to h4), per the Carpentries Lab
  editor checklist.
- **`wbcheck fix`**: work through findings in your editor. In vim/nvim they
  load into the quickfix list; other editors go one finding at a time. Both
  re-check afterwards and report what was fixed. `--apply` offers the safe
  fixes (WB103, WB213) as diffs; `--suggest` offers editorial ones (WB401
  objective rewrites, WB009 listing an episode), each confirmed on its own
  and never applied by `--yes`; `--print` emits quickfix lines.
- **`check --changed [--since REF]`**: only show and count findings in files
  you've changed.
- The TUI re-checks when you come back from the editor (`o`) and says
  whether that finding is fixed.
- **One-line install** with pixi (`install.sh`), plus `wbcheck doctor` and
  `wbcheck update`. CI installs with the script on Linux and macOS and runs
  the installed command.

### Changed
- **AI review returns structured findings** with a verbatim quote, which is
  checked against the episode; findings whose quote isn't there are
  dropped (#26). Grading guidance is pinned from `checker/rubric/`
  (`pixi run refresh-rubric`) instead of fetched and embedded each run
  (#25). Default Claude model `claude-opus-5-5`, with `--effort`.
- Objective findings suggest a concrete rewrite (Understand -> Explain,
  Know -> Identify), and more findings carry line numbers.

### Removed
- LangChain, Chroma, tiktoken, and the Ollama requirement for the Claude
  backend; the `codex` backend.

### Fixed
From an external review (`design/2026-09-29-codex-review-wbcheck.md`):
- `fix --apply` could delete an objective's text (WB401, when it contained
  a quote) and corrupt `config.yaml` (WB009, no final newline or a
  YAML-special file name); `--code WB009` bypassed the reference-content
  safeguard.
- `--changed` missed file names with spaces or non-ASCII characters.
- A `config.yaml` or `CITATION.cff` that isn't a mapping crashed the run.
- Code fences didn't track fence character and length; `::: {#id .class}`
  divs read as closing fences; image syntax in inline code was flagged.
- A review where every episode failed, or `--episode` matched nothing,
  exited 0.
- Quote matching crashed on characters that case-fold to several (`ß`).
- Saved results: `check` after `review` deleted AI findings; `check
  --episode` left a partial snapshot that `review` reused; results from one
  git URL could be merged into another's; ignoring a finding could hand its
  ID to a sibling. Now one refresh policy (`checker/refresh.py`) records
  target identity, commit, scope, and file fingerprints, marks AI findings
  stale when their file changes, and never renumbers after filtering. AI
  finding IDs come from the quoted text, not the model's wording.
- The glossary moved out of the system prompt; Ollama calls got a timeout;
  `issues` reads up to 10,000 existing issues and refuses past that rather
  than risk duplicates; CI builds the wheel and checks its contents.

- Installed packages were missing `checker/report.py` (an unanchored
  `report.*` in `.gitignore` excluded it from the build) and the Quarto
  report extension (now shipped inside the package).
- WB211 flagged callout and spoiler titles (`###` inside a fenced div) as
  a bad first heading.
- `--format json` crashed on an unquoted `created:` date in config.yaml.

The legacy `pixi run check` CLI still works and is unchanged apart from the
new AI review output.
