# Validation request: pedagogy/accessibility checks added to a Carpentries lesson checker

## Context (what came before this round)

`imls-tools` is a small internal tool for UCLA Library's IMLS Open Science
program. It's a Python CLI (`checker/`, run via `pixi run check
<path-or-git-url>`) that Carpentries Workbench lesson authors run locally
before pushing, to catch problems before waiting on the real CI
(`sandpaper::validate_lesson()` / `pegboard`'s validators, several minutes,
Docker-based). Two layers: deterministic mechanical checks
(`checker/lesson_check.py`, regex/line-based, approximating
sandpaper/pegboard's structural rules — front matter, div balance, headings,
broken links/images) and an optional `--ai` narrative review
(`checker/ai_review.py`) with three swappable backends (local Ollama, Claude
API, OpenAI's Codex CLI shelled out to).

A previous validation round already reviewed the core architecture
(regex-vs-AST parsing risk, backend integration patterns, retrieval caching).
Don't relitigate those — this round is about what got added *since*, in a
follow-up pass.

## What changed this round, and why

The maintainer pointed me at two more sources: Carpentries' own
[Collaborative Lesson Development Training](https://carpentries.github.io/lesson-development-training/aio.html)
(CLDT) lesson, and a local monorepo of lessons this team maintains
(`~/projects/lessons/content/`) that has some prior-art tooling (a
frontmatter-validating R script, an exercise-extraction Python script). I
read CLDT and followed a link inside it to
[The Carpentries Lab's actual reviewer checklist](https://raw.githubusercontent.com/carpentries-lab/reviews/main/docs/reviewer_guide.md)
— the rubric real human reviewers use to grade lessons submitted to that
program. Both go well beyond what `sandpaper`/`pegboard` check: they cover
whether a lesson is well-designed, not just well-formed.

From CLDT, the specific, concrete pieces:
- Episodes should be "20-60 minutes of content (teaching + exercises)"
- Objectives should use "action verbs such as 'explain', 'choose', or
  'predict'" rather than "passive verbs such as 'know', 'understand', or
  'appreciate', which are hard to directly assess" (this is the SMART
  objectives framework — Specific, Measurable, Attainable, Relevant,
  Time-bound)
- Formative assessment should occur "often (e.g. after every 15-20 minutes
  of teaching)"
- Accessibility: "avoid regional idioms and contractions," "descriptive
  link text (avoid 'click here')," alt text on all images, no h1/no skipped
  heading levels
- Lessons should include a glossary of key terms

From the Lab reviewer checklist (verbatim quotes), things like:
- "The lesson content does not make extensive use of contractions"
- "The lesson content does not make extensive use of colloquialisms,
  region- or culture-specific references, or idioms"
- "All lesson and episode objectives are assessed by exercises or another
  opportunity for formative assessment"
- "Exercises are designed with diagnostic power"
- "Learning objectives for the lesson and its episodes are clear,
  descriptive, and measurable"
- "No key terms are missing from the lesson glossary"

## What I actually built from this

**Deterministic checks added** (all regex/line-based, same style as the
existing mechanical checker, all low-severity `info`/`warning` not `error` —
these are guidance, not hard structural requirements):

```python
PASSIVE_OBJECTIVE_VERBS = (
    "know", "understand", "appreciate", "learn about",
    "be familiar with", "be aware of", "grasp",
)
CONTRACTION_RE = re.compile(r"\b\w+'(t|s|re|ve|ll|d|m)\b", re.IGNORECASE)
GENERIC_LINK_TEXT = {"here", "click here", "this link", "link", "click", "this"}
```

1. **Episode length**: if `teaching + exercises` (from front matter, both
   already required numeric fields) falls outside 20–60, emit an `info`
   finding. No exemption logic — a legitimately short/long episode just
   gets a note.

2. **Objective verb quality**: walks the episode body tracking div nesting
   depth with a simple counter (open `:::type` increments, bare `:::`
   decrements), flags when inside a *top-level* `objectives` div (depth==0
   when opened) and a bullet line (`- ` or `* `) starts with one of the
   `PASSIVE_OBJECTIVE_VERBS` phrases (case-insensitive, `.startswith()`
   match on the bullet text with markdown bullet markers stripped). Doesn't
   check bullets inside nested divs or other div types.

3. **Generic link text**: extends the existing link-checking function.
   Markdown link syntax `[text](url)` — previously the `text` capture group
   was discarded (`for _, path in LINK_RE.findall(line)`); now checked
   (case-insensitive, exact match after stripping) against
   `GENERIC_LINK_TEXT`.

4. **Contractions**: counts regex matches of `CONTRACTION_RE` across the
   whole episode body (excluding fenced code blocks, via an existing
   line-mask helper), fires an `info` finding if the count is `>= 5`. That
   threshold was picked without any real calibration — just "avoid noise on
   one or two incidental contractions."

5. **Missing glossary**: lesson-level (not episode-level) check in
   `check_config()` — `if not (lesson_dir / "reference.md").exists()`, emit
   an `info` finding. Doesn't check glossary *completeness* (the Lab
   checklist item is "no key terms are missing," which requires knowing
   what the key terms even are — out of reach for a regex checker), just
   presence of the file at all.

**AI review layer changes** (`checker/ai_review.py`): added the CLDT page
and the Lab reviewer_guide.md raw URL to the retrieval source list
(previously just two Carpentries style-guide/episode-structure URLs — now
four, all embedded into one shared in-memory Chroma vectorstore via a local
`nomic-embed-text` Ollama model, top-k retrieved per episode against a query
built from the first 2000 chars of the episode text). Rewrote the review
prompt's grading criteria from a generic 3-item list ("are challenges
pedagogically well-formed," "tone/clarity," "confusing for a fresh
learner") to five items explicitly mirroring the Lab checklist: SMART
objectives, formative-assessment diagnostic power, audience fit, scope/
cognitive load, dismissive-language/jargon.

**Real output** — ran `--ai --backend claude` against a live public episode
(`librarycarpentry/lc-git`'s "What is Git/GitHub?", 10-minute episode with
`exercises: 0` and objectives "recognize why version control is useful" /
"distinguish between Git and GitHub"). The enriched review:
- Called the "recognize" objective unassessable, proposed a measurable
  rewrite
- Pointed out neither objective is actually assessed by any exercise
  (`exercises: 0`) — a direct hit on the Lab checklist's "objectives are
  assessed by exercises" item
- Found two narrative "scenarios" in the episode that are functionally
  already exercises (a question posed, then immediately answered in the
  next paragraph) and proposed the two-line diff to convert them into real
  `::: challenge` / `::: solution` blocks
- Proposed a specific diagnostic multiple-choice question targeting a named
  misconception ("Git and GitHub are one product")

This is a real, qualitative jump from the pre-enrichment review, which just
gave generic style-guide-adjacent commentary.

**Separately, found while adding tests**: the previous round's PR claimed
to add `tests/test_lesson_check.py` (18 pytest cases) and the maintainer
merged it believing that was true. It wasn't — this repo's `.gitignore`
(predates the whole rewrite) had a blanket `*test*` line that silently
matched and excluded the entire `tests/` directory on every `git add`. The
file existed on the PR author's (my) local disk the whole time but was
never actually staged or committed. `main` had zero test files for one full
PR-review-and-merge cycle despite the PR description explicitly claiming
"18/18 passing" in its test plan checklist. I found this by chance (`git
diff --stat` showing the edited test file as unmodified when it should have
had large additions), not by any process that would reliably catch it.
Fixed by removing the `*test*` line and actually committing the file (now
28 cases) in this round's PR. **This repo has no CI at all — no
`.github/workflows` directory, nothing runs `pixi run test` on push or PR.**

## What's already decided — don't relitigate

- The overall two-layer architecture (deterministic + optional AI), pixi,
  three AI backends, markdown-checklist report format — all covered in a
  prior validation round
- That mechanical checks should stay low-severity (`info`/`warning`) for
  anything that's pedagogical guidance rather than a hard structural rule

## What I want you to actually challenge

1. **Is a hardcoded 7-phrase verb list too blunt?** `PASSIVE_OBJECTIVE_VERBS`
   is a `.startswith()` match against 7 fixed phrases. What's the realistic
   false-positive/false-negative rate for something this crude against real
   lesson prose? Is there a materially better cheap heuristic (e.g. a small
   fixed list of *good* action verbs to check *for* instead of bad ones to
   check *against*, so unlisted-but-fine verbs like "recognize" or
   "distinguish" — which is what real lc-git objectives actually used —
   don't risk false negatives just because they're not on either list)?

2. **Is the contraction threshold (`>= 5`) defensible, or arbitrary noise
   dressed up as a rule?** Would per-1000-words normalization matter more
   than a flat count, given episode lengths vary a lot? Is contraction-count
   even a good proxy for the actual Lab checklist concern (translation/ESL
   accessibility), or is it the kind of check that looks rigorous but
   measures the wrong thing?

3. **Lesson-level vs. episode-level scope.** CLDT explicitly gives a
   lesson-level ratio target ("3-4 lesson objectives for every 6 hours").
   Every check I added is either episode-level or a single
   file-existence check at the lesson level. Is skipping true lesson-level
   aggregation (total objectives vs. total teaching time across all
   episodes) a real gap, or is that genuinely not worth the complexity for
   a "catch the obvious stuff fast" tool?

4. **Should more of the Lab checklist become deterministic instead of only
   feeding the AI prompt?** Specific checklist items I did NOT attempt
   mechanically: "exercises are designed with diagnostic power," "example
   datasets are ... available under a CC0 license," "the lesson does not
   make use of superfluous data sets," "tools used ... are open source ...
   or there is a good reason." Are any of these more tractable
   deterministically than I'm assuming (e.g., license-string detection for
   datasets), or are they correctly AI-only territory?

5. **Retrieval mixing.** Four source documents (style guide, episode
   structure doc, the ~40-screen CLDT "all in one" page, and the Lab
   checklist markdown) all get chunked into one shared Chroma collection
   with no source weighting or filtering, retrieved by plain similarity
   against the first 2000 chars of the episode. Does mixing structural
   how-to content with pedagogical-judgment content in one undifferentiated
   index hurt retrieval relevance in practice, or is naive top-k similarity
   good enough here given the corpus is small?

6. **The CI gap, given what it just caused.** A test suite silently failed
   to ship for a full review-and-merge cycle, in a repo with zero CI, and
   the failure mode was "the PR description said it was tested" while the
   repository state said otherwise. What's the actual highest-leverage fix
   here — a GitHub Actions workflow running `pixi run test` on every PR
   (straightforward), something about how PR descriptions/test-plan
   checklists get trusted without verification, or something else you'd
   flag as the real root cause that a CI workflow alone wouldn't fix?

7. **Anything else structurally off** in this round's additions that a
   careful reviewer would flag.

## What I'm not asking about

- The core architecture questions from the previous validation round
  (already covered)
- Code style nitpicks

## What I want back

Direct answers to each numbered point, not a survey. Say explicitly where
you're unsure rather than hedging generically. End with:
- Confidence score (1–10): is this round's addition "good enough to ship to
  a small internal audience, with known caveats documented"?
- The single highest-priority fix before anything else, and why it beats
  the other candidates — including whether that's "add CI" over any of the
  check-quality issues above.

## Adjudication outcome (2026-08-20)

External model gave a confidence of 7/10 as-shipped, 8/10 once two specific
bugs were fixed, with "add CI, make it required" as the top-priority fix.

Verified independently before adopting anything (two turned out to be real
confirmed bugs, one specific number turned out to be accurate, one was
rejected on the reviewer's own reasoning):

- **Glossary path** — confirmed real bug via `gh api` against
  `workbench-template-md` and `librarycarpentry/lc-git`: both use
  `learners/reference.md`, not the root-level path the check used. Fixed.
- **Objective-verb word boundary** — confirmed real bug by reproducing it
  directly: `.startswith("know")` matched "Knowledgeable use of Git". Fixed
  with a proper regex.
- **Contraction regex** — confirmed real bug by reproducing it: `\w+'s`
  matched "learner's"/"Git's" as contractions. Rewrote against a closed set
  of contractable stems, added rate normalization.
