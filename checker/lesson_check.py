"""Mechanical structure checks for a Carpentries Workbench lesson.

These approximate, locally and in seconds, what sandpaper::validate_lesson()
and pegboard's validate_divs() / validate_headings() / validate_links() check
in CI (see https://carpentries.github.io/sandpaper-docs/episodes.html and
https://carpentries.github.io/pegboard/). They are not a replacement for the
real CI check -- they exist so a lesson author can catch the obvious problems
before pushing and waiting on a PR build.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from checker.report import Finding

REQUIRED_TOP_DIVS = ("questions", "objectives", "keypoints")

# Non-exhaustive, but covers everything in the Workbench style guide as of 2026.
KNOWN_DIV_TYPES = {
    "questions",
    "objectives",
    "keypoints",
    "challenge",
    "solution",
    "discussion",
    "callout",
    "testimonial",
    "instructor",
    "spoiler",
    "prereq",
    "checklist",
    "hint",
    "tab",
    "group-tab",
}

CONFIG_PLACEHOLDER_VALUES = {
    "title": "Lesson Title",
    "contact": "team@carpentries.org",
    "source": "https://github.com/carpentries/workbench-template-md",
}

# Collaborative Lesson Development Training (carpentries.github.io/lesson-development-training)
# and The Carpentries Lab reviewer checklist (github.com/carpentries-lab/reviews) both call out
# weak, unmeasurable objective verbs -- prefer "explain"/"choose"/"predict" over these.
PASSIVE_OBJECTIVE_VERBS = (
    "know",
    "understand",
    "appreciate",
    "learn about",
    "be familiar with",
    "be aware of",
    "grasp",
)

# Lab checklist: "does not make extensive use of contractions" (accessibility --
# translation and ESL learners in particular).
CONTRACTION_RE = re.compile(r"\b\w+'(t|s|re|ve|ll|d|m)\b", re.IGNORECASE)

# Lab checklist + CLDT: "descriptive link text" -- avoid generic phrases that
# say nothing out of context (screen readers, translation).
GENERIC_LINK_TEXT = {"here", "click here", "this link", "link", "click", "this"}

FRONT_MATTER_RE = re.compile(r"^---\n(.*?\n)---\n(.*)$", re.DOTALL)
DIV_FENCE_RE = re.compile(r"^(:{3,})\s*\{?\.?([a-zA-Z-]*)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
LINK_RE = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)]+)\)")
CODE_FENCE_RE = re.compile(r"^(```+|~~~+)")


def _code_fence_mask(body: str) -> list[bool]:
    """One bool per line: True if that line falls inside a fenced code block.

    A lesson teaching Markdown, Workbench syntax, or shell `#` comments will
    contain literal `:::` or `#` text inside ```/~~~ blocks -- those aren't
    real divs or headings and must not be checked as such.
    """
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


def check_config(lesson_dir: Path) -> list[Finding]:
    findings: list[Finding] = []
    config_path = lesson_dir / "config.yaml"
    if not config_path.exists():
        return [
            Finding(
                "error",
                "config",
                "config.yaml not found",
                location="config.yaml",
                hint="Every Workbench lesson needs a config.yaml at its root.",
            )
        ]

    try:
        config = yaml.safe_load(config_path.read_text()) or {}
    except yaml.YAMLError as exc:
        return [
            Finding(
                "error", "config", f"config.yaml is not valid YAML: {exc}", location="config.yaml"
            )
        ]

    for field, placeholder in CONFIG_PLACEHOLDER_VALUES.items():
        value = config.get(field)
        if not value or value == placeholder:
            findings.append(
                Finding(
                    "error",
                    "config",
                    f"`{field}` is still the template placeholder or empty",
                    location="config.yaml",
                    hint=f"Set `{field}` to your lesson's real value.",
                )
            )

    if not config.get("created"):
        findings.append(
            Finding(
                "warning",
                "config",
                "`created` date is not set",
                location="config.yaml",
                hint="Set `created` to the date the lesson was started (YYYY-MM-DD).",
            )
        )

    if config.get("life_cycle") == "pre-alpha":
        findings.append(
            Finding(
                "info",
                "config",
                "`life_cycle` is still `pre-alpha`",
                location="config.yaml",
                hint="Update life_cycle as the lesson matures: pre-alpha -> alpha -> beta -> stable.",
            )
        )

    episodes_field = config.get("episodes")
    listed_episodes = episodes_field or []
    episodes_dir = lesson_dir / "episodes"
    on_disk = (
        sorted(p.name for p in episodes_dir.glob("*") if p.suffix in (".md", ".Rmd"))
        if episodes_dir.exists()
        else []
    )

    missing_on_disk = [e for e in listed_episodes if e not in on_disk]
    for name in missing_on_disk:
        findings.append(
            Finding(
                "error",
                "config",
                f"config.yaml lists episode `{name}` but it does not exist under episodes/",
                location="config.yaml",
            )
        )

    # A blank `episodes:` field is valid and documented: sandpaper then includes
    # every file under episodes/ automatically, in alphabetical order. Only flag
    # "unlisted" files when the author is curating an explicit ordered list.
    if episodes_field:
        unlisted = [e for e in on_disk if e not in listed_episodes]
        for name in unlisted:
            findings.append(
                Finding(
                    "warning",
                    "config",
                    f"episodes/{name} exists but is not listed in config.yaml `episodes:`",
                    location="config.yaml",
                    hint="Add it to the episodes list so it's included and ordered in the build.",
                )
            )

    if not (lesson_dir / "reference.md").exists():
        findings.append(
            Finding(
                "info",
                "config",
                "no reference.md (glossary) found at the lesson root",
                location="config.yaml",
                hint="The Carpentries Lab reviewer checklist checks that no key terms are "
                "missing from the lesson glossary.",
            )
        )

    return findings


def _split_front_matter(text: str) -> tuple[dict, str] | None:
    match = FRONT_MATTER_RE.match(text)
    if not match:
        return None
    try:
        front_matter = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return None
    return front_matter, match.group(2)


def _check_front_matter(front_matter: dict, location: str) -> list[Finding]:
    findings = []
    for field in ("title", "teaching", "exercises"):
        if field not in front_matter or front_matter[field] in (None, ""):
            findings.append(
                Finding(
                    "error",
                    "front-matter",
                    f"missing required front-matter field `{field}`",
                    location=location,
                )
            )
    for field in ("teaching", "exercises"):
        value = front_matter.get(field)
        if value is not None and not isinstance(value, (int, float)):
            findings.append(
                Finding(
                    "warning",
                    "front-matter",
                    f"`{field}` should be a number of minutes, got {value!r}",
                    location=location,
                )
            )

    teaching, exercises = front_matter.get("teaching"), front_matter.get("exercises")
    if isinstance(teaching, (int, float)) and isinstance(exercises, (int, float)):
        total = teaching + exercises
        if total < 20 or total > 60:
            findings.append(
                Finding(
                    "info",
                    "front-matter",
                    f"episode is {total:g} min (teaching + exercises), outside the "
                    "20-60 min range Collaborative Lesson Development Training suggests",
                    location=location,
                    hint="Not a hard rule -- but very short or very long episodes are "
                    "worth a second look for scope.",
                )
            )
    return findings


def _check_objective_verbs(body: str, location: str) -> list[Finding]:
    """Flag objectives that open with a hard-to-assess verb (know/understand/...)
    instead of an action verb (explain/choose/predict/...) -- see CLDT's SMART
    objectives guidance and the Carpentries Lab reviewer checklist."""
    findings = []
    in_code = _code_fence_mask(body)
    lines = body.splitlines()
    depth = 0
    in_objectives = False
    objectives_depth = None

    for i, line in enumerate(lines):
        if in_code[i]:
            continue
        match = DIV_FENCE_RE.match(line.strip())
        if match:
            div_type = match.group(2).lower()
            if div_type:
                if div_type == "objectives" and depth == 0:
                    in_objectives = True
                    objectives_depth = depth
                depth += 1
            else:
                depth -= 1
                if in_objectives and depth == objectives_depth:
                    in_objectives = False
            continue

        if not in_objectives:
            continue
        stripped = line.strip()
        if not stripped.startswith(("-", "*")):
            continue
        bullet_text = stripped.lstrip("-* ").strip()
        lower = bullet_text.lower()
        for verb in PASSIVE_OBJECTIVE_VERBS:
            if lower.startswith(verb):
                findings.append(
                    Finding(
                        "warning",
                        "objectives",
                        f'objective starts with a hard-to-assess verb ("{verb}"): '
                        f'"{bullet_text[:70]}"',
                        location=location,
                        hint="Prefer an action verb (explain, choose, predict, ...) -- "
                        "it's hard to observe whether a learner has developed the skill "
                        "otherwise.",
                    )
                )
                break

    return findings


def _check_contractions(body: str, location: str) -> list[Finding]:
    """The Carpentries Lab reviewer checklist flags heavy contraction use as an
    accessibility concern for translation and ESL learners."""
    in_code = _code_fence_mask(body)
    count = sum(
        len(CONTRACTION_RE.findall(line))
        for i, line in enumerate(body.splitlines())
        if not in_code[i]
    )
    if count >= 5:
        return [
            Finding(
                "info",
                "style",
                f"{count} contractions found in this episode",
                location=location,
                hint="Consider spelling them out (don't -> do not) for translation and "
                "ESL learners.",
            )
        ]
    return []


def _check_divs(body: str, location: str) -> list[Finding]:
    findings = []
    stack: list[tuple[str, int]] = []
    seen_top_level: set[str] = set()
    in_code = _code_fence_mask(body)

    for lineno, line in enumerate(body.splitlines(), start=1):
        if in_code[lineno - 1]:
            continue
        match = DIV_FENCE_RE.match(line.strip())
        if not match:
            continue
        div_type = match.group(2).lower()

        if div_type:
            stack.append((div_type, lineno))
            if not stack[:-1]:  # this is a top-level div
                seen_top_level.add(div_type)
            if div_type not in KNOWN_DIV_TYPES:
                findings.append(
                    Finding(
                        "info",
                        "divs",
                        f"unrecognized div type `{div_type}` on line {lineno}"
                        " -- verify against the Workbench style guide",
                        location=location,
                    )
                )
        else:
            if not stack:
                findings.append(
                    Finding(
                        "error",
                        "divs",
                        f"extraneous closing `:::` on line {lineno} with no matching open div",
                        location=location,
                    )
                )
            else:
                stack.pop()

    for div_type, lineno in stack:
        findings.append(
            Finding(
                "error",
                "divs",
                f"`{div_type}` div opened on line {lineno} is never closed",
                location=location,
            )
        )

    for required in REQUIRED_TOP_DIVS:
        if required not in seen_top_level:
            findings.append(
                Finding(
                    "error",
                    "divs",
                    f"missing required `{required}` block",
                    location=location,
                )
            )

    return findings


def _check_headings(body: str, location: str) -> list[Finding]:
    findings = []
    seen: dict[str, int] = {}
    first_heading_seen = False
    in_code = _code_fence_mask(body)

    for lineno, line in enumerate(body.splitlines(), start=1):
        if in_code[lineno - 1]:
            continue
        match = HEADING_RE.match(line)
        if not match:
            continue
        level, text = len(match.group(1)), match.group(2).strip()

        if level == 1:
            findings.append(
                Finding(
                    "error",
                    "headings",
                    f"level-1 heading `# {text}` on line {lineno}"
                    " -- episodes must not use H1, start at H2",
                    location=location,
                )
            )
        elif not first_heading_seen and level != 2:
            findings.append(
                Finding(
                    "warning",
                    "headings",
                    f"first heading `{'#' * level} {text}` on line {lineno} is level {level},"
                    " expected level 2",
                    location=location,
                )
            )

        if level >= 2:
            first_heading_seen = True

        if text in seen:
            findings.append(
                Finding(
                    "warning",
                    "headings",
                    f"heading `{text}` on line {lineno} duplicates the one on line {seen[text]}",
                    location=location,
                )
            )
        else:
            seen[text] = lineno

    return findings


