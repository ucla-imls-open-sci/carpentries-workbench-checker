"""Unified CLI: fast mechanical checks, plus an optional AI narrative review.

    pixi run check <path-or-git-url> [options]

See README.md for the full flag reference and model recommendations.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from checker.ai_review import BACKENDS, review_episode
from checker.lesson_check import run_checks
from checker.report import render_html_via_quarto, render_json, render_markdown, render_terminal


def _resolve_target(target: str) -> tuple[Path, tempfile.TemporaryDirectory | None]:
    if target.startswith(("http://", "https://", "git@")):
        tmp = tempfile.TemporaryDirectory(prefix="imls-tools-")
        dest = Path(tmp.name) / "lesson"
        subprocess.run(["git", "clone", "--quiet", "--depth", "1", target, str(dest)], check=True)
        return dest, tmp
    path = Path(target).expanduser().resolve()
    if not path.exists():
        raise SystemExit(f"path not found: {path}")
    return path, None


def _write_or_print(text: str, output: str | None):
    if output:
        Path(output).write_text(text)
        print(f"wrote {output}", file=sys.stderr)
    else:
        print(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Carpentries Workbench lesson checker")
    parser.add_argument("target", help="local lesson directory, or a git URL to clone and check")
    parser.add_argument("--episode", help="only check this one episode file (by filename)")
    parser.add_argument(
        "--format", choices=("terminal", "markdown", "json"), default="terminal"
    )
    parser.add_argument("--output", help="write the report here instead of stdout")
    parser.add_argument(
        "--html",
        action="store_true",
        help="also render the markdown report to HTML with Quarto, if installed",
    )
    parser.add_argument(
        "--ai",
        action="store_true",
        help="also run an AI narrative review of style/pedagogy (costs time and, for "
        "claude/codex, API usage)",
    )
    parser.add_argument("--backend", choices=tuple(BACKENDS), default="ollama")
    parser.add_argument("--model", help="override the default model for --backend")
    parser.add_argument(
        "--embed-model",
        default="nomic-embed-text",
        help="Ollama embedding model used for local retrieval, regardless of --backend",
    )
    args = parser.parse_args(argv)

    lesson_dir, tmp = _resolve_target(args.target)
    try:
        findings = run_checks(lesson_dir, episode_filter=args.episode)
        title = f"Lesson Check Report — {args.target}"

        if args.format == "terminal":
            report_text = render_terminal(findings, title)
        elif args.format == "markdown":
            report_text = render_markdown(findings, title)
        else:
            report_text = render_json(findings, title)

        _write_or_print(report_text, args.output)

        if args.html:
            md_text = render_markdown(findings, title)
            out_path = Path(args.output).with_suffix(".html") if args.output else Path("report.html")
            rendered = render_html_via_quarto(md_text, out_path)
            if rendered is None:
                print(
                    "quarto not found on PATH -- skipping HTML render "
                    "(install from https://quarto.org, or use --format markdown)",
                    file=sys.stderr,
                )
            else:
                print(f"wrote {rendered}", file=sys.stderr)

        if args.ai:
            episodes_dir = lesson_dir / "episodes"
            episode_files = sorted(p for p in episodes_dir.glob("*.md"))
            if args.episode:
                episode_files = [p for p in episode_files if p.name == args.episode]
            for path in episode_files:
                episode_findings = [f for f in findings if f.location == path.name]
                print(f"\n--- AI review: {path.name} ({args.backend}) ---")
                review = review_episode(
                    path.read_text(),
                    episode_findings,
                    args.backend,
                    args.model,
                    args.embed_model,
                )
                print(review)

        error_count = sum(1 for f in findings if f.severity == "error")
        return 1 if error_count else 0
    finally:
        if tmp is not None:
            tmp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
