"""Every published column must be nameable and explainable."""

import re
from pathlib import Path

import pandas as pd

from oac.labels import EXPLAIN, LABELS, UNRANKED, rename

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


def test_explain_block_is_gone():
    """The collapsible dropdown was the thing the review objected to.

    Its content is not lost: the full text is rendered once, on the Metrics
    page, generated from the same `EXPLAIN` dict.
    """
    import oac.labels as labels
    assert not hasattr(labels, "explain_block")
    assert "explain_block" not in labels.__all__


def test_the_metrics_page_renders_every_explanation():
    """The one place the long form now exists. If it stops rendering there,
    hovering a heading is the only definition left, and 42 words is not one.

    Executes the same loop `site/metrics.qmd`'s chunk uses to build the
    section -- rather than grepping the page's source for "EXPLAIN" and
    "for col", which would still pass with a broken loop body -- and checks
    the actual generated markdown for every column's heading and body text.
    """
    from oac.labels import EXPLAIN, LABELS

    out = []
    for col in sorted(EXPLAIN):
        out.append(f"#### {LABELS.get(col, col)} {{#{col.replace('_', '-')}}}\n")
        out.append(f"`{col}`\n")
        out.append(EXPLAIN[col] + "\n")
    rendered = "\n".join(out)

    for col in EXPLAIN:
        anchor = f"{{#{col.replace('_', '-')}}}"
        assert anchor in rendered, f"{col}: heading missing from the generated markdown"
        assert EXPLAIN[col] in rendered, (
            f"{col}: body text missing from the generated markdown"
        )


#: Files whose running prose a reader sees. Headings may pair the two
#: vocabularies; body text may not use the tier names alone.
PROSE_FILES = [
    "site/index.qmd",
    "site/about.qmd",
    "site/metrics.qmd",
    "src/oac/labels.py",
    "site/airports/index.qmd",
    "site/pipeline.qmd",
    "scripts/gen_pages.py",
    "src/oac/page.py",
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


def test_the_arrival_estimate_is_explained_as_a_reason_not_a_curiosity():
    """Why the reader is told how NM's arrival time is built.

    It is not arithmetic trivia: it is the whole reason no arrival coverage is
    computed for an estimated aerodrome. Stated without that consequence, a
    reader has no idea why they were told. The two must stay in one breath.
    """
    from oac.labels import TIERS_EXPLAINED
    para = [p for p in TIERS_EXPLAINED.split("\n\n")
            if "flight duration" in p]
    assert para, "the arrival arithmetic is not explained anywhere"
    joined = " ".join(para)
    assert "no arrival coverage" in joined or "cannot" in joined, (
        "the arithmetic is stated without the consequence that follows from it"
    )


def test_tracking_errors_state_their_direction_and_do_not_overclaim_merging():
    """The page claimed both failures depress coverage. Only one does.

    Within aerodromes on the 2026 sample, a split departure's track starts a
    median 392 s later than a clean one (later at 182 of 206 aerodromes), so
    split genuinely understates. Merged shows no consistent effect on the
    surviving flight -- a median within-aerodrome delta of -0.009 across the
    12 aerodromes with enough of both -- and its real damage is that the other
    flight is absent from the output entirely.
    """
    from oac.labels import EXPLAIN
    text = EXPLAIN["tracking_err_pct"]
    assert "392" in text, (
        "the split mechanism is not quantified"
    )
    assert "Both depress coverage" not in text, (
        "the unsupported claim about merging is back"
    )
    for word in ("understat", "absent", "downstream"):
        assert word in text, f"the explanation never mentions {word!r}"


from oac.labels import (EXPLAIN, RATINGS, TIPS, rating_cell, tip, tip_header,
                        tip_headers)

TIP_MAX_WORDS = 18


def test_every_explained_column_has_a_tip():
    """A column the reader can hover must have something to show.

    `EXPLAIN` is the full definition and lives on the Metrics page; `TIPS` is
    what fits in a `title` attribute. A column with one and not the other is
    either an unexplained heading or a definition nobody can reach.
    """
    missing = sorted(set(EXPLAIN) - set(TIPS))
    assert not missing, f"columns explained but not tipped: {missing}"
    extra = sorted(set(TIPS) - set(EXPLAIN))
    assert not extra, f"columns tipped but not explained: {extra}"


def test_tips_fit_in_a_tooltip():
    """A tooltip that needs scrolling is the dropdown again, in a smaller box."""
    long = {c: len(t.split()) for c, t in TIPS.items()
            if len(t.split()) > TIP_MAX_WORDS}
    assert not long, f"tips over {TIP_MAX_WORDS} words: {long}"


def test_tips_are_plain_text_safe_for_an_attribute():
    """`title="..."` ends at the first double quote, and renders no markdown.

    A stray `"` truncates the tooltip and leaks the rest into the tag; a `**`
    reaches the reader as two asterisks.
    """
    for col, t in TIPS.items():
        assert '"' not in t, f"{col}: double quote would close the attribute"
        assert "<" not in t and ">" not in t, f"{col}: HTML in tip"
        assert "**" not in t and "`" not in t, f"{col}: markdown in tip"


def test_tip_header_wraps_the_display_name_not_the_column_name():
    h = tip_header("coverage_index")
    assert 'data-bs-toggle="tooltip"' in h
    assert 'tabindex="0"' in h, "keyboard and touch users need focus to open it"
    assert ">Coverage index<" in h, "the reader must still see the display name"
    assert TIPS["coverage_index"] in h


def test_tip_header_falls_back_to_a_bare_name_when_there_is_no_tip():
    """`icao` and `rank` carry no measurement, so they get no tooltip."""
    assert tip_header("icao") == "ICAO"
    assert "<span" not in tip_header("rank")


def test_tip_headers_renames_every_column_and_leaves_the_data_alone():
    import pandas as pd
    df = pd.DataFrame({"icao": ["EBBR"], "coverage_index": [0.91]})
    out = tip_headers(df)
    assert list(out.columns)[0] == "ICAO"
    assert 'data-bs-toggle="tooltip"' in list(out.columns)[1]
    assert out.iloc[0, 1] == 0.91, "values must not be touched"
    assert list(df.columns) == ["icao", "coverage_index"], "input was mutated"


def test_every_rating_band_has_a_tooltip_carrying_its_description():
    for _, name, description in RATINGS:
        cell = rating_cell(name)
        assert 'data-bs-toggle="tooltip"' in cell
        assert description in cell
        assert f">{name}<" in cell


def test_rating_cell_passes_a_blank_through_untouched():
    """A measured aerodrome with no index shows an em dash, not a tooltip."""
    assert rating_cell("—") == "—"


def test_rating_descriptions_are_attribute_safe():
    for _, name, description in RATINGS:
        assert '"' not in description, f"{name}: quote would close the attribute"
