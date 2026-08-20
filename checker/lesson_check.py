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
# weak, unmeasurable objective verbs -- prefer "explain"/"choose"/"predict" over these. This is
# a denylist of *openers*, not a verb classifier: a verb absent from this list is not thereby
# "good", and a match here means "worth a second look", not "wrong" -- CLDT's actual test is
# whether attainment is directly observable, not which word an objective happens to start with.
VAGUE_OBJECTIVE_OPENER_RE = re.compile(
    r"^(know|understand|appreciate|learn about|be familiar with|become familiar with|"
    r"be aware of|grasp|(?:gain|develop) an understanding of)\b",
    re.IGNORECASE,
)

# Contractions are a closed set (pronoun/auxiliary + 't/'s/'re/...), unlike possessives
# (any noun + 's) -- matching \w+ before the apostrophe wrongly counts "learner's"/"Git's"
# as contractions. ’ covers curly/smart apostrophes from copy-pasted prose.
_CONTRACTION_STEMS = (
    "don", "doesn", "didn", "won", "wouldn", "can", "couldn", "shouldn", "isn", "aren",
    "wasn", "weren", "hasn", "haven", "hadn", "mustn", "needn", "shan",
    "i", "you", "he", "she", "it", "we", "they", "who", "what", "that", "there", "here",
    "let", "how", "where", "when", "why",
)
CONTRACTION_RE = re.compile(
    r"\b(?:" + "|".join(_CONTRACTION_STEMS) + r")['’](?:t|s|re|ve|ll|d|m)\b",
    re.IGNORECASE,
)
INLINE_CODE_RE = re.compile(r"`[^`]*`")

# Lab checklist + CLDT: "descriptive link text" -- avoid generic phrases that
# say nothing out of context (screen readers, translation).
GENERIC_LINK_TEXT = {
    "here", "click here", "this link", "link", "click", "this",
    "this page", "read more", "learn more",
}

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

    # Workbench's actual convention is learners/reference.md (confirmed against
    # both carpentries/workbench-template-md and a real published lesson) --
    # accept a legacy root-level reference.md too, since older lessons may
    # still have it there.
    glossary_candidates = (
        lesson_dir / "learners" / "reference.md",
        lesson_dir / "reference.md",
    )
    if not any(p.exists() for p in glossary_candidates):
        findings.append(
            Finding(
                "info",
                "config",
                "no glossary file found (learners/reference.md)",
                location="config.yaml",
                hint="[Carpentries Lab] Checks that no key terms are missing from the "
                "lesson glossary. This only checks the file exists, not its contents.",
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
                    hint="[CLDT] Not a hard rule -- but very short or very long episodes are "
                    "worth a second look for scope.",
                )
            )
    return findings


def _check_objective_verbs(body: str, location: str) -> tuple[list[Finding], int]:
    """Flag objectives that open with a verb that's often hard to assess
    (know/understand/...) instead of an action verb (explain/choose/predict/...)
    -- see CLDT's SMART objectives guidance and the Carpentries Lab reviewer
    checklist. Also returns the objective bullet count, reused by check_episode()
    for the "2-4 objectives per episode" and "assessed by an exercise" checks."""
    findings = []
    in_code = _code_fence_mask(body)
    lines = body.splitlines()
    depth = 0
    in_objectives = False
    objectives_depth = None
    objective_count = 0

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
        objective_count += 1
        verb_match = VAGUE_OBJECTIVE_OPENER_RE.match(bullet_text)
        if verb_match:
            findings.append(
                Finding(
                    "warning",
                    "objectives",
                    f'objective opens with a phrase that can be hard to assess '
                    f'("{verb_match.group(1)}"): "{bullet_text[:70]}"',
                    location=location,
                    hint="[CLDT] Not a hard rule -- judge by whether attainment is directly "
                    "observable, not just the opening word. An action verb (explain, "
                    "choose, predict, ...) usually makes that easier to write.",
                )
            )

    if objective_count > 4:
        findings.append(
            Finding(
                "info",
                "objectives",
                f"{objective_count} objectives in this episode",
                location=location,
                hint="[CLDT] Aim for 2-4 objectives per episode; consider splitting into "
                "multiple episodes if you need more.",
            )
        )

    return findings, objective_count