- **"2-4 objectives per episode"** — verified as real, verbatim CLDT
  guidance (re-fetched the page) rather than assumed accurate. Implemented
  as an episode-scoped check.
- **Lesson-level 3-4-objectives/6hr ratio** — rejected, agreeing with the
  reviewer's own stated reasoning (no reliable way to locate lesson-level
  objectives yet); implemented the episode-level version instead.
- **Pin the Lab checklist verbatim into the prompt** rather than leave it to
  retrieval — adopted, cheap and directly addresses "retrieval can omit the
  very rubric it's supposed to enforce."
- **Add CI** (`pixi run test` on push/PR) — adopted immediately, given it's
  the direct fix for how the previous round's test suite went uncommitted
  for a full review cycle undetected.
- **Make CI a required status check** (branch protection) — deferred, asked
  the maintainer directly rather than assumed, since it's a repo-wide policy
  change affecting other collaborators, not a code fix.
- Dataset CC0/license evidence reporting, per-topic retrieval rework, and
  lesson-level teaching-time summaries were all deferred as new scope, not
  bugs — no evidence yet they're worth the added complexity.

Result: `checker/lesson_check.py`, `checker/ai_review.py`, and
`tests/test_lesson_check.py` updated; `.github/workflows/test.yml` added;
recalibrated against `~/projects/lessons/content` (real local lessons) to
confirm the fixes fire on genuine signal, not just the synthetic test cases.
35/35 tests passing. See PR #8 on `ucla-imls-open-sci/imls-tools`.
