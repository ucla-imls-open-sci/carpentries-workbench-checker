# Contributing

Thanks for your interest in `carpentries-workbench-checker`! This is a small
tool maintained within the UCLA Library IMLS Open Science program (part of
the [UC OSPO Network](https://ucospo.net)) — currently solo-maintained, so
process here is intentionally lightweight.

## Ways to Contribute

- Bug reports and fixes, especially false positives/negatives against real
  Carpentries Workbench lessons
- New checks, grounded in an actual source (`sandpaper`/`pegboard`'s real
  validation rules, the Carpentries style guide, [Collaborative Lesson
  Development Training](https://carpentries.github.io/lesson-development-training/aio.html),
  or [The Carpentries Lab's reviewer checklist](https://github.com/carpentries-lab/reviews/blob/main/docs/reviewer_guide.md))
  — please cite the source in the PR, and tag the finding's hint text
  (`[CLDT]`, `[Carpentries Lab]`, etc.) so it's clear what's an official
  Workbench rule vs. a local heuristic
- Documentation fixes

## Finding Something to Work On

No formal issue triage process yet — check the
[Issues tab](https://github.com/ucla-imls-open-sci/carpentries-workbench-checker/issues),
or open a new one if you've found a problem or have an idea.

## Setting Up a Dev Environment

```bash
git clone https://github.com/ucla-imls-open-sci/carpentries-workbench-checker.git
cd carpentries-workbench-checker
pixi install
```

See the [README](README.md) for the full setup and usage reference.

## Running Tests

```bash
pixi run test
```

Covers the mechanical checks (`checker/lesson_check.py`) — no network access
or local models needed. If you're changing behavior in `checker/lesson_check.py`,
add a regression test alongside the fix; several existing tests exist
specifically because a real lesson surfaced a bug the synthetic cases
missed (see commit history for examples).

The AI review layer (`checker/ai_review.py`) isn't covered by automated
tests since it calls live models — changes there should be manually
smoke-tested against a real lesson before opening a PR.

## Commit Norms

No enforced format — clear, descriptive commit messages are enough. If a
commit fixes a bug found by testing against a real lesson, say which lesson
and what the actual wrong output was; that context is more useful than the
diff alone.

## Pull Requests

Branch off `main`, open a PR against it — direct pushes to `main` aren't
used here. Include what you tested and how (which lesson, what the
before/after output looked like) in the PR description; "trust me" isn't
enough for a tool whose whole job is producing trustworthy findings.

## Code of Conduct

Please read our [Code of Conduct](CODE_OF_CONDUCT.md).
