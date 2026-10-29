"""Check that `wbcheck fix --annotate` leaves a lesson's rendered HTML unchanged.

    python scripts/render_safety.py path/to/lesson

Copies the lesson twice, annotates one copy, builds both with sandpaper, and
compares every page after removing HTML comments and sorting tag attributes
(sandpaper's attribute order varies between builds). Needs Rscript with the
sandpaper package, and git. Exits 0 when all pages match, 1 when some differ,
2 when it could not build. The build of a lesson that fails on its own (for
example a missing `questions` block) is reported as 2, not as a difference.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def _normalize(html: str) -> list[str]:
    html = re.sub(r"<!--.*?-->", "", html, flags=re.S)

    def sort_attrs(m: re.Match) -> str:
        attrs = sorted(re.findall(r'[\w:-]+(?:="[^"]*")?', m[2]))
        return f"<{m[1]} {' '.join(attrs)}>"

    html = re.sub(r'<(\w+)((?:\s+[\w:-]+(?:="[^"]*")?)+)\s*>', sort_attrs, html)
    return [line for line in (x.strip() for x in html.splitlines()) if line]


def _build(lesson: Path) -> bool:
    git = ["git", "-c", "user.email=t@example.org", "-c", "user.name=T"]
    shutil.rmtree(lesson / ".git", ignore_errors=True)
    shutil.rmtree(lesson / "site", ignore_errors=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=lesson, check=True)
    subprocess.run(["git", "add", "-A"], cwd=lesson, check=True)
    subprocess.run([*git, "commit", "-qm", "snapshot"], cwd=lesson, check=True)
    done = subprocess.run(
        ["Rscript", "-e", "sandpaper::build_lesson('.', preview=FALSE, quiet=TRUE)"],
        cwd=lesson, capture_output=True, text=True,
    )
    return done.returncode == 0 and (lesson / "site" / "docs").is_dir()


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    source = Path(argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="wbcheck-render-") as tmp:
        plain, noted = Path(tmp) / "plain", Path(tmp) / "annotated"
        for dest in (plain, noted):
            shutil.copytree(source, dest, ignore=shutil.ignore_patterns(".git", "site", ".wbcheck"))
        subprocess.run(["wbcheck", "check", str(noted), "--quiet"], capture_output=True)
        added = subprocess.run(["wbcheck", "fix", str(noted), "--annotate", "--min-severity", "info"],
                               capture_output=True, text=True, stdin=subprocess.DEVNULL)
        print(added.stderr.strip().splitlines()[0] if added.stderr.strip() else "no notes added")
        for label, lesson in (("plain", plain), ("annotated", noted)):
            if not _build(lesson):
                print(f"sandpaper could not build the {label} copy; nothing compared")
                return 2
        bad = []
        pages = sorted((plain / "site" / "docs").glob("*.html"))
        for page in pages:
            other = noted / "site" / "docs" / page.name
            if not other.is_file() or _normalize(page.read_text()) != _normalize(other.read_text()):
                bad.append(page.name)
        print(f"{len(pages)} pages compared; differing: {', '.join(bad) or 'none'}")
        return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
