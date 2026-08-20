"""Unit tests for the mechanical lesson checks.

A few of these are regression tests for real bugs found while hardening this
tool against actual lessons (see PR history): code fences hiding literal
`:::`/`#` text from the checks, a blank `episodes:` config field being a
valid "include everything" signal rather than an omission, and Workbench's
episodes/fig/-relative image path convention.
"""

from __future__ import annotations

from pathlib import Path

from checker.lesson_check import (
    _check_contractions,
    _check_divs,
    _check_front_matter,
    _check_headings,
    _check_links,
    _check_objective_verbs,
    check_config,
    check_episode,
)

VALID_EPISODE_BODY = """\
:::::: questions
- What is this?
::::::

:::::: objectives
- Learn things.
::::::

## A heading

Some content.

:::::: keypoints
- A point.
::::::
"""


def make_lesson(tmp_path: Path, config_extra: str = "", episodes: dict[str, str] | None = None) -> Path:
    lesson_dir = tmp_path / "lesson"
    (lesson_dir / "episodes").mkdir(parents=True)
    (lesson_dir / "config.yaml").write_text(
        "title: 'Real Title'\n"
        "contact: 'team@example.org'\n"
        "created: 2026-01-01\n"
        "source: 'https://example.org'\n"
        f"{config_extra}\n"
    )
    for name, body in (episodes or {}).items():
        (lesson_dir / "episodes" / name).write_text(body)
    return lesson_dir


def episode_text(front_matter: str = "title: 'Ep'\nteaching: 15\nexercises: 15", body: str = VALID_EPISODE_BODY) -> str:
    return f"---\n{front_matter}\n---\n{body}"


# -- config.yaml -------------------------------------------------------------


def test_config_placeholder_values_are_errors(tmp_path):
    lesson_dir = tmp_path / "lesson"
    (lesson_dir / "episodes").mkdir(parents=True)
    (lesson_dir / "config.yaml").write_text(
        "title: 'Lesson Title'\ncontact: 'team@carpentries.org'\ncreated: 2026-01-01\n"
    )
    findings = check_config(lesson_dir)
    messages = [f.message for f in findings]
    assert any("title" in m and "placeholder" in m for m in messages)
    assert any("contact" in m and "placeholder" in m for m in messages)


def test_config_missing_episode_on_disk_is_error(tmp_path):
    lesson_dir = make_lesson(tmp_path, config_extra="episodes:\n- ghost.md\n")
    findings = check_config(lesson_dir)
    assert any(f.severity == "error" and "ghost.md" in f.message for f in findings)


def test_config_blank_episodes_field_does_not_warn_about_unlisted_files(tmp_path):
    # A blank `episodes:` is documented Workbench behavior: sandpaper includes
    # every file automatically. This must not produce "unlisted" warnings.
    lesson_dir = make_lesson(
        tmp_path, config_extra="episodes:\n", episodes={"01-intro.md": episode_text()}
    )
    findings = check_config(lesson_dir)
    assert not any("not listed" in f.message for f in findings)


def test_config_explicit_list_missing_a_file_warns_unlisted(tmp_path):
    lesson_dir = make_lesson(
        tmp_path,
        config_extra="episodes:\n- 01-intro.md\n",
        episodes={"01-intro.md": episode_text(), "02-extra.md": episode_text()},
    )
    findings = check_config(lesson_dir)
    assert any("02-extra.md" in f.message and "not listed" in f.message for f in findings)


# -- front matter --------------------------------------------------------


def test_front_matter_missing_required_fields():
    findings = _check_front_matter({"title": "Ep"}, "ep.md")
    categories = {f.message for f in findings}
    assert any("teaching" in m for m in categories)
    assert any("exercises" in m for m in categories)


def test_front_matter_episode_length_outside_range_is_info():
    findings = _check_front_matter({"title": "Ep", "teaching": 5, "exercises": 5}, "ep.md")
    assert any(f.severity == "info" and "outside the 20-60 min" in f.message for f in findings)


def test_front_matter_episode_length_in_range_is_silent():
    findings = _check_front_matter({"title": "Ep", "teaching": 15, "exercises": 15}, "ep.md")
    assert not any("20-60 min" in f.message for f in findings)


# -- glossary -----------------------------------------------------------


def test_config_missing_glossary_is_info(tmp_path):
    lesson_dir = make_lesson(tmp_path)
    findings = check_config(lesson_dir)
    assert any(f.severity == "info" and "glossary" in f.message for f in findings)


