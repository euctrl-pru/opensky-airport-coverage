"""Every published column must be nameable and explainable."""

import re
from pathlib import Path

import pandas as pd

from oac.labels import EXPLAIN, LABELS, UNRANKED, explain_block, rename

DATA = Path(__file__).resolve().parent.parent / "data"
REPO = Path(__file__).resolve().parent.parent


def test_every_ranking_column_has_a_label_and_an_explanation():
    """A column reaching a table without a label ships a raw variable name.

    Asserted against the real ranking CSVs, so adding a column to the
    aggregation and forgetting to name it fails here rather than on the page.
    """
    files = sorted(DATA.glob("ranking_tier_a_*.csv"))
    if not files:
        return  # nothing generated yet
    missing_label, missing_explain = [], []
    for col in pd.read_csv(files[-1]).columns:
        if col in UNRANKED or col.startswith("_"):
            continue
        if col not in LABELS:
            missing_label.append(col)
        elif col not in EXPLAIN:
            missing_explain.append(col)
    # Not every aggregate column reaches a published table, so this asserts on
    # the columns the ranking actually carries.
    shown = {"rank", "icao", "name", "n_gt", "detection_pct",
             "dep_continuity_p50", "arr_continuity_p50", "coverage_index",
             "dep_no_ground_pct", "merged_pct_dep", "off_s_p50", "land_s_p50",
             "off_s_p90", "land_s_p10", "fragmented_pct_dep"}
    for col in shown:
        assert col in LABELS or col in UNRANKED, f"{col} has no display name"
        if col not in UNRANKED:
            assert col in EXPLAIN, f"{col} has no explanation"


def test_labels_carry_units_and_direction():
    """A name without its unit sends the reader back to the glossary."""
    assert "%" in LABELS["detection_pct"]
    assert "s" in LABELS["off_s_p50"]
    assert "median" in LABELS["dep_continuity_p50"]


def test_rename_maps_headers_and_leaves_unknown_columns_alone():
    df = pd.DataFrame({"detection_pct": [1.0], "something_new": [2.0]})
    out = rename(df)
    assert "Flights seen (%)" in out.columns
    assert "something_new" in out.columns, "unknown columns must survive"


def test_explain_block_is_collapsed_and_covers_only_the_given_columns():
    b = explain_block(["detection_pct", "coverage_index"])
    assert 'collapse="true"' in b
    assert "Flights seen (%)" in b
    assert "Coverage index" in b
    assert "Taxi-out observed" not in b, "only the columns asked for"


def test_explain_block_is_empty_when_nothing_needs_explaining():
    assert explain_block(["icao", "name", "rank"]) == ""


#: Files whose running prose a reader sees. Headings may pair the two
#: vocabularies; body text may not use the tier names alone.
PROSE_FILES = [
    "site/index.qmd",
    "site/about.qmd",
    "site/metrics.qmd",
    "src/oac/labels.py",
]

#: "Tier A" is allowed only when immediately followed by its plain-word
#: gloss, which is what a heading looks like: "Tier A (measured)".
_ALLOWED = re.compile(r"Tier A \(measured\)|Tier B \(estimated\)")
_ANY_TIER = re.compile(r"Tier [AB]")


def test_tier_names_never_appear_without_their_plain_word_gloss():
    """A reader meeting "Tier B" alone has to go and look it up.

    The decision (2026-08-29) is that headings pair both vocabularies once --
    "Tier A (measured)" -- and body prose then uses only the plain words.
    This asserts the rule mechanically, because the alternative is that the
    tier names creep back one sentence at a time.
    """
    offenders = []
    for rel in PROSE_FILES:
        text = (REPO / rel).read_text()
        # Blank out every legitimate paired mention, then anything left that
        # still says "Tier A" or "Tier B" is a bare one.
        stripped = _ALLOWED.sub("", text)
        for m in _ANY_TIER.finditer(stripped):
            line = stripped[:m.start()].count("\n") + 1
            context = stripped.splitlines()[line - 1].strip()
            offenders.append(f"{rel}:{line}: {context[:90]}")
    assert not offenders, (
        "bare tier name in reader-facing prose; use 'measured'/'estimated', "
        "or pair it as 'Tier A (measured)' in a heading:\n"
        + "\n".join(offenders)
    )