def _check_links(body: str, lesson_dir: Path, location: str) -> list[Finding]:
    findings = []
    episode_dir = (lesson_dir / "episodes") if (lesson_dir / "episodes").exists() else lesson_dir

    for lineno, line in enumerate(body.splitlines(), start=1):
        for alt, path in IMAGE_RE.findall(line):
            if not alt.strip():
                findings.append(
                    Finding(
                        "warning",
                        "links",
                        f"image on line {lineno} has no alt text: `{path}`",
                        location=location,
                        hint="Add descriptive alt text for accessibility.",
                    )
                )
            if not path.startswith(("http://", "https://", "{{")):
                # Workbench episodes reference images (e.g. fig/foo.png) relative to
                # episodes/, not the lesson root -- check both, episode dir first.
                in_episode_dir = (episode_dir / path.lstrip("/")).resolve().exists()
                in_lesson_root = (lesson_dir / path.lstrip("/")).resolve().exists()
                if not (in_episode_dir or in_lesson_root):
                    findings.append(
                        Finding(
                            "error",
                            "links",
                            f"image on line {lineno} points to a missing file: `{path}`",
                            location=location,
                        )
                    )

        for text, path in LINK_RE.findall(line):
            if text.strip().lower() in GENERIC_LINK_TEXT:
                findings.append(
                    Finding(
                        "warning",
                        "links",
                        f'generic link text "{text}" on line {lineno}',
                        location=location,
                        hint="Screen readers and translation tools lose context with "
                        "generic link text like 'click here' -- describe the destination.",
                    )
                )
            if path.startswith(("http://", "https://", "#", "mailto:", "{{")):
                continue
            # Sandpaper renders every .md source to a same-named .html page, so a
            # link to e.g. reference.html or ../learners/setup.html has no literal
            # file on disk -- check for the .md source instead.
            check_path = path.split("#", 1)[0]
            if check_path.endswith(".html"):
                check_path = check_path[: -len(".html")] + ".md"
            if not check_path:
                continue
            search_dirs = (episode_dir, lesson_dir, lesson_dir / "learners", lesson_dir / "instructors", lesson_dir / "profiles")
            if not any((d / check_path.lstrip("/")).resolve().exists() for d in search_dirs):
                findings.append(
                    Finding(
                        "warning",
                        "links",
                        f"internal link on line {lineno} may be broken: `{path}`",
                        location=location,
                    )
                )
    return findings


