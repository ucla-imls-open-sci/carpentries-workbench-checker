# Validation request: report output format is hard to scan

## What this project is

`carpentries-workbench-checker` is a small internal CLI tool (UCLA IMLS
Open Science / UC OSPO Network programs) that Carpentries Workbench lesson
authors run locally before pushing, to catch structural/pedagogical
problems before waiting on the real CI build. It runs deterministic checks
(front matter, required divs, headings, links, objective quality,
boilerplate/placeholder detection, contractions, etc.) against a lesson
repo and produces a report someone reads to decide what to fix. It is not
being redesigned architecturally this round -- this round is narrowly about
**how the findings are laid out on the page**, because a real user found
the current layout hard to scan.

## The complaint, verbatim

> "let's /validate-external on the output format for this report, e.g. the
> task lists as one line, without structure below that. it is hard to read
> by me. i want something ppl can scan and see what is off, what needs to
> change, etc."

This is the person who actually reads these reports (a UCLA library
director reviewing lesson repos, sometimes handing the PDF to a lesson
maintainer who isn't in this codebase at all). "One line, no structure
below it" and "hard to scan" are the two concrete complaints to solve for.

## The current design (exact code + a real example)

Findings are a flat dataclass: `severity` (error/warning/info), `category`
(config/front-matter/divs/headings/links/objectives/style/boilerplate),
`message`, `location`, optional `hint`, optional `line`. The markdown
renderer (`checker/report.py::render_markdown`, the source both the
plain-markdown output and the Quarto-rendered HTML/PDF come from) groups
findings by file, then emits each one as a single bullet line plus an
optional indented italic line underneath:

```python
for location, items in by_location.items():
    lines.append(f"## {location}{_blame_suffix(location, blame)}")
    lines.append("")
    for f in items:
        icon = SEVERITY_ICON_PLAIN.get(f.severity, "")
        box = "- [ ]" if f.severity in ("error", "warning") else "-"
        where = _markdown_location_link(location, f.line, github_base)
        entry = f"{box} {icon} {where} **{f.category}** — {f.message}"
        lines.append(entry)
        if f.hint:
            lines.append(f"      *Fix:* {f.hint}{_guide_link_markdown(f.category)}")
        elif f.category in CATEGORY_GUIDE_LINKS:
            lines.append(f"      *Guide:*{_guide_link_markdown(f.category)}")
    lines.append("")
```

Real output, from a just-generated report against a live lesson
(`librarycarpentry/lc-r`), unedited:

```markdown
## episodes/01-intro-to-r.Rmd

- [ ] ⚠️ [episodes/01-intro-to-r.Rmd:228](https://github.com/.../01-intro-to-r.Rmd#L228) **headings** — heading `Exercise` on line 228 duplicates the one on line 175
      *Guide:* [Episodes and lesson structure](https://carpentries.github.io/sandpaper-docs/episodes.html)
- [ ] ⚠️ [episodes/01-intro-to-r.Rmd:236](https://github.com/.../01-intro-to-r.Rmd#L236) **headings** — heading `Solution` on line 236 duplicates the one on line 182
      *Guide:* [Episodes and lesson structure](https://carpentries.github.io/sandpaper-docs/episodes.html)
- [ ] ⚠️ [episodes/01-intro-to-r.Rmd:662](https://github.com/.../01-intro-to-r.Rmd#L662) **headings** — heading `Exercise` on line 662 duplicates the one on line 175
      *Guide:* [Episodes and lesson structure](https://carpentries.github.io/sandpaper-docs/episodes.html)
```

Rendered (HTML/PDF via a Quarto custom-format extension, same markdown
source): each finding is one paragraph-height line -- checkbox, small
emoji, a blue link, a bold category word, an em dash, then the message, all
run together left-to-right -- followed by an indented, italicized "Fix:" or
"Guide:" line in smaller visual weight than the finding itself. There is no
table, no columns, no visual separation between "what's wrong" and "what
to do about it" beyond that one line being indented and italic.

At the top of the whole report there IS a scannable piece: a **Files**
checklist (one line per file, `- [ ] path — N issue(s)`), so file-level
triage already works. The complaint is specifically about the
**per-finding detail underneath each file heading**.

**A real scale data point**: in the `lc-r` example above, 14 of that
lesson's 22 warnings are the exact same root cause (a `Solution`/`Exercise`
heading reused across challenges instead of given unique text) -- but the
current layout presents all 14 as visually identical, independent
one-liners grouped by *file*, so the fact that it's one repeated pattern
across the whole lesson doesn't show at a glance; a reader has to notice it
themselves by reading 14 near-identical lines.

## What's already decided -- don't relitigate

- The underlying `Finding` data model (severity/category/message/location/
  hint/line) is fixed for this round. This is a rendering-layer question,
  not a data-model question.
- Terminal and JSON output formats are not part of this complaint (only
  markdown/HTML/PDF, which share the same `render_markdown` source) and
  aren't being touched.
- The Quarto custom-format-extension architecture (`_extensions/checker-report/`,
  which owns theme/colors/margins) stays. This round is about markdown
  *structure* (what elements exist: bullets vs. tables vs. definition
  lists vs. `<details>` blocks), which the extension's CSS/LaTeX can then
  style -- not about switching rendering pipelines.
- GitHub blob deep-linking (`path:line` -> a real `#L42` GitHub URL) and
  the file-level checklist at the top both work and should be kept.
- Severity icons (❌/⚠️/ℹ️) and the checkbox-vs-bullet distinction
  (actionable vs. info-only) should be kept as signals, just not
  necessarily rendered the same way.

