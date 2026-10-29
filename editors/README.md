# wbcheck in your editor

Pick the editor you use. The first three views touch no lesson files. The
inline notes at the end are optional and do.

Every view reads findings from the last `wbcheck check`. Re-run it after you
edit (`wbcheck check . --quiet`) to refresh.

| Editor | How findings show | Needs |
|---|---|---|
| nvim / vim | quickfix list | `wbcheck fix` (see the main README) |
| RStudio | Markers pane | `editors/wbcheck-markers.R`, jsonlite, rstudioapi |
| Positron / VS Code | Problems panel | a task with a problem matcher |
| Positron / VS Code | Problems panel with rule help | the SARIF Viewer extension |
| any editor | comments in the file | `wbcheck fix --annotate` |

## RStudio: Markers pane

```r
source("path/to/carpentries-workbench-checker/editors/wbcheck-markers.R")
wbcheck_markers()                 # shows findings from .wbcheck/results.json
wbcheck_markers(refresh = TRUE)   # runs `wbcheck check` first
wbcheck_markers(min_severity = "warning")
```

It calls `rstudioapi::sourceMarkers()` (RStudio 0.99.225 or newer). Click a
marker to jump to the file and line. `wbcheck_marker_frame()` builds the table
without RStudio if you want to look at it.

## Positron or VS Code: Problems panel

Both read the same `tasks.json`. Save this as `.vscode/tasks.json` in the
lesson folder (Positron also reads it):

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "wbcheck",
      "type": "shell",
      "command": "wbcheck check . --quiet; wbcheck report . --lines -",
      "problemMatcher": {
        "owner": "wbcheck",
        "fileLocation": "absolute",
        "pattern": {
          "regexp": "^(.+):(\\d+):(\\d+): (error|warning|info) (\\S+) (.*)$",
          "file": 1, "line": 2, "column": 3, "severity": 4, "code": 5, "message": 6
        }
      }
    }
  ]
}
```

Run it with Terminal > Run Task > wbcheck. Findings appear in the Problems
panel. The `;` matters: `wbcheck check` exits 1 when it finds errors, and
the report must still run.

`wbcheck report . --lines -` prints one line per finding:

```
/path/to/lesson/episodes/01-intro.md:16:1: warning WB213 heading `#### Too deep` on line 16 jumps from level 2 to level 4
```

Use `--lines FILE` to write it to a file instead.

## Positron or VS Code: SARIF

```bash
wbcheck report . --sarif wbcheck.sarif
```

Open `wbcheck.sarif` with the SARIF Viewer extension
(`MS-SarifVSCode.sarif-viewer`). It lists results with each rule's title and
help. Keep the file out of the lesson repo: add `wbcheck.sarif` to
`.gitignore`, or write it under `.wbcheck/`, which already ignores itself.

SARIF 2.1.0 also loads into GitHub code scanning. wbcheck sets `partialFingerprints`
from its finding ID, so a result keeps its identity when its line moves.

## Inline notes (edits lesson files)

For an editor with no problems panel, or to leave a trail for a co-author:

```bash
wbcheck fix . --annotate              # add a comment above each flagged block
wbcheck fix . --clean-annotations     # remove exactly those comments
```

A note is one line:

```markdown
<!-- wbcheck WB213: heading `#### Too deep` jumps from level 2 to level 4 -->

#### Too deep
```

In front matter it is a YAML comment (`# wbcheck WB104: ...`). Rules:

- Running `--annotate` twice adds nothing.
- Notes never go inside a fenced code block. A finding in a code block gets its note above the opening fence.
- A note goes above the first line of the paragraph or list, not between list items, and above a div rather than between the div and its heading.
- Each Markdown note is followed by one blank line. Pandoc does not see a list or heading that starts right after a comment. `--clean-annotations` removes the blank line too, so annotate then clean restores the file byte for byte.
- A front-matter note is skipped if it would change how the YAML parses.
- Findings with no line (for example WB110) and findings in non-Markdown files (config.yaml) get no note. They are listed as skipped.
- Notes do not render. A sandpaper build of two real lessons, with and without notes, gave identical HTML apart from the comments.

Until you clean, `wbcheck check` warns about each note (WB115). To block a
push or publish in CI:

```bash
wbcheck check . --fail-on annotations
```

`--fail-on annotations` exits 1 on errors and on leftover notes. It does not
fail on other warnings. Use `--fail-on warning` if you want those too.
