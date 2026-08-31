"""Local pre-flight checks for Carpentries Workbench lessons.

Mirrors (a fast, local subset of) what sandpaper::validate_lesson() and
pegboard's validate_divs()/validate_headings()/validate_links() check in CI,
plus an optional AI narrative review layered on top.
"""

__version__ = "0.1.0"  # kept in sync with pixi.toml's [workspace] version by hand