## Specific questions -- please give concrete answers, not general advice

1. **Is grouping by file the wrong primary grouping for scannability?**
   Given the real example above (14/22 warnings are one repeated pattern),
   would grouping by *category* first (all "duplicate heading" findings
   together, so the repetition is visually obvious as one pattern instead
   of 14 separate lines) -- with file:line as a sub-detail -- surface "what
   needs to change" faster than the current file-first grouping? Or is
   file-first still right because the reader fixes one file at a time
   regardless of how many categories it touches?

2. **Should each finding be a table row instead of a bullet + indented
   line?** A markdown table (`| ⚠️ | file:line | category | message | fix |`)
   would put "what's wrong" and "what to do" in separate columns a reader's
   eye can scan down, instead of one run-on line. Concrete downsides to
   weigh: table cells can't easily wrap a long message/fix without getting
   unreadable in a narrow terminal-width markdown viewer (e.g. GitHub's PR
   diff view, VS Code's default markdown preview), and long URLs inside
   table cells break table alignment in plain-text markdown. Is a table the
   right call here, and if column width is the real risk, what's the
   concrete alternative (definition list? two-line card format with a
   visual left border per finding? HTML `<dl>` since this already renders
   through Quarto/pandoc which allows raw HTML)?

3. **Should "Fix:" stop being a trailing italic line and become the
   visually primary element?** Right now the *problem* description reads
   first, in full sentence form, and the *fix* is secondary and smaller.
   For someone who just wants to know "what do I change," should the fix
   text lead (e.g. bold imperative first: "**Give this Solution a unique
   heading**" then the detail below), rather than leading with a passive
   description of what's wrong?

4. **What's the concrete "scannable" structure you'd actually ship**, given
   this renders through Quarto/pandoc (so raw HTML in the markdown source
   is available, e.g. `<details>`/`<summary>` for collapsible per-file or
   per-category sections, `<dl>` definition lists, or CSS classes the
   `checker-report` Quarto extension can style)? Please show a redrafted
   example of the exact `lc-r` excerpt above (the 3 duplicate-heading
   findings, plus the one `config.yaml` error) in your proposed structure,
   not just a description of the idea.

5. **Confidence score (1-10)** on your top recommendation, and what would
   most likely prove it wrong (e.g. "this only helps if most lessons have
   >1 finding per category, small lessons with 2-3 total findings won't
   benefit and the extra structure is overhead").

Please give concrete corrections (real restructured markdown/HTML
examples, not descriptions of formats) so they can go through an
adopt/reject pass against the actual codebase before anything changes.

## Outcome

Two rounds. Round 1 (general UX advice) recommended severity -> category ->
shared-fix grouping for the whole detail section, replacing file-first
entirely. Built and tested it -- worked, verified via a real render through
`checker-report` (Quarto extension) that nested checkboxes and headings
inside a `>` blockquote render correctly in both HTML and PDF. Two things
were caught during that verification, not proposed corrections: (1) a
severity emoji inside a `##`/`###` heading breaks in PDF -- LaTeX's font has
no glyph for it, renders as a broken box in both the heading and the PDF
TOC, so the shipped design keeps emoji inline in body text only, never in
headings; (2) the reviewer's worked example invented a `config.yaml`
finding ("keywords still template default") that this tool doesn't actually
check -- the real finding in that same data was `contact`, not `keywords`.
Not adopted as presented; real data substituted.

Round 2, run independently by the user with actual usability-research
citations (Johnson et al. ICSE 2013, Nachtigall et al. ISSTA 2022, GOV.UK's
error-summary pattern, Google's Tricorder), revised the recommendation:
keep the *detail* section file-first (matches the actual editing workflow --
someone with one file open in an editor wants everything about that file in
one place, not scattered across category sections), and let a new top-level
pattern-summary table do the "is this one repeated problem" job instead.
The GOV.UK citation is real and relevant but was validated for a form
corrected in place on the same page; this report is read once then acted on
elsewhere, so the transfer isn't exact -- the citation's own evidence table
rated file-vs-category grouping "moderate, not directly tested," same
strength either way.

**Final shape shipped** (splits the difference, keeps what both rounds
independently agreed on): Files checklist (unchanged) -> a cross-lesson
Action Summary table, one row per exact shared `hint`, not one row per
finding or per file -> file-first detail sections, each `## location`, with
findings inside a file that share an exact `hint` still collapsed into one
`**Change:**` + occurrence checklist + single `**Guide:**` line rather than
N separate cards. Grouping key is the literal `hint` string throughout,
never normalized `message` text (both rounds agreed stripping/normalizing
message text would eventually merge unrelated findings or silently stop
grouping when wording changed).

Verified against a live example (`librarycarpentry/lc-r`): the busiest file
(`episodes/01-intro-to-r.Rmd`, 8 findings) collapsed from 8 separate lines
to 3 blocks (7 duplicate-heading warnings -> 1 change-group, plus 2
one-offs), and the lesson-wide 16-occurrence duplicate-heading pattern
across 4 files shows as one Action Summary row. `checker/lesson_check.py`,
`checker/report.py`, `README.md`, `tests/test_report.py` updated; 142/142
tests passing (13 new, covering the grouping logic directly plus the
rendered structure). One follow-up not done this round: several existing
`hint` strings (the CLDT ones) read as explanatory sentences rather than
short imperatives, which makes them long in the Action Summary table's
"What to change" column -- a content pass on hint wording, not a rendering
change, flagged but out of scope here.
