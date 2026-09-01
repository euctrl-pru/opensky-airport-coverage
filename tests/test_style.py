"""Budgets on the constructions that make the copy read as machine-written.

Not a style opinion for its own sake. A reviewer asked for prose that sounds
like a person, and "sounds like a person" is unreviewable as a diff comment.
These are the specific tics, counted, with a per-file ceiling -- so the ask
becomes something a test can hold.

Only reader-facing prose is counted: markdown outside code chunks, plus the
strings the chunks display. Code, comments and docstrings are exempt; they are
not what the reviewer read.
"""

import ast
import re
from pathlib import Path

import pytest

SITE = Path(__file__).resolve().parent.parent / "site"

#: Extended by later tasks as each file is trimmed.
FILES = ["index.qmd", "metrics.qmd", "about.qmd", "pipeline.qmd"]

#: construction -> (pattern, max occurrences per file)
BUDGETS = {
    "em-dash aside": (r"\s[—–]\s", 4),
    "'rather than'": (r"\brather than\b", 3),
    "bold lead-in": (r"\*\*[^*\n]{3,70}\*\*\s*[—–]", 0),
    "'that is the point/finding'":
        (r"\bthat is (?:the |exactly )?(?:point|finding)\b", 0),
    "'it is worth'": (r"\bit is worth\b|\bworth (?:knowing|seeing|noting)\b", 0),
    "'the point'": (r"\bthe (?:whole )?point\b", 0),
    "'silently'": (r"\bsilently\b", 0),
    "'deliberately'": (r"\bdeliberate(?:ly)?\b", 1),
    "'genuinely/actually'": (r"\b(?:genuinely|actually)\b", 2),
}

#: These are ceilings on padding, not a cap on what the site may say. Raise one
#: deliberately when a page gains a fact a reader asked for -- `index.qmd` went
#: 630 -> 645 to name the sampled days -- and never to make a passing edit fit.
#: The distinction is the whole value of the number: a budget nudged up to
#: accommodate a rewrite stops measuring anything.
WORD_BUDGET = {"index.qmd": 645, "metrics.qmd": 1100,
               "about.qmd": 460, "pipeline.qmd": 250}


def prose(name: str) -> str:
    """Markdown outside code chunks, plus every string handed to `Markdown()`.

    A page's framing text lives in both places -- `index.qmd` builds most of
    its paragraphs inside `display(Markdown(...))` so it can interpolate a
    count -- and a budget that saw only one of them would be trivially evaded.

    Parsed rather than regexed, and this matters. A regex over string literals
    also captures **docstrings** and code strings: measured against the real
    page it counted `table()`'s docstring, `downloads()`'s docstring and
    "btn btn-outline-primary btn-sm" as reader-facing prose, inflating
    `index.qmd` from 1,263 words to 1,480. A budget built on that number would
    push an implementer to delete internal documentation to pass a test about
    what the reader sees.
    """
    text = (SITE / name).read_text()
    text = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)   # YAML header
    outside = re.sub(r"```.*?```", "", text, flags=re.S)
    shown = []
    for chunk in re.findall(r"```\{python\}(.*?)```", text, re.S):
        try:
            tree = ast.parse(chunk)
        except SyntaxError:                      # a chunk mid-edit
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if (getattr(node.func, "id", None)
                    or getattr(node.func, "attr", None)) != "Markdown":
                continue
            for arg in ast.walk(node):
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    shown.append(arg.value)
    out = outside + "\n" + "\n".join(shown)
    return re.sub(r"<[^>]+>", " ", out)          # markup is not prose


def words(s: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", s))


@pytest.mark.parametrize("name", FILES)
@pytest.mark.parametrize("tic", sorted(BUDGETS))
def test_construction_stays_within_budget(name, tic):
    pattern, ceiling = BUDGETS[tic]
    found = re.findall(pattern, prose(name), re.I)
    assert len(found) <= ceiling, (
        f"{name}: {len(found)} x {tic}, budget {ceiling}. "
        f"First few: {found[:4]}"
    )


@pytest.mark.parametrize("name", FILES)
def test_page_stays_within_its_word_budget(name):
    n = words(prose(name))
    assert n <= WORD_BUDGET[name], f"{name}: {n} words, budget {WORD_BUDGET[name]}"


#: A generated page aggregates ~6 sections into one document, so the per-file
#: ceilings are scaled. Applied to prose only -- see `page_prose`.
PAGE_BUDGETS = {"em-dash aside": 8, "'rather than'": 4}
PAGE_WORD_BUDGET = 450


def page_prose(md: str) -> str:
    """A generated page's prose, with table rows removed.

    `_s(None)` renders a missing value as an em dash, so a page with blanks in
    its percentile tables carries dozens of them in cells. Counting those as a
    stylistic tic would police the blanks instead of the writing.
    """
    return "\n".join(ln for ln in md.split("\n")
                     if not ln.lstrip().startswith("|"))


@pytest.mark.parametrize("tic", sorted(PAGE_BUDGETS))
def test_generated_aerodrome_page_stays_within_budget(aerodrome_page, tic):
    pattern, _ = BUDGETS[tic]
    found = re.findall(pattern, page_prose(aerodrome_page("A")), re.I)
    assert len(found) <= PAGE_BUDGETS[tic], (
        f"aerodrome page: {len(found)} x {tic}, budget {PAGE_BUDGETS[tic]}. "
        f"First few: {found[:4]}"
    )


def test_generated_aerodrome_page_stays_within_its_word_budget(aerodrome_page):
    n = words(page_prose(aerodrome_page("A")))
    assert n <= PAGE_WORD_BUDGET, f"aerodrome page: {n} words, budget {PAGE_WORD_BUDGET}"


def label_prose() -> str:
    from oac.labels import EXPLAIN, TIERS_EXPLAINED
    return "\n\n".join(list(EXPLAIN.values()) + [TIERS_EXPLAINED])


@pytest.mark.parametrize("tic", sorted(BUDGETS))
def test_column_explanations_stay_within_budget(tic):
    pattern, ceiling = BUDGETS[tic]
    found = re.findall(pattern, label_prose(), re.I)
    # 51 definitions in one string, so the per-file ceiling is scaled rather
    # than applied to the concatenation. Scale 4, not 6: at 6 the em-dash
    # allowance is 24 against 24 present today, and a budget already satisfied
    # before the work starts tests nothing.
    allowed = ceiling * 4
    assert len(found) <= allowed, (
        f"EXPLAIN: {len(found)} x {tic}, budget {allowed}. First few: {found[:4]}"
    )


def test_explanations_stay_within_their_word_budget():
    from oac.labels import EXPLAIN, TIERS_EXPLAINED
    total = sum(words(v) for v in EXPLAIN.values())
    assert total <= 1500, f"EXPLAIN is {total} words, budget 1500"
    # 150 -> 160 on 2026-09-01: the note gained the sentence explaining the
    # asterisk in the all-aerodromes table, which is a fact a reader asked for
    # rather than padding. Everything else in the block was cut to pay for it.
    assert words(TIERS_EXPLAINED) <= 160, (
        f"TIERS_EXPLAINED is {words(TIERS_EXPLAINED)} words, budget 160")


def test_no_single_explanation_is_a_wall_of_text():
    """The longest entry was 249 words, which is a page, not a definition."""
    from oac.labels import EXPLAIN
    long = {c: words(v) for c, v in EXPLAIN.items() if words(v) > 90}
    assert not long, f"explanations over 90 words: {long}"