def check_episode(path: Path, lesson_dir: Path) -> list[Finding]:
    location = str(path.relative_to(lesson_dir)) if path.is_relative_to(lesson_dir) else path.name
    text = path.read_text(errors="replace")
    findings: list[Finding] = []

    parsed = _split_front_matter(text)
    if parsed is None:
        findings.append(
            Finding(
                "error",
                "front-matter",
                "episode does not start with a `---` YAML front-matter block",
                location=location,
            )
        )
        body = text
        front_matter = {}
    else:
        front_matter, body = parsed
        findings.extend(_check_front_matter(front_matter, location))

    findings.extend(_check_divs(body, location))
    findings.extend(_check_headings(body, location))
    findings.extend(_check_links(body, lesson_dir, location))
    findings.extend(_check_objective_verbs(body, location))
    findings.extend(_check_contractions(body, location))

    in_code = _code_fence_mask(body)
    lines = body.splitlines()
    challenges = sum(
        1
        for i, ln in enumerate(lines)
        if not in_code[i] and re.match(r"^:{3,}\s*\{?\.?challenge", ln)
    )
    solutions = sum(
        1
        for i, ln in enumerate(lines)
        if not in_code[i] and re.match(r"^:{3,}\s*\{?\.?solution", ln)
    )
    if challenges > solutions:
        findings.append(
            Finding(
                "info",
                "divs",
                f"{challenges} challenge(s) but only {solutions} solution(s)",
                location=location,
                hint="Not every challenge needs a solution block, but double-check this is intentional.",
            )
        )

    return findings


def run_checks(lesson_dir: Path, episode_filter: str | None = None) -> list[Finding]:
    findings = check_config(lesson_dir)

    episodes_dir = lesson_dir / "episodes"
    if not episodes_dir.exists():
        findings.append(
            Finding("error", "config", "no episodes/ directory found", location=str(lesson_dir))
        )
        return findings

    episode_files = sorted(p for p in episodes_dir.glob("*") if p.suffix in (".md", ".Rmd"))
    if episode_filter:
        episode_files = [p for p in episode_files if p.name == episode_filter]
        if not episode_files:
            findings.append(
                Finding(
                    "error",
                    "config",
                    f"no episode named `{episode_filter}` found under episodes/",
                )
            )
            return findings

    for path in episode_files:
        findings.extend(check_episode(path, lesson_dir))

    return findings