def test_config_present_glossary_is_silent(tmp_path):
    lesson_dir = make_lesson(tmp_path)
    (lesson_dir / "reference.md").write_text("# Reference\n")
    findings = check_config(lesson_dir)
    assert not any("glossary" in f.message for f in findings)


# -- divs -----------------------------------------------------------------


def test_divs_valid_body_has_no_findings():
    assert _check_divs(VALID_EPISODE_BODY, "ep.md") == []


def test_divs_unclosed_is_error():
    body = ":::: challenge\nNo closing fence.\n"
    findings = _check_divs(body, "ep.md")
    assert any("never closed" in f.message for f in findings)


def test_divs_extraneous_close_is_error():
    body = "Some text.\n:::\n"
    findings = _check_divs(body, "ep.md")
    assert any("extraneous closing" in f.message for f in findings)


def test_divs_missing_required_blocks():
    findings = _check_divs("Just prose, no divs at all.\n", "ep.md")
    messages = [f.message for f in findings]
    assert any("questions" in m for m in messages)
    assert any("objectives" in m for m in messages)
    assert any("keypoints" in m for m in messages)


def test_divs_inside_code_fence_are_ignored():
    # A lesson teaching Workbench/Markdown syntax will show ::: literally in a
    # code block -- that must not be parsed as a real div.
    body = VALID_EPISODE_BODY + "\n```\n::: challenge\nexample text\n:::\n```\n"
    findings = _check_divs(body, "ep.md")
    assert findings == []


# -- headings ---------------------------------------------------------------


def test_headings_level_one_is_error():
    findings = _check_headings("# Top level\n\n## Ok\n", "ep.md")
    assert any(f.severity == "error" for f in findings)


def test_headings_first_not_level_two_is_warning():
    findings = _check_headings("### Starts too deep\n", "ep.md")
    assert any("expected level 2" in f.message for f in findings)


def test_headings_duplicate_is_warning():
    findings = _check_headings("## Same\n\ntext\n\n## Same\n", "ep.md")
    assert any("duplicates" in f.message for f in findings)


def test_headings_inside_code_fence_are_ignored():
    # A shell lesson's example code full of `# comment` lines must not be
    # parsed as episode headings.
    body = "## Real heading\n\n```bash\n# this is a shell comment, not a heading\n```\n"
    findings = _check_headings(body, "ep.md")
    assert findings == []


# -- links --------------------------------------------------------------


def test_links_image_missing_alt_and_missing_file(tmp_path):
    lesson_dir = make_lesson(tmp_path)
    body = "![](fig/does-not-exist.png)\n"
    findings = _check_links(body, lesson_dir, "episodes/ep.md")
    messages = [f.message for f in findings]
    assert any("no alt text" in m for m in messages)
    assert any("missing file" in m for m in messages)


def test_links_episode_relative_fig_image_resolves(tmp_path):
    # Workbench images live under episodes/fig/ and are referenced relative
    # to the episode, not the lesson root.
    lesson_dir = make_lesson(tmp_path)
    (lesson_dir / "episodes" / "fig").mkdir()
    (lesson_dir / "episodes" / "fig" / "diagram.png").write_bytes(b"")
    body = "![a diagram](fig/diagram.png)\n"
    findings = _check_links(body, lesson_dir, "episodes/ep.md")
    assert not any("missing file" in f.message for f in findings)


def test_links_html_target_resolves_against_md_source(tmp_path):
    # Sandpaper renders every .md source to a same-named .html page, so a
    # link to reference.html should resolve against reference.md.
    lesson_dir = make_lesson(tmp_path)
    (lesson_dir / "reference.md").write_text("# Reference\n")
    body = "See the [reference](reference.html) page.\n"
    findings = _check_links(body, lesson_dir, "episodes/ep.md")
    assert not any("may be broken" in f.message for f in findings)


def test_links_generic_link_text_is_warning(tmp_path):
    lesson_dir = make_lesson(tmp_path)
    body = "Read more [here](https://example.org/docs).\n"
    findings = _check_links(body, lesson_dir, "episodes/ep.md")
    assert any("generic link text" in f.message for f in findings)


# -- objectives (CLDT / Carpentries Lab checklist) ---------------------------