def _check_contractions(body: str, location: str) -> list[Finding]:
    """The Carpentries Lab reviewer checklist flags heavy contraction use as an
    accessibility concern for translation and ESL learners. Contractions are a
    closed set of stems (it's, don't, ...), unlike possessives (any noun + 's),
    so CONTRACTION_RE only matches known stems -- and inline code spans are
    stripped first so identifiers like `don't_do_this` don't get counted."""
    in_code = _code_fence_mask(body)
    contraction_count = 0
    word_count = 0
    for i, line in enumerate(body.splitlines()):
        if in_code[i]:
            continue
        prose = INLINE_CODE_RE.sub(" ", line)
        contraction_count += len(CONTRACTION_RE.findall(prose))
        word_count += len(prose.split())

    if word_count == 0:
        return []
    rate_per_1000 = contraction_count / word_count * 1000
    if contraction_count >= 5 and rate_per_1000 >= 5:
        return [
            Finding(
                "info",
                "style",
                f"{contraction_count} contractions found ({rate_per_1000:.1f} per 1,000 "
                "words)",
                location=location,
                hint="[Carpentries Lab] Consider spelling them out (don't -> do not) for "
                "translation and ESL learners. This threshold is a local heuristic, not "
                "an official Carpentries rule.",
            )
        ]
    return []


def _check_divs(body: str, location: str, line_offset: int = 0) -> list[Finding]:
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
                        f"unrecognized div type `{div_type}` on line {lineno + line_offset}"
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
                        f"extraneous closing `:::` on line {lineno + line_offset} with no "
                        "matching open div",
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
                f"`{div_type}` div opened on line {lineno + line_offset} is never closed",
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


def _check_headings(body: str, location: str, line_offset: int = 0) -> list[Finding]:
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
        reported_line = lineno + line_offset

        if level == 1:
            findings.append(
                Finding(
                    "error",
                    "headings",
                    f"level-1 heading `# {text}` on line {reported_line}"
                    " -- episodes must not use H1, start at H2",
                    location=location,
                )
            )
        elif not first_heading_seen and level != 2:
            findings.append(
                Finding(
                    "warning",
                    "headings",
                    f"first heading `{'#' * level} {text}` on line {reported_line} is level "
                    f"{level}, expected level 2",
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
                    f"heading `{text}` on line {reported_line} duplicates the one on line "
                    f"{seen[text]}",
                    location=location,
                )
            )
        else:
            seen[text] = reported_line

    return findings


def _check_links(body: str, lesson_dir: Path, location: str, line_offset: int = 0) -> list[Finding]:
    findings = []
    episode_dir = (lesson_dir / "episodes") if (lesson_dir / "episodes").exists() else lesson_dir
    in_code = _code_fence_mask(body)

    for i, line in enumerate(body.splitlines()):
        if in_code[i]:
            continue
        lineno = i + 1 + line_offset
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
                        hint="[CLDT/Carpentries Lab] Screen readers and translation tools "
                        "lose context with generic link text like 'click here' -- "
                        "describe the destination.",
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
        line_offset = 0
    else:
        front_matter, body = parsed
        findings.extend(_check_front_matter(front_matter, location))
        # Every check below reports line numbers relative to `body`, which
        # starts after the front matter -- offset them back to real file
        # line numbers, or every reported line is wrong by the front
        # matter's length.
        line_offset = text[: len(text) - len(body)].count("\n")

    findings.extend(_check_divs(body, location, line_offset))
    findings.extend(_check_headings(body, location, line_offset))
    findings.extend(_check_links(body, lesson_dir, location, line_offset))
    objective_findings, objective_count = _check_objective_verbs(body, location)
    findings.extend(objective_findings)
    findings.extend(_check_contractions(body, location))

    # [Carpentries Lab]: "All lesson and episode objectives are assessed by
    # exercises or another opportunity for formative assessment."
    if objective_count > 0 and front_matter.get("exercises") == 0:
        findings.append(
            Finding(
                "warning",
                "objectives",
                f"{objective_count} objective(s) declared but exercises: 0 -- nothing "
                "in this episode formally assesses them",
                location=location,
                hint="[Carpentries Lab] Consider adding a challenge, discussion, or "
                "other formative-assessment checkpoint.",
            )
        )

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
