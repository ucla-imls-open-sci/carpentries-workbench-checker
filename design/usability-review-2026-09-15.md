# Lesson author usability review

Reviewed 2026-09-15. Scope: checker code, CLI, existing terminal and Markdown reports, tests, and author workflows in a local editor and GitHub. This is an expert review, not an observed user study. No checker implementation was changed. The HTML was not visually evaluated in a browser and live AI responses were not tested.

## Recommendation

Make the checker answer three questions immediately: **What should I work on next? Where is it? What would a useful change look like?**

Keep the deterministic/optional-AI split, file-first details, grouping of repeated findings, source links, and fix hints. Improve trust and the editing loop before adding more checks.

The saved baseline has 26 findings across 10 files, presented as a file checklist, 13 action-summary rows, and detailed findings across 158 lines of Markdown. The grouping helps, but authors still have to distinguish drafting work from structural faults, interpret long hints, and choose a starting point.

## Confirmed implementation problems

| Priority | Evidence | Author impact and recommended fix |
|---|---|---|
| High | `checker/lesson_check.py:272` and `:494`: a YAML list in place of a mapping raises `AttributeError` for config and `TypeError` for episode front matter in targeted probes. | An ordinary editing mistake stops the report. Validate the loaded YAML type, report the file and relevant line, and show a small `key: value` example. Continue checking independent files. |
| High | `checker/lesson_check.py:918`: `[Next](next.html)` produces a broken-link warning when `episodes/next.Rmd` exists. `![Plot](fig/plot.png "A plot")` produces a missing-image error even when the image exists. Both reproduced. | False positives waste time and erode confidence. Resolve both `.md` and `.Rmd`; parse Markdown destinations separately from optional titles. Add regression fixtures for these cases and reference-style links. |
| High | `checker/cli.py:301`: AI reviews are printed after the report has already been written and rendered. | `--ai --output report.md` omits AI feedback from the saved report; JSON on stdout is followed by non-JSON text. Collect AI results before rendering; include them in every selected format. Report partial AI failure without losing mechanical results. |
| Medium | `checker/cli.py:135`: links use Git HEAD although checks read working-tree files. | Uncommitted changes can send the author to the wrong lines on GitHub; unpushed commits may not be available there. Label the checked revision/state. Prefer local locations for modified files and keep snapshot links distinct from branch editing links. |
| Medium | `checker/cli.py:18` imports the AI module, which imports LangChain and Chroma at module load. `pixi.toml` installs the full AI environment. | The documented lightweight mechanical path still requires AI dependencies through the CLI. Lazy-load AI code and provide a small core installation/environment, with AI dependencies optional. Core still needs PyYAML, so correct the README's dependency claim. |
| Medium | `checker/report.py:169` always emits ANSI styling; the CLI defaults to terminal regardless of output extension. Existing `report.md` contains ANSI terminal output. | A natural save command produces an awkward file. When format is unspecified, infer Markdown/JSON from the filename; disable ANSI for files and non-interactive output. Explicit format should take precedence. |

## Improvements that reduce author effort

### 1. Put a short starting point before the inventory

Show at most three recommended actions, followed by complete per-file details. Use short action titles rather than copying the full explanatory hint into the summary. Keep all findings available and make any abbreviated display explicit.

For the supplied baseline, a useful starting point is:

1. Replace the sample image destination in `episodes/introduction.md:79`.
2. Finish the placeholder questions and key points in three episodes.
3. Give the two episodes still called “Using Markdown” their own titles.

Show draft completion and teaching suggestions separately from structural checks. Placeholder content matters, but ten red errors on a pre-alpha lesson can make routine drafting look like a failed build. Use visible text labels, not just emoji or color. Make CI failure policy explicit and configurable; preserve an option for strict readiness checks.

### 2. Make each finding a small editing task

Use: location, short action, evidence, one concrete suggestion, optional explanation/source. Include line numbers for front matter, objectives, and configuration, which currently often lack them. For a missing element, identify an insertion point without pretending the missing text has a source line.

Example based on an existing finding:

> **Make this objective observable**  
> `episodes/why-license.md`, Objectives block  
> Current: “Understand what an open source software license is.”  
> Suggested starting point: “Explain what permissions an open source software license gives someone using the software.”  
> Check that an exercise or discussion gives learners a chance to demonstrate this. Adapt the wording to what this episode actually teaches.

Do not automatically rewrite pedagogical content. Offer a suggestion that the author can accept or adapt. Replace judgmental phrases such as “an empty episode is more honest” with “This section still contains template examples. Replace them as you draft this episode.”

### 3. Match the scope to the author's current work

`run_checks()` always checks config and support files before applying `--episode`. A request to work on one episode therefore still includes unrelated glossary, setup, and profile work.