def test_objectives_vague_opener_is_warning():
    body = """\
:::::: objectives
- Understand how version control works.
::::::
"""
    findings, count = _check_objective_verbs(body, "ep.md")
    assert any("hard to assess" in f.message for f in findings)
    assert count == 1


def test_objectives_vague_opener_word_boundary_no_false_positive():
    # "Knowledgeable"/"Understanding-based" must not match "know"/"understand"
    # as a bare prefix -- this was a real bug (no \b in the original regex).
    body = """\
:::::: objectives
- Knowledgeable use of Git for version control.
- Understanding-based approach to Git basics.
::::::
"""
    findings, count = _check_objective_verbs(body, "ep.md")
    assert findings == []
    assert count == 2


def test_objectives_action_verb_has_no_finding():
    body = """\
:::::: objectives
- Explain how version control works.
::::::
"""
    findings, count = _check_objective_verbs(body, "ep.md")
    assert findings == []
    assert count == 1


def test_objectives_verb_check_ignores_other_divs():
    # "Understand" inside a callout, not objectives, shouldn't be flagged --
    # the check only looks at bullets inside the objectives block.
    body = """\
:::::: callout
- Understand this is just an aside.
::::::
"""
    findings, count = _check_objective_verbs(body, "ep.md")
    assert findings == []
    assert count == 0


def test_objectives_more_than_four_is_info():
    body = """\
:::::: objectives
- Explain A.
- Explain B.
- Explain C.
- Explain D.
- Explain E.
::::::
"""
    findings, count = _check_objective_verbs(body, "ep.md")
    assert count == 5
    assert any("5 objectives" in f.message for f in findings)


# -- style (contractions) ----------------------------------------------------


def test_contractions_below_threshold_is_silent():
    body = "This isn't flagged since it's only one line.\n"
    assert _check_contractions(body, "ep.md") == []


def test_contractions_above_threshold_is_info():
    body = "\n".join([f"Line {i}: don't do that, it's not right." for i in range(5)])
    findings = _check_contractions(body, "ep.md")
    assert findings and findings[0].severity == "info"


def test_contractions_possessives_are_not_counted():
    # Real bug: \w+'s matched possessives ("learner's", "Git's") as
    # contractions. Repeat past the count threshold to isolate the fix.
    body = "\n".join(
        [f"Check the learner's laptop and Git's staging area, line {i}." for i in range(5)]
    )
    assert _check_contractions(body, "ep.md") == []


def test_contractions_curly_apostrophe_is_counted():
    body = "\n".join([f"Line {i}: don’t do that, it’s not right." for i in range(5)])
    findings = _check_contractions(body, "ep.md")
    assert findings and findings[0].severity == "info"


# -- objectives assessed by exercises (Carpentries Lab checklist) -----------


def test_objectives_with_zero_exercises_is_warning(tmp_path):
    lesson_dir = make_lesson(tmp_path)
    path = lesson_dir / "episodes" / "01-intro.md"
    path.write_text(
        episode_text(
            front_matter="title: 'Ep'\nteaching: 15\nexercises: 0",
            body=VALID_EPISODE_BODY,
        )
    )
    findings = check_episode(path, lesson_dir)
    assert any("exercises: 0" in f.message for f in findings)


def test_objectives_with_nonzero_exercises_is_silent(tmp_path):
    lesson_dir = make_lesson(tmp_path)
    path = lesson_dir / "episodes" / "01-intro.md"
    path.write_text(episode_text())  # default fixture has exercises: 15
    findings = check_episode(path, lesson_dir)
    assert not any("exercises: 0" in f.message for f in findings)


# -- glossary path (Workbench convention) ------------------------------------


def test_config_glossary_at_learners_path_is_recognized(tmp_path):
    # Real bug: the check only looked at lesson_dir/reference.md, but
    # Workbench's actual convention (confirmed against workbench-template-md
    # and a real published lesson) is learners/reference.md.
    lesson_dir = make_lesson(tmp_path)
    (lesson_dir / "learners").mkdir()
    (lesson_dir / "learners" / "reference.md").write_text("# Reference\n")
    findings = check_config(lesson_dir)
    assert not any("glossary" in f.message for f in findings)


# -- end to end -------------------------------------------------------------


def test_check_episode_end_to_end_valid_episode_has_no_findings(tmp_path):
    lesson_dir = make_lesson(tmp_path)
    path = lesson_dir / "episodes" / "01-intro.md"
    path.write_text(episode_text())
    assert check_episode(path, lesson_dir) == []
