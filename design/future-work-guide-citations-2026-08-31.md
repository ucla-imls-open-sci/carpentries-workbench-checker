# Future work: precise guide citations per check

Not started -- captured so whoever picks it up doesn't have to re-research
the source material. `CATEGORY_GUIDE_LINKS` in `checker/report.py` currently
maps each check category to one static, whole-page link:

```python
CATEGORY_GUIDE_LINKS: dict[str, tuple[str, str]] = {
    "config": ("Episodes and lesson structure", "https://carpentries.github.io/sandpaper-docs/episodes.html"),
    "front-matter": ("Episode front matter", "https://carpentries.github.io/sandpaper-docs/episodes.html"),
    "divs": ("Workbench Component Guide", "https://carpentries.github.io/sandpaper-docs/component-guide.html"),
    "headings": ("Episodes and lesson structure", "https://carpentries.github.io/sandpaper-docs/episodes.html"),
    "links": ("Episodes and lesson structure", "https://carpentries.github.io/sandpaper-docs/episodes.html"),
    "objectives": ("CLDT: SMART objectives", "https://carpentries.github.io/lesson-development-training/aio.html"),
    "style": ("Carpentries Lab reviewer checklist", "https://github.com/carpentries-lab/reviews/blob/main/docs/reviewer_guide.md"),
}
```

Five different categories (`config`, `front-matter`, `divs`, `headings`,
`links`) all point at the same generic sandpaper-docs page, and `style`
links to the top of `reviewer_guide.md` with no anchor even though the
checklist inside it is sectioned. The goal: cite the most specific real
source per check, not the closest generic one.

## What's actually in carpentries-lab/reviews

Pulled and read directly (2026-08-31), not from memory:

- **`docs/reviewer_guide.md`** -- has a real `## Reviewer Checklist` with
  anchored subsections: `#accessibility`, `#content`, `#design`,
  `#supporting-information`, `#general`. `#accessibility` explicitly calls
  out contractions ("does not make extensive use of contractions") --
  this is a direct, exact match for our `style` check, which currently
  links to the whole file instead of `#accessibility`.
- **`docs/templates/review_template.md`** -- the same checklist, no prose
  around it, meant to be copy-pasted by a Lab reviewer. Same content as
  reviewer_guide.md's checklist, just without the surrounding process
  explanation.
- **`docs/editor_guide.md`** -- a *second*, more precise checklist (what a
  Lab Editor checks before review). Directly relevant, more specific than
  what we currently cite in several places:
  - `#accessibility`: "h2 is used for sections," "no 'jumps' ... e.g.
    h2->h4," "no page contains more than one h1 element." This states our
    `headings` category's rules more precisely than the generic
    sandpaper-docs episodes.html page we currently cite for it.
  - `#structure`: "Estimated times are included... Episode lengths are
    appropriate for management of cognitive load" -- matches our
    `front-matter` episode-length (20-60 min) check.
  - `#content`: "All non-discussion exercises have solutions" -- matches
    our `divs` category's "N challenge(s) but 0 solution(s)" check.
  - `#supporting-information`: "a glossary of key terms or links out to
    definitions" -- matches our glossary-existence check (currently filed
    under `config`).
  - `#design`: "Learning objectives are defined for the lesson and every
    episode" -- another legitimate citation for `objectives`, alongside
    CLDT.
- **`docs/author_guide.md`** -- checked, not useful here. It's the
  submission-process checklist (lesson title, repo URLs, DOI, JOSE
  submission, code-of-conduct/license/template confirmation) that authors
  fill out when *submitting* to Carpentries Lab for review -- not content-
  quality guidance. Doesn't map to any of our checks.

## Proposed remapping (needs real editorial judgment, not a find-replace)

| Category | Current link | Proposed |
|---|---|---|
| `style` | `reviewer_guide.md` (top) | `reviewer_guide.md#accessibility` |
| `headings` | sandpaper-docs episodes.html | keep as primary (it's the mechanical-rule source Workbench itself enforces) + add `editor_guide.md#accessibility` as a secondary "why" citation, since it states the exact rule set more precisely |
| `objectives` | CLDT aio.html only | keep CLDT + add `reviewer_guide.md#design` or `editor_guide.md#design` |
| glossary check (currently `config`) | sandpaper-docs episodes.html | `reviewer_guide.md#supporting-information` or `editor_guide.md#supporting-information` |
| `divs` (challenge/solution count) | component-guide.html | keep for div syntax + add `editor_guide.md#content` for the "solutions required" rule specifically |

`CATEGORY_GUIDE_LINKS` is currently `category -> one (label, url)` tuple.
Supporting a primary + secondary citation per category (or per specific
check within a category, since e.g. `headings` covers three different
rules with three different best sources) means either allowing a list of
tuples per category, or moving citation choice down to the individual
`Finding`'s `hint` construction in `lesson_check.py` instead of a
category-wide default in `report.py`. Worth deciding before implementing,
not deciding while implementing.

## Bonus finding: a possible new check, not just a citation fix

`editor_guide.md#accessibility` states "no 'jumps' ... e.g. h2->h4" as a
rule. `_check_headings` in `lesson_check.py` currently checks "first
heading must be level 2" and "no duplicate headings," but does **not**
check for a level *skip* mid-document (e.g. a real `h2` followed later by
an `h4` with no `h3` in between). This is a real gap against Carpentries'
own stated rule, separate from the citation-accuracy work above -- flagged
here, not scoped or built.
