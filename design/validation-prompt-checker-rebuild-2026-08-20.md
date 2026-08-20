# Validation request: rebuilt Carpentries lesson checker (imls-tools)

## What this project is

`imls-tools` is a small internal tool maintained by UCLA Library's IMLS Open
Science program. It's used by people authoring/maintaining Carpentries
Workbench lessons (lc-git, lc-*, and similar library-carpentry-style lesson
repos) to catch structural problems in their lesson content *before* pushing
and waiting on Carpentries' real CI, which runs `sandpaper::validate_lesson()`
and the `pegboard` R package's validators inside a Docker container and takes
several minutes per run.

I (an AI assistant, working with the maintainer) just rebuilt this tool from
scratch, replacing an older grep-based bash/Python checker. I want an
independent critique of the design before it ships more broadly. Evaluate
this as if you were reviewing a PR from an engineer you don't fully trust yet
— assume nothing was pressure-tested unless the evidence below shows it was.

## The problem domain (so you can judge the checks)

Carpentries Workbench lessons are a fixed structure:
- `config.yaml` at the lesson root: metadata (title, contact, license,
  episode order, etc.)
- `episodes/*.md` (or `.Rmd`): each has YAML front matter (`title`,
  `teaching`, `exercises` in minutes) followed by a pandoc-fenced-div-based
  body. Required top-level divs: `:::: questions`, `:::: objectives`,
  `:::: keypoints`. Optional: `challenge`, `solution`, `discussion`,
  `callout`, `testimonial`, `instructor`, `spoiler`, `prereq`, `checklist`,
  `hint`, `tab`, `group-tab`.
- Headings inside an episode body must start at `##` (level 2); `#` (level 1)
  is forbidden.
- Images conventionally live in `episodes/fig/` and are referenced by
  episodes with relative paths like `fig/foo.png` (relative to the episode's
  own directory, not the lesson root — this tripped up my first draft).
- Sandpaper renders every `.md` source to a same-named `.html` page, so an
  in-lesson link like `reference.html` has no literal file on disk; its
  source is `reference.md`.
- The real validator is `pegboard`, an R6-class-based package that parses
  the actual Markdown AST (via commonmark) and validates div structure,
  headings, and links against it.

## What I built

A Python CLI (`checker/`, run via `pixi run check <path-or-git-url>`) with
two layers:

**1. Mechanical checks (`checker/lesson_check.py`)** — regex/line-based, not
an AST parser. No dependencies beyond PyYAML. Checks:
- `config.yaml`: placeholder values left unfilled (title/contact/source),
  `created` date presence, episode list cross-referenced against files on
  disk in both directions (with a carve-out: a blank `episodes:` field is
  valid Workbench behavior meaning "include everything alphabetically," so
  that case must NOT warn about every file being "unlisted")
- Front matter: `title`/`teaching`/`exercises` present, `teaching`/`exercises`
  numeric
- Divs: stack-based balance check (push on `::: type`, pop on bare `:::`),
  required top-level divs present, div type checked against a hardcoded
  "known types" set (unknown types produce an info-level note, not an
  error), challenge/solution count mismatch (info-level only)
- Headings: first heading must be level 2, no level-1 headings, duplicate
  heading text within an episode
- Links/images: missing alt text, broken internal file references (checked
  against both the episode's own directory and the lesson root, and `.html`
  links resolved against a `.md` source instead of a literal file)

