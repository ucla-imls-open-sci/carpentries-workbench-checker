Carpentries Workbench Checker
==============================

[![License: BSD 3-Clause](https://img.shields.io/badge/License-BSD_3--Clause-blue.svg)](LICENSE)

Local pre-flight checks for [Carpentries Workbench](https://carpentries.github.io/workbench/)
lessons: a fast, deterministic structure check (front matter, required
`:::` blocks, headings, links/images), plus an optional AI narrative review
of writing and pedagogy. Point it at a local lesson directory or a lesson's
git URL; run it before opening a PR instead of waiting on the sandpaper CI
build.

## Why two layers

Real Carpentries CI (`sandpaper::validate_lesson()` and the `pegboard`
package's `validate_divs()` / `validate_headings()` / `validate_links()`, run
inside a Docker container on every PR) is authoritative but slow — several
minutes, and it only runs after you push. `checker/lesson_check.py` mirrors
the same rules locally, in under a second, with no dependencies beyond
Python: required front matter (`title`, `teaching`, `exercises`), the three
required top-level blocks (`questions`, `objectives`, `keypoints`), balanced
and recognized `:::` div types, heading rules (start at `##`, no `#`, no
duplicates), broken internal links/images (including the
`episodes/fig/`-relative image convention Workbench actually uses, and the
fact that `.html` links point at rendered `.md` sources, not literal files),
and whether an episode (or `learners/setup.md`, `instructors/instructor-notes.md`,
`profiles/learner-profiles.md`) is still the unedited scaffold Sandpaper
generated, structurally complete but never actually written.

None of that requires a model. The AI layer (`checker/ai_review.py`) is for
the part a deterministic checker can't do: whether a challenge is
pedagogically sound, whether the tone matches the
[style guide](https://carpentries.github.io/sandpaper-docs/instructor/style.html),
whether something will confuse a learner encountering it fresh. It's given
the mechanical findings as context so it doesn't repeat them.

This is a local approximation, not a replacement for the real CI check —
sandpaper is still the final word.

## Setup

Uses [pixi](https://pixi.sh) for the whole environment, including Ollama
itself (installed from conda-forge, no separate `brew install ollama` step
needed):

```bash
pixi install
```

## Running the checker

```bash
# Mechanical checks only, terminal output
pixi run check ./my-lesson

# Or check a lesson straight from its git URL (clones to a temp dir, cleans up after)
pixi run check https://github.com/librarycarpentry/lc-git.git

# Markdown checklist you can paste into a PR description or read locally
pixi run check ./my-lesson --format markdown --output report.md

# Same, rendered to HTML with Quarto if you have it installed (falls back to
# a warning + the markdown file if you don't)
pixi run check ./my-lesson --format markdown --output report.md --html

# One episode only
pixi run check ./my-lesson --episode 03-sharing.md

# Machine-readable, e.g. for a CI step of your own
pixi run check ./my-lesson --format json

# Annotate each file's findings with who last touched it (git log -1) --
# turns the markdown report into something you can split straight into
# per-owner follow-up issues. Requires my-lesson to be a git repo; silently
# skipped (no annotations, no error) otherwise.
pixi run check ./my-lesson --format markdown --blame --output report.md
```

Exit code is `1` if any error-level finding was reported, `0` otherwise —
safe to use in a pre-commit hook or your own CI step.

### Adding the AI narrative review

Off by default (it costs time, and for `claude`/`codex` it costs API usage).
Add `--ai`:

```bash
pixi run check ./my-lesson --episode 03-sharing.md --ai --backend ollama
pixi run check ./my-lesson --episode 03-sharing.md --ai --backend claude
pixi run check ./my-lesson --episode 03-sharing.md --ai --backend codex
```

All three backends use the same local Ollama embedding model
(`nomic-embed-text`) to retrieve relevant style-guide passages — that part
never leaves your machine or costs anything, regardless of which backend
answers the actual question.

Alongside objectives/assessment/audience-fit/scope/tone, the review also
grades a sixth criterion: **glossary gaps**. It reads the lesson's
`learners/reference.md` (treating it as empty if it's still the
`sandpaper::create_lesson()` placeholder, so an unwritten glossary doesn't
get mistaken for "nothing's missing") and lists terms of art, acronyms, or
domain-specific jargon the episode uses but doesn't define, each with a
one-sentence draft definition scoped to how *this* lesson actually uses the
term. Skips anything the episode already explains inline, and anything
already covered (even loosely) in the existing glossary.

| Backend | What it needs | Notes |
|---|---|---|
| `ollama` | `pixi run pull-models` (see below), `ollama serve` running | Fully local, free, slower and less sharp than the API backends |
| `claude` | `ANTHROPIC_API_KEY` set, or `ant auth login` | Uses the Anthropic Python SDK directly. Default model `claude-opus-5`; override with `--model claude-sonnet-5` or `--model claude-haiku-4-5` if you want cheaper/faster over Opus's quality |
| `codex` | The [OpenAI Codex CLI](https://developers.openai.com/codex) (`npm install -g @openai/codex`) logged in and working (`codex exec "hello"` should just print a reply) | Shells out to `codex exec`; pass `--model <name>` to override its configured default |

`--model` overrides the default for whichever `--backend` you picked.

## Recommended local models (16GB Apple Silicon)

Pull them with pixi:

```bash
pixi run pull-models          # nomic-embed-text + qwen3.5:9b-q4_K_M (default, balanced)
pixi run pull-models-small     # nomic-embed-text + qwen3.5:4b (faster, lighter)
pixi run pull-models-coding    # qwen2.5-coder:7b (for code-heavy lessons)
```

| Model | Download | Use it for | Why |
|---|---|---|---|
| `qwen3.5:9b-q4_K_M` (default) | ~6.6 GB | General episode review | Best balance of quality and footprint at this size — 256K context, leaves real headroom on 16GB while your browser/editor are also open |
| `qwen3.5:4b` | ~3.4 GB | Quick iterative checks | Noticeably faster, still coherent; use while drafting, switch to the 9B for a final pass |
| `qwen2.5-coder:7b` | ~4.7 GB | Lessons with heavy code blocks (shell, Python, R episodes) | Coder-tuned variant reviews code samples more carefully than the general model |
| `gpt-oss:20b` | ~14 GB | A stretch option if you want the best local quality and can close everything else | Runs on 16GB via MXFP4 quantization, but leaves little headroom — expect it to be slow with other apps open |
| `nomic-embed-text` | ~274 MB | Retrieval (used by every backend, not just `ollama`) | Small, fast, good enough for retrieving style-guide passages |

Don't run the checker's Ollama backend and something else memory-hungry
(another large model, a heavy IDE) at the same time on 16GB — swap will tank
throughput long before you run out of RAM outright.

## What each check maps to

| Category | What we check | Mirrors |
|---|---|---|
| `config` | Placeholder values left unfilled, `created` date, episode list vs. files on disk, episode files under `episodes/` with no `.md`/`.Rmd` extension (invisible to both Sandpaper and this checker's own glob otherwise) | `sandpaper::validate_lesson()` |
| `front-matter` | `title` / `teaching` / `exercises` present and numeric, episode length (`teaching`+`exercises`) roughly 20–60 min | `sandpaper::validate_lesson()`, [CLDT episode scope guidance](https://carpentries.github.io/lesson-development-training/aio.html) |
| `divs` | Required `questions`/`objectives`/`keypoints`, balanced `:::` fences, recognized div types, challenge/solution counts | `pegboard::validate_divs()` |
| `headings` | First heading is `##`, no `#`, no duplicate headings | `pegboard::validate_headings()` |
| `links` | Missing alt text, broken internal links/images (including `episodes/fig/`-relative images and `.html`→`.md` resolution), generic link text (`"click here"`) | `pegboard::validate_links()`, [Carpentries Lab reviewer checklist](https://github.com/carpentries-lab/reviews/blob/main/docs/reviewer_guide.md) |
| `objectives` | Weak/unmeasurable objective verbs (`know`, `understand`, `appreciate`, ...) vs. action verbs (`explain`, `choose`, `predict`, ...) | CLDT's SMART objectives guidance |
| `style` | Heavy contraction use | Carpentries Lab reviewer checklist (accessibility, translation/ESL learners) |
| `boilerplate` | Unedited `sandpaper::create_lesson()` scaffold left in place: an episode's title or body still the generated default, or a `questions`/`objectives`/`keypoints` block that exists but only holds placeholder bullets (`keypoint1`, `Put questions here`, ...); same idea applied to `learners/setup.md`, `learners/reference.md`, `instructors/instructor-notes.md`, `profiles/learner-profiles.md`, which the checks above never look at since they aren't episodes | CLDT, a structurally-complete episode (passes every check above) can still be entirely unwritten, this is the gap between "the required blocks exist" and "someone wrote the lesson" |
| `config` | *(also)* missing lesson glossary (`reference.md`) | Carpentries Lab reviewer checklist |

Div and heading checks skip content inside fenced code blocks (```` ``` ````/`~~~`) — a lesson that teaches Markdown, Workbench syntax, or shell `#` comments will contain literal `:::`/`#` text that isn't a real div or heading.

The `objectives`, `style`, and glossary checks aren't things `sandpaper`/`pegboard` check at all — they come from [Collaborative Lesson Development Training](https://carpentries.github.io/lesson-development-training/aio.html) and [The Carpentries Lab's reviewer checklist](https://github.com/carpentries-lab/reviews/blob/main/docs/reviewer_guide.md), the same two sources the `--ai` review's retrieval now pulls from (alongside the style guide) so its narrative review grades against the same rubric a human Lab reviewer would.

## Testing

```bash
pixi run test
```

Unit tests cover the mechanical checks only (`checker/lesson_check.py`) — no
network access or local models needed. The AI review layer isn't covered by
automated tests since it calls out to live models; it's been manually
smoke-tested against a real public lesson for all three backends.

## Migrating from the old scripts

This replaces `content-checker/` (`content_check.py`, `content_check_cli.py`,
`content_check.sh`) and `llama-checker.py`, which are removed. The old
`content_check.sh -U <url>` remote-check and `-o <file>` output-to-file
options are now `pixi run check <url>` and `--output <file>`; the GUI/CLI
episode picker is gone in favor of `--episode <name>` (scripting-friendly,
and doesn't hardcode a contributor's home directory the way the old shell
script did).

`proposal_analysis.ipynb` (scores lesson proposal PDFs against a rubric via
the OpenAI API) is unrelated to lesson checking and untouched here — it
still uses the legacy `openai.Completion.create` API and could use its own
pass at some point.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Everyone participating is expected
to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## License

[BSD 3-Clause](LICENSE)