Make episode mode focus on that file plus configuration problems directly relevant to it. Put other lesson-wide findings in an optional summary. Accept either a filename or a file path, including an absolute editor-provided path. Add changed-file checking later; identify deleted/renamed files and affected links rather than ignoring them.

Treat unlisted episodes as potentially intentional drafts. Workbench explicitly supports leaving a new episode out of the schedule while drafting. Phrase the finding as “This episode is not in the published schedule. Add it when ready,” rather than always telling the author to add it. [Workbench episode structure](https://carpentries.github.io/sandpaper-docs/episodes.html).

### 4. Bring feedback into both editing environments

| Local editor or text editor | Editing on GitHub |
|---|---|
| A documented lightweight install and one check command. | A maintainer installs a reusable workflow once; authors need no local environment. |
| Plain `path:line:column` diagnostics and a small VS Code task/problem matcher example. Resolve paths against the lesson root, even when launched from the checker repository. | On PR updates, emit file/line annotations and a short job summary. Include a full Markdown report when needed. |
| Re-run the selected episode after saving. Add watch mode only if authors need it. | Use the PR's actual checked revision for evidence. Provide a separately labeled branch edit link when the head repository/ref are known and editing is possible. |

The existing workflow tests this tool itself; it is not a lesson-author integration. GitHub supports file/line annotations and Markdown job summaries directly. Start there before adding a bot that repeatedly posts comments. Escape author-controlled text in workflow commands, run with read-only permissions, and ensure the summary is published even when checks find errors. [GitHub workflow commands](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands).

### 5. Keep guidance specific and appropriately qualified

Add stable rule IDs and per-rule source references to `Finding`. Group by rule and corrective action rather than literal hint wording, so copy edits do not change grouping or future dismissals. Retain distinct actions within a rule.

Category-level sources are too broad: the timing suggestion currently points to episode front matter rather than the CLDT guidance it cites. Give each rule an exact section link and identify whether it is a Workbench requirement, training recommendation, Lab review criterion, or checker heuristic. Existing `design/future-work-guide-citations-2026-08-31.md` already anticipates this work.

Allow an author to mark a suggestion intentional with a reason, scoped to a rule and file. Show these decisions separately so they remain reviewable. Avoid blanket suppression of categories.

Do not imply that clearing findings proves teaching readiness. The current clean Markdown message, “Nothing to address before opening a PR,” exceeds what these checks establish. Prefer “No issues found by the selected automated checks.” Lifecycle guidance should describe draft/pilot work without automatically promoting stages. [Carpentries lesson lifecycle](https://docs.carpentries.org/resources/curriculum/lesson-life-cycle.html).

### 6. Make optional AI feedback targeted

The prompt asks about audience fit, but the CLI supplies the episode and glossary without the learner profile, prerequisites, or lesson sequence. Supply that context when available; report insufficient context when it is missing. The Lab checklist supports evaluating audience fit and assessment, but a model needs lesson-specific evidence to do that usefully. [Lab reviewer guide](https://github.com/carpentries-lab/reviews/blob/main/docs/reviewer_guide.md).

Request at most three high-value suggestions per episode, each with an exact excerpt, explanation of the learner difficulty, and a proposed revision or assessment idea. Validate quoted text against the source. Keep expanded glossary suggestions optional. Preserve source metadata in retrieved guidance: `_style_context()` currently joins only page content, discarding source attribution. Cache guidance across runs and provide an explicit refresh so repeat checks do not need to fetch and embed everything again.

## Suggested delivery order

1. **Reliability and quick wins:** YAML guards, link regressions, correct saved output, short action wording, line locations, bounded clean-report language. These are prerequisites for trusted author feedback.
2. **A complete author workflow:** lightweight core, focused episode checks, three-item starting summary, reusable GitHub workflow and editor task example.
3. **Refinement from actual use:** stable rules/sources, intentional exceptions, changed-file feedback, structured AI suggestions. Reuse the existing design notes for citations and lifecycle guidance.

Avoid making PDF styling, numerical quality scores, automatic rewriting, or a custom editor extension prerequisites for this work.

## Validation

The existing suite passed: **149 tests**, with one dependency deprecation warning. Temporary targeted fixtures reproduced the YAML crashes and two link false positives above. No source files were changed and no paid/live AI review was run.

After implementation, ask several lesson authors to fix one structural problem, one placeholder, and one objective suggestion, using both local and GitHub workflows. Observe whether they can choose a next action, reach the correct line, make a change without reading a long guide, and confirm that the finding disappears. Measure completion time, mistaken edits, and clarification requests. These are proposed usability checks, not results already demonstrated.