Div and heading checks explicitly skip lines inside fenced code blocks
(``` or ~~~), computed via a simple per-line boolean mask:

```python
def _code_fence_mask(body: str) -> list[bool]:
    mask = []
    in_fence = False
    for line in body.splitlines():
        stripped = line.strip()
        if not in_fence:
            if CODE_FENCE_RE.match(stripped):
                in_fence = True
                mask.append(True)
            else:
                mask.append(False)
        else:
            mask.append(True)
            if CODE_FENCE_RE.match(stripped):
                in_fence = False
    return mask
```

This was added after I found that without it, a lesson teaching Markdown or
Workbench syntax itself — or any shell lesson with `#` comments in example
code — would produce false-positive div/heading findings, because the
checker was reading `:::`/`#` inside code fences as real markup.

**2. Optional AI narrative review (`checker/ai_review.py`, `--ai` flag)** —
for judgment a deterministic checker can't make: is a challenge
pedagogically sound, does the tone match the Carpentries style guide, will
something confuse a fresh learner. Retrieval (style guide + episode-structure
docs, chunked and embedded via a local Ollama `nomic-embed-text` model into
an in-memory Chroma vectorstore, rebuilt from scratch — re-fetched over HTTP
and re-embedded — on every CLI invocation) feeds context into a prompt that
also includes the mechanical findings for that episode, so the LLM is told
not to repeat them. Three swappable backends for the actual generation step:
- `ollama` — fully local via `langchain_ollama.ChatOllama`
- `claude` — direct Anthropic Python SDK call, model defaults to
  `claude-opus-5`, user-overridable via `--model`
- `codex` — shells out to the OpenAI Codex CLI (`codex exec "<prompt>"`),
  parses stdout as the response

The Claude backend now passes `output_config={"effort": "high"}` for
Opus/Sonnet-family models (skipped for Haiku, which doesn't support it),
reasoning that pedagogy/style judgment is "intelligence-sensitive work."

**Reporting (`checker/report.py`)**: a shared `Finding` dataclass
(severity/category/message/location/hint), rendered as terminal (ANSI
colors), a Markdown checklist (`- [ ] ❌ ... *Fix:* ...`, meant to be pasted
into a PR description), JSON, or piped through `quarto render` to HTML if
Quarto is installed (skipped gracefully, not a hard failure, if it isn't).

**Environment**: managed entirely by `pixi`, including Ollama itself
(installed as a conda-forge package, not via a separate Homebrew step).

## Decisions already made — don't relitigate these

- pixi as the environment manager (matches the maintainer's existing
  toolchain across other projects)
- Three backends, all reusing the same local embedding step for retrieval
  regardless of which one generates the final text
- Markdown-checklist as the primary "actionable" report format
- No TUI (Textual) — this is a one-shot "run it, read it, fix things, run it
  again" tool, not a persistent dashboard
- BSD-3-Clause license (org convention)
- The mechanical layer is explicitly framed as an approximation / local
  pre-flight check, not a replacement for the real `sandpaper`/`pegboard` CI
  run

## What I want you to actually challenge

1. **Regex/line-based parsing vs. a real Markdown AST.** `pegboard` (the
   real validator) parses via commonmark into an actual AST. My checker is
   regex-on-lines. I already found and fixed one class of failure this
   causes (code-fence false positives). What other failure modes does a
   non-AST approach have here that I likely haven't hit yet? (Nested/oddly
   indented divs, divs using `{.challenge}` attribute-block syntax instead
   of a bare word, multi-line front matter edge cases, CRLF line endings,
   front matter delimiters that aren't exactly `---` at column 0, etc.) Is
   this fundamentally the wrong approach given a real parser already exists
   in the ecosystem (even if it's R, not Python)?

2. **False confidence risk.** The tool's whole value proposition is "catch
   problems before you push and wait on real CI." If it has false negatives
   (says clean, but `sandpaper::validate_lesson()` still fails), that's
   worse than having no tool at all, because it actively misleads the
   author. Given the approach in (1), how much should the tool's messaging
   change to guard against someone treating a clean run as a guarantee?

3. **Coverage gaps against the real validator.** Pegboard also does things
   this tool doesn't attempt at all: e.g., I don't know its full rule set.
   Based on what you know about Carpentries Workbench/sandpaper/pegboard,
   what validation categories is this tool likely missing entirely (not just
   implementing imperfectly)?

4. **Mixing a deterministic checker and an LLM reviewer in one CLI.** Is
   `pixi run check --ai --backend X` the right shape, or should the
   deterministic tool and the AI-assisted tool be separate, so people can
   depend on the deterministic one in CI/pre-commit without ever touching
   API keys or model downloads?

5. **The Codex backend integration pattern.** Shelling out to a CLI
   (`subprocess.run(["codex", "exec", ...])`) and parsing stdout as the
   answer, versus calling OpenAI's API directly. What breaks with the
   shell-out approach that wouldn't with a direct API integration (version
   drift in the CLI's output format, auth/config living outside the tool's
   control, the CLI's own sandboxing/agentic behavior doing unwanted things
   like trying to explore the filesystem for an otherwise-simple text-in/
   text-out task)? Is there a case for using the OpenAI Python SDK directly
   instead, matching how the `claude` backend calls Anthropic's SDK
   directly?

6. **Retrieval rebuilt on every invocation.** Every CLI run that touches
   `--ai` re-fetches two style-guide URLs over HTTP and re-embeds them into
   a fresh in-memory Chroma store — there's no caching across invocations.
   How much does this actually matter for a tool invoked interactively by
   one person at a time, versus being an obvious first fix?

7. **Defaulting to `effort: high` for Claude.** Reasonable, or should this
   be user-controlled given it's a cost/latency tradeoff the tool is making
   unilaterally on the user's behalf?

8. **Anything else structurally wrong** that a careful reviewer would flag
   in the architecture, not just nitpicks in individual functions.

## What I'm not asking about

- Code style/formatting nitpicks
- Whether pixi vs. poetry/uv is the right packaging choice (decided)
- Whether to add a TUI (decided against)

## What I want back

For each numbered point above: a direct answer, not a survey of
possibilities. Where you're not sure, say so explicitly rather than
hedging generically. End with:
- An overall confidence score (1-10) in the current architecture as "good
  enough to ship to a small internal audience of lesson maintainers,
  with known caveats documented"
- The single highest-priority fix you'd make before anything else, and why
  it beats the other candidates
