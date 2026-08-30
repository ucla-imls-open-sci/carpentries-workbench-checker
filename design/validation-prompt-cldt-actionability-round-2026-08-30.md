# Validation request: boilerplate/placeholder detection, --blame, AI glossary-gap suggestions

## Context (what came before this round)

`carpentries-workbench-checker` is a small internal tool for UCLA's IMLS
Open Science / UC OSPO Network programs. It's a Python CLI (`checker/`, run
via `pixi run check <path-or-git-url>`) that Carpentries Workbench lesson
authors run locally before pushing, to catch problems before waiting on the
real CI (`sandpaper::validate_lesson()` / `pegboard`'s validators, several
minutes, Docker-based). Two layers: deterministic mechanical checks
(`checker/lesson_check.py`) approximating sandpaper/pegboard's structural
rules plus CLDT/Carpentries Lab pedagogical guidance, and an optional `--ai`
narrative review (`checker/ai_review.py`, three swappable backends: local
Ollama, Claude API, OpenAI's Codex CLI).

A previous validation round (2026-08-20) covered the core architecture and
a first pass of CLDT/Lab-checklist-derived checks (objective verb quality,
contractions, episode length, generic link text, glossary-file existence).
That round's top fix was "add CI", `.github/workflows/test.yml` now runs
`pixi run test` on every push/PR, and it is NOT a required branch-protection
check (deferred to the maintainer, still undecided). Don't relitigate the
core architecture or that first round's specific checks, this round is
about what got added since.

## What changed this round, and why

I spent CLDT co-teaching a real cohort (UC OSPO Network's "Software
Licensing" lesson team) through a two-day training, then audited the actual
lesson repo they produced (`UC-OSPO-Network/oss-license-workshop`) the
following week. Every new check below exists because it maps to a real bug
found in that specific audit, not a hypothetical.

**What the audit found** (all confirmed by hand, then cross-checked against
the checker before I touched any code): an episode can pass every existing
mechanical check, valid front matter, all three required
`questions`/`objectives`/`keypoints` blocks present, no broken links, and
still be entirely unwritten:
- `episodes/choosing-licenses.md`'s title was still the literal
  `sandpaper::create_lesson()` scaffold default, `"Using Markdown"`
- `episodes/introduction.md` still had the scaffold's own worked example
  (`paste("This", "new", "lesson", "looks", "good")`) as its only content,
  and wasn't even listed in `config.yaml`'s `episodes:`
- `episodes/why-license.md` and `episodes/when-license-clash.md` both had
  `keypoints` blocks present and structurally valid, containing only
  `keypoint1`/`keypoint2` or `keypoint 1`/`keypoint 2`
- `episodes/when-license-clash.md` had `exercise:` (singular) instead of
  `exercises:` in front matter, passes YAML parsing, reads as a missing
  field with zero indication the author actually set a value under the
  wrong key
- An open draft PR's new episode file, `episode-2-permissive-vs-copyleft`,
  had no `.md` extension, silently excluded from every existing check's
  glob, so it sat unbuilt and uninspected on an open PR for days
- All four support files (`learners/setup.md`, `learners/reference.md`,
  `instructors/instructor-notes.md`, `profiles/learner-profiles.md`) were
  still 100% scaffold placeholder text, none of these are ever seen by
  `check_episode()` (they aren't episodes), and `check_config()` only
  checked that `learners/reference.md` *exists*, never its content

**Deterministic checks added**, all in `checker/lesson_check.py`, same
severity conventions as before (structural violations `error`, content gaps
that a build will still succeed with `warning`):

```python
SCAFFOLD_EPISODE_TITLE = "using markdown"
SCAFFOLD_BODY_FINGERPRINTS = (
    "this is a lesson created via the carpentries workbench",
    'paste("this", "new", "lesson", "looks", "good")',
    "buoyant barnacle",
)

PLACEHOLDER_BULLET_TEXTS = {
    "keypoint1", "keypoint2", "keypoint 1", "keypoint 2",
    "objective 1", "objective n",
    "put questions here", "put objectives here", "put keypoints here",
}

SUPPORT_FILE_CHECKS = {
    "learners/reference.md": ("this is a placeholder file", "<hint text>"),
    "learners/setup.md": ("fixme: setup instructions live in this document", "<hint text>"),
    "instructors/instructor-notes.md": ("this is a placeholder file", "<hint text>"),
    "profiles/learner-profiles.md": ("this is a placeholder file", "<hint text>"),
}
```

1. **`_check_boilerplate`**: exact case-insensitive match of episode title
   against `SCAFFOLD_EPISODE_TITLE`, and substring match of episode body
   against each `SCAFFOLD_BODY_FINGERPRINTS` entry. Fires per-fingerprint
   (an episode with 2 matches gets 2 findings).
2. **`_check_placeholder_bullets`**: walks div nesting (same
   stack-tracking pattern as the existing `_check_divs`), and when inside a
   top-level `questions`/`objectives`/`keypoints` block, checks each bullet
   line's stripped-lowercased text against `PLACEHOLDER_BULLET_TEXTS`
   (exact match, not substring).
3. **Extension-less episode file warning**, in `check_config()`: any
   non-directory, non-dotfile entry directly under `episodes/` whose suffix
   isn't `.md`/`.Rmd` gets flagged. This is the fix for the PR-#5 bug above,
   the existing episode-iteration glob (`p.suffix in (".md", ".Rmd")`)
   already silently excluded such files; now their absence from the build
   is at least visible.
4. **`check_support_files()`**: new top-level function, not called from
   `check_episode()`. Iterates `SUPPORT_FILE_CHECKS`, and for each path that
   exists, does a case-insensitive substring match against its one
   fingerprint string. Wired into `run_checks()` unconditionally (runs even
   when `--episode` filters to one episode, same as `check_config()`
   already did).

**`--blame` flag** (`checker/cli.py`, `checker/report.py`): optional
annotation on the markdown/terminal report, `## episodes/foo.md (last
touched by: Jane Doe)`, sourced from `git log -1 --format=%an -- <path>`
run once per unique finding location. Silently produces no annotation if
`lesson_dir` isn't a git repo, or if a specific path has no commit history.
Motivation: I manually did this (via ad-hoc shell one-liners) to split the
`oss-license-workshop` audit findings into six per-owner GitHub issues; this
makes that reusable without re-deriving the git-log incantation each time.

**AI review glossary-gap criterion** (`checker/ai_review.py`): the `--ai`
review's prompt gained a sixth grading criterion (previously five:
objectives, formative assessment, audience fit, scope/cognitive load,
tone). It reads `learners/reference.md` (via a new `_read_glossary()` in
`cli.py`, which returns `""` if the file is missing OR still matches the
`SUPPORT_FILE_CHECKS["learners/reference.md"]` placeholder fingerprint) and
asks the model to list terms of art/jargon the episode uses that aren't
already glossed, each with a one-sentence definition scoped to how *this*
lesson uses the term, explicitly instructed to skip anything the episode
already explains inline.

**Live-verified** (`--backend claude`, against the real
`episodes/why-license.md`): correctly reported "the glossary is empty" and
suggested 7 terms (copyright, IP, open source software, open source
license, all rights reserved, licensor/licensee, public domain), including
flagging "public domain" specifically because the episode's own Myth/Fact
challenge item hinges on the public-domain-vs-public-availability
confusion, a genuinely good catch I hadn't spotted myself when auditing the
episode by hand.

**Something that happened during this same session, unrelated to the code
itself**: the first PR for this round (#14) was merged via GitHub's web UI
at a moment when its cached "PR head" display was stale, one commit behind
the actual branch tip. The merge only pulled in the first of two commits.
I caught this afterward by checking `git merge-base --is-ancestor <sha>
origin/main` directly rather than trusting `gh pr view --json commits`
(which was also serving stale cached data at that moment). Separately, when
building the follow-up PR to recover the missing commit, I branched off
local `main` right after `git fetch origin`, fetch updates `origin/main`,
not local `main`, so that branch was built on a ref 4 commits stale. I
caught *that* one by noticing the test count had dropped from 66 to 38 in
the PR's own CI-equivalent local run, not by any process that would
reliably catch it. Both mistakes were fixed before merging (closed the bad
PR, rebuilt off a properly-pulled `main`), but both happened, and in both
cases a green CI run on the resulting PR would NOT have caught the problem,
CI validates "does what's merged pass tests," not "is what merged the
thing that was intended."

## What's already decided, don't relitigate

- The overall two-layer architecture, pixi, three AI backends, markdown
  report format
- The existing severity conventions (structural = `error`, content
  guidance = `warning`/`info`)
- That CI runs `pixi run test` on push/PR (already shipped from the prior
  round)

## What I want you to actually challenge

1. **Exact-substring scaffold/placeholder matching, false-negative risk.**
   `SCAFFOLD_BODY_FINGERPRINTS` and `PLACEHOLDER_BULLET_TEXTS` are closed,
   hand-picked lists built from exactly what I saw in one real repo. An
   author who edits *some* of the scaffold but leaves an untouched sentence
   not in the fingerprint list (or writes `TBD`, `TODO`, `N/A`, `...` as a
   keypoint instead of `keypoint1`) sails through undetected. Is this
   closed-list approach fundamentally the wrong shape for this problem, and
   if so what's a better cheap heuristic, e.g. flagging suspiciously short
   bullet text (under N characters) instead of/in addition to exact-match
   denylisting?

2. **`SUPPORT_FILE_CHECKS` hardcodes exactly 4 paths, each with exactly one
   fingerprint string.** The existing glossary-*existence* check elsewhere
   in the same file already has a legacy-path fallback (`learners/reference.md`
   OR root-level `reference.md`, for older lessons), but this new
   content-check dict only checks the `learners/` path. Is that an
   inconsistency worth fixing, or a non-issue since content-boilerplate
   checking on a legacy-path lesson just silently finds nothing (fails
   open, not a false positive)?

3. **`--blame`'s `git log -1` picks the single most-recent committer,
   full stop.** No co-author parsing, no "who wrote the most lines"
   weighting, nothing. For a file with a one-line typo fix from someone who
   isn't its actual primary author, this misattributes ownership for
   issue-filing purposes. Is that a real problem worth `git log --follow
   --format=%an -- <path> | sort | uniq -c | sort -rn | head -1` (most
   frequent committer) or similar, or is "whoever touched it last" actually
   the more useful signal for a live multi-week check-in cadence (most
   recent activity, not historical authorship)?

4. **The AI glossary-gap criterion has zero calibration.** I ran it once,
   against one episode, and it produced output I judged good by eye. There's
   no test coverage for output *quality* (only that the prompt assembles
   correctly, which is all that's practically testable without mocking an
   LLM). Is eyeballing one live run adequate confidence for something that
   ships to other lesson authors, or is there a cheap way to get more
   signal here, e.g. running it against a handful of already-published,
   known-good Carpentries lessons with real glossaries and checking it
   doesn't hallucinate gaps that are already covered?

5. **The two merge/branch mistakes described above.** Both happened despite
   CI existing and passing throughout. What's the actual highest-leverage
   fix, requiring CI as a branch-protection check (would this even have
   caught either mistake, given both produced green CI runs), a rule to
   always merge via `gh pr merge` instead of the web UI, a rule to always
   `git fetch && git switch -C <branch> origin/main` instead of bare
   `main`, something about verifying `git merge-base --is-ancestor` before
   trusting any merge/PR-state claim, or something else entirely that
   would actually have caught these two specific failure modes?

6. **Anything else structurally off** in this round's additions that a
   careful reviewer would flag, including things not asked about above.

## What I'm not asking about

- The core two-layer architecture or first-round checks (already validated)
- Code style nitpicks
- Whether CI should exist at all (it does, decided)

## What I want back

Direct answers to each numbered point, not a survey. Say explicitly where
you're unsure rather than hedging generically. End with:
- Confidence score (1-10): is this round's addition "good enough to ship to
  a small internal audience, with known caveats documented"?
- The single highest-priority fix before anything else, and why it beats
  the other candidates, including whether that's the CI/merge-process
  question over any of the check-quality questions above.

## Adjudication outcome (2026-08-30)

External model gave 8/10 confidence as good enough to ship, with a
SHA-pinned pre-merge preflight (not required CI) as the top-priority fix.

Verified independently before adopting anything, two claims turned out to
be wrong (checked against actual code and this session's own transcript,
not taken on faith):

- **Both "unaddressed" audit findings the review opened and closed with are
  actually already implemented.** The `exercise:`/`exercises:` typo check
  (`_SINGULAR_FIELD_TYPOS`) and the unlisted-`.md`-episode warning both
  exist and were demonstrated firing correctly earlier in this same
  session. Rejected, no action.
- Claimed subprocess shell-injection risk and a `:line`-suffixed cache-key
  concern, both checked against the real code and don't apply: git
  subprocess calls already use argument-list + `--` (no shell
  interpolation), and no `Finding.location` in this codebase ever carries a
  line-number suffix. Rejected, no action.

Adopted (10 items), all implemented and tested this round:

- Expanded `PLACEHOLDER_BULLET_TEXTS` with a placeholder grammar
  (`PLACEHOLDER_GRAMMAR_RE`): TBD/TODO/FIXME as an opener, N/A/none as the
  whole bullet only (to avoid flagging "None of these licenses..."),
  punctuation-only, `xxx`, bracketed instructions
- Normalize markdown emphasis/inline-code wrapping and one trailing
  sentence-ending punctuation mark before placeholder comparison
  (`_normalize_bullet_text`), and recognize `+` and numbered-list bullet
  markers, not just `-`/`*`
- One shared `resolve_glossary_path()` used by `check_config()`,
  `check_support_files()`, and `_read_glossary()` -- fixes a real bug
  confirmed by the fix itself: the AI review's glossary reader only checked
  the modern path, so a legacy-layout lesson's real glossary would read as
  "missing" to the AI even though the existence check correctly found it
- `--blame`: renamed to "last change authored by", switched `%an` to
  `%aN` (`.mailmap` canonicalization), added date + short SHA, added a
  5-second subprocess timeout
- AI glossary-gap prompt: capped to 8 prioritized terms, requires a citing
  phrase/sentence per term, and both episode text and glossary text are now
  wrapped in `<<<...>>>` delimiters with an explicit instruction not to
  treat embedded text as commands (prompt-injection defense-in-depth)
- Boilerplate body-fingerprint findings now report a real line number
  (previously only the bullet-placeholder and title checks did)
- Documented scaffold-fingerprint provenance and drift risk in
  `_check_boilerplate`'s docstring

Deferred, needs a real scope decision, not a same-session fix:

- Block-level/whole-episode low-prose heuristic (needs corpus calibration
  first, per the reviewer's own caveat)
- Placeholder-fingerprint-plus-real-content-appended-below edge case (same
  calibration problem, narrower likelihood)
- Full AI glossary-gap evaluation corpus (6-10 published lessons, ablation
  testing, cross-backend comparison) -- real methodology, real new scope

Also adopted as a personal/session process change, not a code change: the
review correctly pointed out that required CI would not have caught either
of this session's two real merge/branch mistakes (a stale-cached PR head
merge, a follow-up branch built off unfetched local `main`), since CI only
proves the tested commit passed, not that it was the intended commit.
Verified `gh pr merge --match-head-commit` is a real flag before trusting
it. Going forward: always `git fetch` before branching off `main` (verified
via `git switch -c <branch> origin/main`, not bare `main`), and prefer
`git merge-base --is-ancestor <sha> origin/main` / `git ls-remote` over
`gh pr view`'s sometimes-stale cached fields when a merge outcome needs
confirming.

Result: `checker/lesson_check.py`, `checker/cli.py`, `checker/ai_review.py`,
`checker/report.py`, `README.md` updated; 82/82 tests passing (16 new);
re-run against the real `oss-license-workshop` audit repo to confirm same
finding count as before (no false positives/negatives from the grammar
expansion) plus the new line numbers and blame format. See PR on
`ucla-imls-open-sci/carpentries-workbench-checker`.
