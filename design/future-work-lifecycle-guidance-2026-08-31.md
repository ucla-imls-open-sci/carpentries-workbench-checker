# Future work: lesson lifecycle "what's next" guidance

Not started. Idea: since the checker already reads `life_cycle` from
`config.yaml` (`LessonMetadata.life_cycle`, via `read_lesson_metadata`) and
already computes error/warning/note counts, it could tell the author what
concretely stands between the lesson and its next lifecycle stage, instead
of just reporting `life_cycle` as a fact in the header.

## The actual stages and criteria

Source: https://docs.carpentries.org/resources/curriculum/lesson-life-cycle.html
(fetched and quoted 2026-08-31, not from memory).

| Stage | Advances to next when | Verbatim |
|---|---|---|
| Pre-alpha -> Alpha | a first draft is complete | "This label is typically applied to a lesson until a first draft has been completed." |
| Alpha -> Beta | developers are confident it's ready for other instructors to pilot | "This label is typically applied to a lesson after its first draft has been completed, and before the first pilot workshops take place" |
| Beta -> Stable | feedback from beta pilot workshops has been incorporated | "This label is typically applied to a lesson after feedback from beta pilot workshops has been incorporated." |

**Who approves the change matters and differs by lesson type** -- worth
surfacing since Tim's own lessons are mostly Incubator/Library Carpentry,
not official program lessons:

- **Incubator lessons** (most of what's in `~/projects/lessons/content`):
  self-declared. "lesson developers are free to choose whichever label
  they feel is appropriate."
- **Carpentries Lab lessons**: should already be marked stable after peer
  review (the Lab review process, see `future-work-guide-citations-2026-08-31.md`,
  gates this).
- **Official Carpentries program lessons** (Library/Data/Software
  Carpentry): needs "consultation with the relevant Curriculum Advisory
  Committee and/or the Curriculum Team" -- not something a local tool can
  verify or grant.

## What's actually machine-checkable here (and what isn't)

Two of the three transitions have decent automatable proxies using data
the checker already has. The third does not, and shouldn't be faked:

- **Pre-alpha -> Alpha** ("first draft complete"): reasonable proxy =
  zero `boilerplate`-category findings (no unwritten scaffold episodes or
  placeholder support files left). This is exactly what `boilerplate`
  already checks for.
- **Alpha -> Beta** ("confident it's ready for other instructors to
  pilot"): reasonable proxy = zero `error`-severity findings, and ideally
  a low/zero `warning` count. Not a perfect proxy (confidence is a human
  judgment) but a defensible "here's what's still rough" signal.
- **Beta -> Stable** ("beta pilot feedback incorporated"): **not
  checkable at all** from repo content -- this requires knowing whether a
  pilot happened and whether feedback was addressed, information this
  tool has no access to. Any implementation should say something like "no
  mechanical check applies here -- this is a human judgment call based on
  pilot feedback," not silently omit stage-3 guidance or fake a check.

## Sketch of the feature (not designed in detail, just the shape)

A new section in the report (terminal/markdown/HTML/PDF), something like:

```
## Next steps: pre-alpha -> alpha

3 boilerplate finding(s) remain (unwritten scaffold). Clear these to reach
alpha ("first draft complete"). See the Files/Action Summary above for
which ones.
```

or, if already past what's checkable:

```
## Next steps: alpha -> beta

0 errors, 2 warnings remaining. Close to ready for outside instructors to
pilot -- the 2 warnings above are worth a look first.
```

or, at beta:

```
## Next steps: beta -> stable

No mechanical check applies -- this stage advances once feedback from a
beta pilot workshop has been incorporated, which only you know the status
of.
```

Open questions for whoever builds this, not resolved here:

- Does this replace or sit alongside the existing lesson-metadata block?
- Does it need its own CLI flag (e.g. `--next-steps`) or is it always-on
  given metadata is already always-on?
- Should the Incubator-vs-official-program distinction change the wording
  (self-declare vs "needs Curriculum Team consultation")? `LessonMetadata`
  already has `carpentry` (lc/dc/swc/cp/incubator) to key off of.
