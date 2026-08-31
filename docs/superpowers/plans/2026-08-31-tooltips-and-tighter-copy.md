# Header Tooltips and Tighter Copy — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the site's collapsible explanation blocks with hover tooltips on column headings and rating values, move the full definitions to the Metrics page, and cut the site's prose roughly in half without dropping a single fact.

**Architecture:** Column explanations currently exist once, in `oac.labels.EXPLAIN`, and are rendered inline above every table as a collapsed Quarto callout (`explain_block`). That stays the single source of truth, but splits into two renderings: a new `TIPS` dict of one-line summaries that reach the reader as Bootstrap tooltips on the `<th>`, and the existing full `EXPLAIN` text, rendered in one place only — a generated column reference on `metrics.qmd`. `explain_block` is deleted. Tooltips are Bootstrap 5.3 tooltips, which Quarto's cosmo theme already ships (`site_libs/bootstrap/bootstrap.min.js`, verified to contain both `createPopper` and the `Tooltip` class), initialised by one delegated call from an `include-after-body` snippet. Nothing is fetched from a CDN, preserving the offline-render property that `init_notebook_mode(connected=False)` was chosen for.

**Tech Stack:** Quarto 1.10.18 (cosmo theme, Bootstrap 5.3.1), itables 2.9.1 over DataTables, pandas, Python 3.10.

**Spec:** No separate spec document. The authority is the review feedback and the answered design questions, both reproduced verbatim under *Source remarks* below. Where this plan and those remarks disagree, the remarks win.

---

## Global Constraints

- **Nothing external is fetched at render or at view time.** No CDN, no web font, no remote script. The page must work offline. This is why `init_notebook_mode(all_interactive=False, connected=False)` embeds DataTables, and it is why tooltips use the Bootstrap already vendored by Quarto rather than a tooltip library.
- **No fact may be deleted, only relocated or compressed.** Every number, caveat and definition currently on the site must still be reachable after this work. The reader's route to it changes; its existence does not.
- **Tooltip text is plain text in an HTML `title` attribute.** No markdown, no HTML tags, and never a `"` character — it would terminate the attribute. Tips are at most **18 words**.
- **Display and export must not converge.** `src/oac/tables.py` returns data; the page decorates it. Tooltip spans, links and em dashes are applied on the display path only. The CSV and XLSX downloads keep plain display names and bare values. `tests/test_tables.py` already guards this and must keep passing untouched.
- **`src/oac/tables.py` is not modified by this plan.** The tooltip layer sits above it.
- **Units stay as published.** No threshold, formula or published `version` string changes. This is an editorial and presentation change only; no committed CSV is regenerated.
- **Voice — banned constructions.** These are the tics that make the copy read as machine-written. Budgets are per file and enforced by `tests/test_style.py` (Task 5):
  | Construction | Pattern | Budget per file |
  |---|---|---|
  | Em-dash aside | ` — ` | ≤ 4 |
  | "rather than" | `\brather than\b` | ≤ 3 |
  | Bold lead-in | `**Phrase** —` | 0 |
  | "and that is the point / the finding" | — | 0 |
  | "it is worth …" / "worth knowing/seeing/noting" | — | 0 |
  | "the point is" / "the whole point" | — | 0 |
  | "silently" | — | 0 |
  | "deliberately" | — | ≤ 1 |
  | "genuinely" / "actually" | — | ≤ 2 |
  Current counts, measured on the branch before any work: 122 em-dash asides and 36 "rather than" across the six files. `index.qmd` alone has 34 and `metrics.qmd` 35.
- **Findings survive; commentary does not.** A striking result is still stated plainly as a result. What goes is the second pass at the same idea, the aside explaining why the first pass was interesting, and the sentence announcing that a fact is important.
- **Word budgets.** Measured before starting, and each task states its own target:
  | Source | Now | Target |
  |---|---|---|
  | `labels.py` `EXPLAIN` (51 entries) | 2,135 w | ≤ 1,500 w |
  | `labels.py` `TIERS_EXPLAINED` | 324 w | ≤ 150 w |
  | `labels.py` `TIPS` (new, 51 entries) | — | ≤ 780 w |
  | `site/index.qmd` prose | 812 w | ≤ 420 w |
  | `site/metrics.qmd` prose | 2,027 w | ≤ 1,200 w |
  | `site/about.qmd` prose | 838 w | ≤ 500 w |
  | `site/pipeline.qmd` prose | 344 w | ≤ 250 w |
  | A generated Tier A aerodrome page, prose only | 1,706 w | ≤ 450 w |

  The aerodrome-page figure is measured on a fully-populated page with table
  rows excluded, and is the worst offender on the site: roughly 1,000 of those
  words are the six `explain_block` callouts rendering `EXPLAIN` inline, which
  Task 3 removes outright. A Tier A page carries **8** collapsed callouts today.
  Target after this plan: **0** on Tier A, and exactly **1** on Tier B, the
  measured-or-estimated note.
- **Test command.** `OPDI_REPO=/home/jupyter/work/opdi-workspace/opdi python -m pytest tests/ -q`. The `OPDI_REPO` variable is required — without it `conftest.py`'s `bootstrap()` resolves the opdi checkout as a sibling directory and collection fails before any test runs.
- **Commit messages describe the change only.** No `Co-Authored-By`, no "generated with" trailer.

---

## Source remarks

Reviewer feedback, verbatim (originally part Dutch):

> Het is een serieuze boterham hoe define je de categories?
> mijn mening is dat het echt een overload aan uitleg is
> like kan je geen popup maken als je hovered over de column titles?

And the instruction derived from it:

> Could you do the following: Add pop ups next to columns names in the table with information (tooltip) instead of the massive dropdown. Avoid claudish text, write natural. You sound like claude, sound like a person. At last, minimize the text lengths everywhere.. It's just too much info. Don't leave out things, just shorten your lengthy explanations.

Followed by:

> Also add tooltips for the coverage levels (good, excellent, poor, ...)

**Answered design questions:**

1. *Where does the long detail go?* One line in the tooltip; the full definition lives on the Metrics page. Every collapsible "What these columns mean" dropdown is deleted.
2. *How hard to cut?* Substantial — roughly half. Every fact kept, elaboration dropped.
3. *Scope?* All pages, including the 352 generated aerodrome pages.
4. *Voice?* Ban the tics, keep the findings. A striking result is still stated as one.

---

## File Structure

| File | Change | Responsibility after this plan |
|---|---|---|
| `src/oac/labels.py` | Modify | `LABELS` (display names), `TIPS` (new, ≤ 18-word tooltip text), `EXPLAIN` (full text, trimmed), `RATINGS`, and the helpers that wrap a name or a rating value in a tooltip span. `explain_block` is **deleted**. |
| `site/tooltips.html` | Create | One `<script>` initialising Bootstrap's delegated tooltip. Included after body on every page. |
| `site/_quarto.yml` | Modify | Registers `tooltips.html` via `include-after-body`. |
| `site/index.qmd` | Modify | Rankings page: tooltip headers, tooltip rating cells, no dropdowns, prose halved. |
| `site/metrics.qmd` | Modify | Becomes the single home of the full column definitions, generated from `EXPLAIN`. Its own prose trimmed. |
| `site/about.qmd`, `site/pipeline.qmd` | Modify | Prose trimmed. |
| `src/oac/page.py` | Modify | Aerodrome pages: tooltip headers, no dropdowns, prose trimmed. |
| `tests/test_labels.py` | Modify | Tooltip helpers, TIPS coverage and length, `explain_block` removal. |
| `tests/test_style.py` | Create | The banned-construction budgets, applied to reader-facing prose. |
| `tests/test_site_copy.py` | Modify | Asserts the rankings page uses tooltip headers and has no dropdowns. |
| `tests/test_gen_pages.py` | Modify | Same assertions against a generated aerodrome page. |

**Not modified:** `src/oac/tables.py`, `scripts/gen_pages.py`, `tests/test_tables.py`. If a task appears to require editing any of these, stop and re-read the Global Constraints — the download path must not acquire tooltip markup.

---

## Task 1: Tooltip infrastructure

**Files:**
- Modify: `src/oac/labels.py`
- Create: `site/tooltips.html`
- Modify: `site/_quarto.yml`
- Test: `tests/test_labels.py`

**Interfaces:**
- Consumes: `LABELS`, `RATINGS`, `EXPLAIN` (all already in `labels.py`).
- Produces, for Tasks 2 and 4:
  - `TIPS: dict[str, str]` — column name → tooltip text.
  - `tip(col: str) -> str` — the tip, or `""`.
  - `tip_header(col: str) -> str` — the display name wrapped in a tooltip span, or the bare display name when there is no tip.
  - `tip_headers(df: pd.DataFrame) -> pd.DataFrame` — `df` with tooltip-span headers. The display-path replacement for `rename`.
  - `rating_cell(band: str) -> str` — a rating word wrapped in a tooltip span carrying that band's description.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_labels.py`:

```python
import re

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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `OPDI_REPO=/home/jupyter/work/opdi-workspace/opdi python -m pytest tests/test_labels.py -q`

Expected: FAIL — `ImportError: cannot import name 'TIPS' from 'oac.labels'`.

- [ ] **Step 3: Add `TIPS` to `src/oac/labels.py`**

Insert immediately after the `LABELS` dict and before `EXPLAIN`. Use exactly this text — it is written to the 18-word budget and the attribute-safety rules:

```python
#: One line per column, short enough for a `title` attribute. `EXPLAIN` below
#: carries the full definition, and the Metrics page is where it is rendered.
#: Plain text only: no markdown, no HTML, and no double quote, which would
#: close the attribute and leak the rest of the tip into the tag.
TIPS = {
    "n_gt": "Take-offs and landings the reference data records here. Below 20 an aerodrome is not ranked.",
    "n_gt_dep": "Take-offs recorded here, counted against each flight's origin aerodrome.",
    "n_gt_arr": "Landings recorded here, counted against each flight's destination aerodrome.",
    "n_detected": "How many of those movements produced at least one ADS-B position report.",
    "n_detected_dep": "Take-offs with at least one matching position report.",
    "n_detected_arr": "Landings with at least one matching position report.",
    "detection_pct": "Share of movements seen at least once in the air. A floor, not a coverage figure.",
    "detection_pct_dep": "Share of departures seen at least once in the air.",
    "detection_pct_arr": "Share of arrivals seen at least once in the air.",
    "n_capture_excluded": "Movements with impossible times, such as off-block after take-off. Dropped, not clamped.",
    "n_capture_excluded_dep": "Departures with impossible recorded times, excluded from the coverage figures.",
    "n_capture_excluded_arr": "Arrivals with impossible recorded times, excluded from the coverage figures.",
    "measured_pct": "Share of movements whose stand and runway times come from the airport operator.",
    "measured_pct_dep": "Share of departures with operator-recorded stand and runway times.",
    "measured_pct_arr": "Share of arrivals with operator-recorded stand and runway times.",
    "measured": "Whether the airport operator records this aerodrome's real stand and runway times.",
    "dep_signal_p50": "Share of the position reports a taxi-out should produce that arrived. Median across departures.",
    "dep_signal_est": "The same over a taxi window Network Manager predicted. Read the median, never one row.",
    "arr_signal_p50": "Share of expected reports that arrived during taxi-in. Median across arrivals.",
    "signal_p50": "Taxi-out and taxi-in averaged: one figure for a typical ground movement.",
    "dep_continuity_p50": "Share of 30-second slices of the taxi-out holding at least one report.",
    "arr_continuity_p50": "Share of 30-second slices of the taxi-in holding at least one report.",
    "dep_continuity_p10": "The worst-covered tenth of departures, by the 30-second slice measure.",
    "dep_continuity_p90": "The best-covered tenth of departures, by the 30-second slice measure.",
    "arr_continuity_p10": "The worst-covered tenth of arrivals, by the 30-second slice measure.",
    "arr_continuity_p90": "The best-covered tenth of arrivals, by the 30-second slice measure.",
    "dep_max_gap_median_s": "Longest silence during a typical taxi-out. One big gap means a blind spot.",
    "arr_max_gap_median_s": "Longest silence during a typical taxi-in.",
    "dep_reach_p50": "How far back the first report lies, as a share of the taxi. Diagnostic only.",
    "arr_reach_p50": "How far forward the last report lies, as a share of the taxi-in. Diagnostic only.",
    "off_s_p50": "Seconds between the track starting and wheels-off. Negative is good.",
    "off_s_p10": "The earliest tenth: how far ahead of take-off tracking begins at best.",
    "off_s_p90": "The latest tenth: how much of the departure is missed at worst.",
    "land_s_p50": "Seconds between landing and the track ending. Positive is good.",
    "land_s_p10": "The tenth where tracking stops earliest after landing.",
    "land_s_p90": "The tenth where tracking runs longest after landing.",
    "dep_no_ground_pct": "Share of departures never heard while still on the ground.",
    "arr_no_ground_pct": "Share of arrivals whose track ends at or before touchdown.",
    "dep_full_capture_pct": "Share of departures where at least 95% of expected reports arrived.",
    "arr_full_capture_pct": "Share of arrivals where at least 95% of expected reports arrived.",
    "taxi_out_median_s": "How long a typical taxi-out takes here. Context for the coverage figures.",
    "taxi_in_median_s": "How long a typical taxi-in takes here. Context for the coverage figures.",
    "clean_pct_dep": "Share of departures matched to exactly one track holding no other flight.",
    "clean_pct_arr": "Share of arrivals matched to exactly one track holding no other flight.",
    "fragmented_pct_dep": "Share of departures cut across several tracks, which understates their coverage.",
    "fragmented_pct_arr": "Share of arrivals cut across several tracks, which understates their coverage.",
    "merged_pct_dep": "Share of departures sharing a track with another flight, which is then lost.",
    "merged_pct_arr": "Share of arrivals sharing a track with another flight, which is then lost.",
    "tracking_err_pct": "Split and merged added together. High means coverage understated, not poor reception.",
    "coverage_index": "Share of movements seen, times how much of a typical ground movement arrives.",
    "rating": "Plain-language band over the coverage index. Hover a value for what that band means.",
}
```

- [ ] **Step 4: Add the helpers to `src/oac/labels.py`**

Append after the existing `rename` function:

```python
def tip(col: str) -> str:
    """The tooltip text for a column, or an empty string."""
    return TIPS.get(col, "")


def _tip_span(text: str, tip_text: str) -> str:
    """`text` wrapped so Bootstrap will show `tip_text` on hover or focus.

    `tabindex` is what makes it reachable without a mouse. Bootstrap opens a
    tooltip on focus as well as hover, so a keyboard user tabs to the heading
    and a touch user taps it; without the attribute a `<span>` takes neither.
    """
    return (f'<span data-bs-toggle="tooltip" tabindex="0" '
            f'title="{tip_text}">{text}</span>')


def tip_header(col: str) -> str:
    """The display name, carrying its tooltip.

    Columns with nothing to explain get a bare name. Wrapping them anyway
    would put a focus stop and an empty tooltip on `ICAO` and `#`.
    """
    name = label(col)
    t = tip(col)
    return _tip_span(name, t) if t else name


def tip_headers(df):
    """`df` with tooltip-carrying display names as headers.

    The display-path counterpart of `rename`. `rename` stays, and is what the
    CSV and XLSX downloads use: a `<span>` in a spreadsheet header is markup a
    reader has to look past, and the file has no Bootstrap to render it.
    """
    return df.rename(columns={c: tip_header(c) for c in df.columns})


#: Band name -> the sentence describing it, from `RATINGS`.
_RATING_TEXT = {name: description for _, name, description in RATINGS}


def rating_cell(band: str) -> str:
    """A rating word carrying its band's description on hover.

    Applied on the display path only. The downloads keep the bare word, so a
    spreadsheet column of ratings stays sortable and filterable.
    """
    text = _RATING_TEXT.get(band)
    return _tip_span(band, text) if text else band
```

Then extend `__all__` to include the new names:

```python
__all__ = ["LABELS", "TIPS", "EXPLAIN", "UNRANKED", "RATINGS", "label",
           "explain", "tip", "tip_header", "tip_headers", "rating_cell",
           "rename", "explain_block", "rating", "TIERS_EXPLAINED"]
```

`explain_block` stays in `__all__` for now; Task 3 removes it along with the function.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `OPDI_REPO=/home/jupyter/work/opdi-workspace/opdi python -m pytest tests/test_labels.py -q`

Expected: PASS.

- [ ] **Step 6: Create `site/tooltips.html`**

```html
<script>
// Bootstrap tooltips are opt-in: the CSS and JS ship with Quarto's cosmo
// theme, but nothing initialises them. One delegated instance on <body>
// covers every tooltip on the page, including the ones itables injects into
// table headers after this script has already run -- a per-element loop here
// would find no table and silently do nothing.
//
// `container: "body"` matters. DataTables is configured with scrollX, which
// wraps the table in an overflow container; a tooltip positioned inside that
// wrapper is clipped at its edge, which is exactly where the last column's
// heading sits.
document.addEventListener("DOMContentLoaded", function () {
  if (typeof bootstrap === "undefined") return;
  new bootstrap.Tooltip(document.body, {
    selector: '[data-bs-toggle="tooltip"]',
    container: "body",
    placement: "top",
    trigger: "hover focus"
  });
});
</script>
```

- [ ] **Step 7: Register it in `site/_quarto.yml`**

Under `format: html:`, after `fig-format: svg`, add:

```yaml
    # Bootstrap ships with the cosmo theme but initialises no tooltips. This
    # is the one line of JavaScript that turns the column headings on.
    include-after-body: tooltips.html
```

- [ ] **Step 8: Verify Quarto picks up the include**

Run: `quarto inspect site`

Expected: the output's `format.html.include-after-body` (or `metadata`) mentions `tooltips.html`. If it does not, the key is at the wrong indentation level — it belongs under `format: html:`, not under `website:`.

- [ ] **Step 9: Run the whole suite**

Run: `OPDI_REPO=/home/jupyter/work/opdi-workspace/opdi python -m pytest tests/ -q`

Expected: all existing tests still pass; the new ones pass. Nothing else has changed yet.

- [ ] **Step 10: Commit**

```bash
git add src/oac/labels.py site/tooltips.html site/_quarto.yml tests/test_labels.py
git commit -m "Add one-line column tips and the Bootstrap tooltip they render in"
```

---

## Task 2: Tooltips on the rankings page, dropdowns off

**Files:**
- Modify: `site/index.qmd`
- Test: `tests/test_site_copy.py`

**Interfaces:**
- Consumes from Task 1: `tip_headers`, `rating_cell`.
- Produces: nothing for later tasks. The aerodrome pages (Task 4) apply the same helpers independently.

**Note:** this task changes *which helpers the page calls*. The prose on the page is trimmed in Task 5, not here. Keeping the two apart means a reviewer can see the markup change without it being buried in a rewrite of every paragraph.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_site_copy.py`:

```python
def test_the_rankings_page_has_no_collapsible_explanation_blocks():
    """The dropdowns are what the review called an overload of explanation.

    They are replaced by a tooltip per heading, with the full text on the
    Metrics page. A reintroduced `explain_block` call would put the wall of
    text back above the table.
    """
    assert "explain_block" not in INDEX.read_text()


def test_both_ranking_tables_carry_tooltip_headers():
    src = chunk_source()
    assert src.count("tip_headers(") >= 2, (
        "each ranking table's headers must carry their tooltip"
    )
    assert "table(rename(" not in src, (
        "rename() is the export path; the page must use tip_headers()"
    )


def test_the_rating_column_is_tooltipped_on_the_page_only():
    """Hovering Excellent should say what Excellent means.

    Applied in the page chunk, not in `oac.tables`, so the download keeps the
    bare word.
    """
    assert "rating_cell" in chunk_source()


def test_the_page_points_at_the_full_definitions():
    """Nothing is deleted, so the reader needs the route to the long form."""
    assert "metrics.qmd" in INDEX.read_text()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `OPDI_REPO=/home/jupyter/work/opdi-workspace/opdi python -m pytest tests/test_site_copy.py -q`

Expected: FAIL — `explain_block` is still present and `tip_headers` is not.

- [ ] **Step 3: Update the imports in `site/index.qmd`**

Replace:

```python
from oac.labels import TIERS_EXPLAINED, explain_block, rating, rename
```

with:

```python
from oac.labels import TIERS_EXPLAINED, rating, rating_cell, tip_headers
```

`rating` is still used by the overview map, which colours by band. `rename` is no longer used on this page — the downloads call it inside `oac.tables`.

- [ ] **Step 4: Drop the fleet-summary dropdown**

Delete these four lines from the fleet-summary chunk:

```python
    display(Markdown(explain_block(
        ["dep_signal_p50", "arr_signal_p50", "coverage_index", "detection_pct"],
        title="What these measures are",
    )))
```

The rows in that table are prose labels ("Taxi-out received — measured aerodromes"), not column names, so there is no heading to hang a tooltip on. The prose above it carries the meaning, and Task 5 rewrites it to do so in fewer words.

- [ ] **Step 5: Switch the measured table to tooltip headers**

In the measured-table chunk, replace:

```python
    t = measured_table(a)
    display(Markdown(explain_block(MEASURED_COLS)))
    display(downloads("measured", LATEST))
    t = t.copy()
    t["icao"] = [f'<a href="airports/{i}.html">{i}</a>' for i in t["icao"]]
    table(rename(t))
```

with:

```python
    t = measured_table(a)
    display(downloads("measured", LATEST))
    t = t.copy()
    t["icao"] = [f'<a href="airports/{i}.html">{i}</a>' for i in t["icao"]]
    # Hover text on the band, from the same table that assigns it. Display
    # path only: the download keeps "Excellent" as a plain sortable word.
    t["rating"] = [rating_cell(v) for v in t["rating"]]
    table(tip_headers(t))
```

`MEASURED_COLS` is now imported but unused on this page. Leave the import in place — `tests/test_tables.py::test_column_order_constants_match_what_the_builders_emit` does not read the page, but the constant still documents the table's order, and removing it from the import line risks the multi-line-import parsing that `tests/test_imports.py` guards. If the linter objects to the unused name, remove `MEASURED_COLS` and `ALL_COLS` from the import and confirm `pytest tests/test_imports.py` still passes.

- [ ] **Step 6: Switch the all-aerodromes table to tooltip headers**

In that chunk, delete the line:

```python
    display(Markdown(explain_block(ALL_COLS)))
```

and replace the final `table(rename(t))` with `table(tip_headers(t))`. Leave the em-dash substitution for `dep_signal_est` exactly as it is — it is display-only and correct.

- [ ] **Step 7: Add the route to the full definitions**

The current closing line of the intro chunk is:

```
Every column is defined in [Metrics](metrics.qmd); click any aerodrome for its
map, its distributions and its history.
```

Replace with:

```
Hover any column heading for what it measures. [Metrics](metrics.qmd) has the
full definitions; click an aerodrome for its map and history.
```

- [ ] **Step 8: Run the tests**

Run: `OPDI_REPO=/home/jupyter/work/opdi-workspace/opdi python -m pytest tests/ -q`

Expected: PASS, including `tests/test_tables.py` untouched — the downloads must still carry plain display names.

- [ ] **Step 9: Render the page and check the markup reached the browser**

Run: `PYTHONPATH="$(pwd)/src:$(pwd)" quarto render site/index.qmd`

Then confirm, in `site/_site/index.html` (or wherever the render lands):

```bash
grep -c 'data-bs-toggle="tooltip"' site/index.html
grep -c 'tooltips.html\|bootstrap.Tooltip' site/index.html
```

Expected: the first is at least 15 (the union of both tables' explained columns plus the rating cells), the second at least 1. If the tooltip count is zero, `allow_html=True` has been lost from the `table()` helper — itables escapes header HTML without it, and the reader would see raw `<span …>` as text.

- [ ] **Step 10: Commit**

```bash
git add site/index.qmd tests/test_site_copy.py
git commit -m "Put column definitions in header tooltips on the rankings page"
```

---

## Task 3: Metrics becomes the single home of the full definitions

**Files:**
- Modify: `site/metrics.qmd`
- Modify: `src/oac/labels.py` (delete `explain_block`)
- Test: `tests/test_labels.py`

**Interfaces:**
- Consumes from Task 1: `TIPS`, `EXPLAIN`, `LABELS`.
- Produces: nothing. This is the task that makes "nothing is deleted" true, so it must land before Task 4 removes the last dropdowns.

- [ ] **Step 1: Write the failing tests**

Replace the two `explain_block` tests in `tests/test_labels.py` with:

```python
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
    """
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent
           / "site" / "metrics.qmd").read_text()
    assert "EXPLAIN" in src, "the column reference is no longer generated"
    assert "for col" in src or "for c" in src, "generated, not pasted"
```

- [ ] **Step 2: Run to verify they fail**

Run: `OPDI_REPO=/home/jupyter/work/opdi-workspace/opdi python -m pytest tests/test_labels.py -q`

Expected: FAIL — `explain_block` still exists.

- [ ] **Step 3: Add the generated column reference to `site/metrics.qmd`**

Append at the end of the file:

````markdown
## Column reference

Every column on the site, in full. The tables above give the formula; this
gives the reading. The same text is what a column heading shows on hover, in
one line instead of several.

```{python}
#| echo: false
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

from IPython.display import Markdown, display

from oac.labels import EXPLAIN, LABELS, TIPS

# Generated from `oac.labels`, never pasted. A definition edited in one place
# and copied in another is how a heading's tooltip comes to disagree with the
# page it links to.
out = []
for col in sorted(EXPLAIN):
    out.append(f"#### {LABELS.get(col, col)} {{#{col.replace('_', '-')}}}\n")
    out.append(f"`{col}`\n")
    out.append(EXPLAIN[col] + "\n")
display(Markdown("\n".join(out)))
```
````

The anchor on each heading (`{#coverage-index}`) makes each definition individually linkable, so a future change can point a reader at one column rather than the whole page.

- [ ] **Step 4: Delete `explain_block` from `src/oac/labels.py`**

Remove the whole function and drop `"explain_block"` from `__all__`. Also update the module docstring: the sentence beginning "Tables render the display name; each table is preceded by a collapsible block…" no longer describes the module. Replace that paragraph with:

```
So every column has three things here: a **display name** carrying its unit and
its direction, a **one-line tip** short enough for a tooltip, and a fuller
**explanation** in ordinary language. Tables show the display name and carry
the tip on hover. `site/metrics.qmd` renders the explanations in full, once.
```

- [ ] **Step 5: Run the tests**

Run: `OPDI_REPO=/home/jupyter/work/opdi-workspace/opdi python -m pytest tests/ -q`

Expected: FAIL in `src/oac/page.py`, which still imports and calls `explain_block`. That is Task 4's work. If the failure is anywhere else, fix it here.

To keep this task independently green, apply the minimal change to `src/oac/page.py` now: drop `explain_block` from its import and delete the four call sites (lines ~125, ~141, ~187, ~399), leaving the tables in place. Task 4 adds the tooltips.

- [ ] **Step 6: Run the tests again**

Run: `OPDI_REPO=/home/jupyter/work/opdi-workspace/opdi python -m pytest tests/ -q`

Expected: PASS.

- [ ] **Step 7: Render metrics.qmd and confirm the reference is there**

Run: `PYTHONPATH="$(pwd)/src:$(pwd)" quarto render site/metrics.qmd`

Confirm the rendered HTML contains a "Column reference" heading and at least 51 `<h4>` entries.

- [ ] **Step 8: Commit**

```bash
git add site/metrics.qmd src/oac/labels.py src/oac/page.py tests/test_labels.py
git commit -m "Render the full column definitions once, on the Metrics page"
```

---

## Task 4: Tooltips on the aerodrome pages

**Files:**
- Modify: `src/oac/page.py`
- Test: `tests/test_gen_pages.py`

**Interfaces:**
- Consumes from Task 1: `tip_header`.
- Note: aerodrome pages use pandoc pipe tables built by `page.py`'s `_table()`, not itables. Raw HTML in a pipe-table header cell renders as HTML in Quarto's HTML output, so the same span works. It must not contain a `|` character — none of the tips do, and `tests/test_labels.py` can be extended to assert it if a future tip is at risk.

- [ ] **Step 1: Add the page fixture to `tests/conftest.py`**

Both this task and Task 6 need a *fully populated* aerodrome page. An empty
one is not a useful subject: `build_page("A", {}, {}, None, "2026", {})` runs
without error but every section returns its "no data" early exit, producing 409
words where a real page has 1,706. A budget measured against it would pass on a
page nobody could read.

Append to `tests/conftest.py`:

```python
import numpy as np
import pandas as pd
import pytest

#: One aerodrome's stats row, complete enough that every section of
#: `build_page` renders its prose rather than its "no data" branch.
_PAGE_STATS = pd.Series({
    "n_gt_dep": 500, "n_gt_arr": 480, "n_detected_dep": 498,
    "n_detected_arr": 470, "detection_pct_dep": 99.6, "detection_pct_arr": 97.9,
    "coverage_index": 0.71, "dep_signal_p50": 0.74, "arr_signal_p50": 0.68,
    "off_s_p50": -320.0, "land_s_p50": 210.0,
    "clean_pct_dep": 91.0, "fragmented_pct_dep": 8.0, "merged_pct_dep": 1.0,
    "clean_pct_arr": 90.0, "fragmented_pct_arr": 9.0, "merged_pct_arr": 1.0,
    "n_capture_excluded_dep": 3, "taxi_out_median_s": 700.0,
    "taxi_in_median_s": 300.0,
})


@pytest.fixture
def aerodrome_page():
    """Build a complete aerodrome page for a tier. Returns the markdown."""
    from oac.page import build_page

    rng = np.random.default_rng(0)

    def frame(off_col, sig_col):
        return pd.DataFrame({off_col: rng.normal(-300, 200, 50),
                             sig_col: rng.uniform(0, 1, 50)})

    def build(tier="A"):
        frames = {"dep": {p: frame("off_s", "dep_signal")
                          for p in ("2026", "2025")},
                  "arr": {p: frame("land_s", "arr_signal")
                          for p in ("2026", "2025")}}
        figs = {"dep_hist": "d.svg", "arr_hist": "a.svg",
                "dep_ecdf": "de.svg", "arr_ecdf": "ae.svg",
                "dep_hist_overflow": {"2026": (2, 1)},
                "map_html": "<div>map</div>"}
        ranking = pd.DataFrame([dict(_PAGE_STATS)] * 3)
        stats = {"2026": _PAGE_STATS, "2025": _PAGE_STATS}
        return build_page(tier, stats, frames, ranking, "2026", figs)

    return build
```

- [ ] **Step 2: Write the failing tests**

Add to `tests/test_gen_pages.py`:

```python
def test_the_aerodrome_pages_have_no_collapsible_explanation_blocks(
        aerodrome_page):
    """A Tier A page carried eight of these, which is the overload complained of.

    Six were `explain_block` rendering `EXPLAIN` inline; two were hand-written.
    The definitions are not lost -- they are the header tooltips, and the full
    text is on the Metrics page.
    """
    assert aerodrome_page("A").count("callout-note collapse") == 0


def test_an_estimated_page_keeps_exactly_one_note(aerodrome_page):
    """The measured-or-estimated note stays collapsed, and is the only one.

    It explains why the page has no coverage index at all, which a reader
    cannot get from any column heading, so it is not a column definition and
    does not move to Metrics.
    """
    md = aerodrome_page("B")
    assert md.count("callout-note collapse") == 1
    assert "Measured or estimated?" in md


def test_page_py_no_longer_calls_explain_block():
    """Belt and braces: a section whose data is missing renders no prose, so
    the generated-page assertion alone could pass on a page that skipped it.
    """
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent
           / "src" / "oac" / "page.py").read_text()
    assert "explain_block" not in src


def test_the_generated_tables_carry_tooltip_headers(aerodrome_page):
    md = aerodrome_page("A")
    assert md.count('data-bs-toggle="tooltip"') >= 6


def test_tooltip_headers_never_contain_a_pipe():
    """A `|` inside a markdown table cell ends the cell early."""
    from oac.labels import TIPS, tip_header
    for col in TIPS:
        assert "|" not in tip_header(col)
```

- [ ] **Step 3: Run to verify they fail**

Run: `OPDI_REPO=/home/jupyter/work/opdi-workspace/opdi python -m pytest tests/test_gen_pages.py -q`

Expected: FAIL. A Tier A page has 8 collapsed callouts against an expected 0, and a Tier B page 7 against an expected 1. Six of them are `explain_block`, already removed in Task 3 — if they are still present, Task 3 did not land.

- [ ] **Step 4: Import the helper**

In `src/oac/page.py`, change:

```python
from oac.labels import TIERS_EXPLAINED, label, rating
```

to:

```python
from oac.labels import TIERS_EXPLAINED, label, rating, tip_header
```

- [ ] **Step 5: Give the quality table tooltip headers and drop its callout**

In `_quality_section`, replace the `cols` list and the returned string. The three headings become tooltip headers built from the columns they display:

```python
    cols = ["period",
            tip_header("clean_pct_dep"),
            tip_header("fragmented_pct_dep"),
            tip_header("merged_pct_dep")]
    rows = []
    for p, r in stats.items():
        for side, sfx in (("departures", "dep"), ("arrivals", "arr")):
            rows.append({
                "period": f"{p} {side}",
                cols[1]: _p(r.get(f"clean_pct_{sfx}")),
                cols[2]: _p(r.get(f"fragmented_pct_{sfx}")),
                cols[3]: _p(r.get(f"merged_pct_{sfx}")),
            })
    return ("## Was each flight tracked as one flight?\n\n"
            "A poor coverage number can mean the receivers heard nothing, or "
            "that the algorithm cut the flight's track up. This separates "
            "them.\n\n"
            + _table(rows, cols))
```

Note the rows now key on the tooltip header string, because `_table` looks up each column name in each row dict. Using `cols[1]` rather than repeating the span keeps the two in step.

- [ ] **Step 6: Drop the callout from `_counts_section`**

Same treatment. Replace the returned string's opening `"::: {.callout-note collapse=\"true\"}\n## The underlying counts\n\n"` with `"## The underlying counts\n\n"`, delete the trailing `+ ":::\n"`, and cut the explanatory paragraph to:

```python
        "Everything above is derived from these. Typical taxi times are "
        "context: the same 200 seconds of reception is most of a short taxi "
        "and a fraction of a long one.\n\n"
```

The definitions of "reference data", "seen" and "unusable reference rows" are not lost — they are the tooltips on `n_gt_dep`, `n_detected_dep` and `n_capture_excluded`, and the full text is on Metrics. Apply `tip_header` to those three column headings the same way as in Step 5.

- [ ] **Step 7: Tooltip the remaining generated tables**

Three more `_table` calls take literal column names:
- `_side_section`'s percentile tables use `["period", "n"] + [f"p{q}" for q in PCTS]` — percentile columns, not named measures. Leave them; the prose line above each already says what is being measured.
- `_context_section` builds a `measure` column whose *values* are `label(col)`. Change that to `tip_header(col)` so each row's measure name carries its own tooltip:

```python
            "measure": tip_header(col),
```
- `build_page`'s headline table uses literal keys `"departures"`, `"arrivals"`, `"detection (dep)"`, `"detection (arr)"`, `"coverage index"`. Replace the last three headings with `tip_header("detection_pct_dep")`, `tip_header("detection_pct_arr")` and `tip_header("coverage_index")`, keeping the row dict keys in step exactly as in Step 5.

- [ ] **Step 8: Run the tests**

Run: `OPDI_REPO=/home/jupyter/work/opdi-workspace/opdi python -m pytest tests/ -q`

Expected: PASS.

- [ ] **Step 9: Generate the pages and check one by eye**

Run: `PYTHONPATH="$(pwd)/src:$(pwd)" python scripts/gen_pages.py`

Then: `grep -c 'data-bs-toggle' site/airports/EBBR.qmd`

Expected: at least 6. Then confirm `git status` shows no unexpected change to tracked files beyond the aerodrome pages this task is meant to alter — `scripts/gen_pages.py` rewrites `site/airports/index.qmd`, which is tracked, and it must come back byte-identical.

- [ ] **Step 10: Commit**

```bash
git add src/oac/page.py tests/conftest.py tests/test_gen_pages.py site/airports/
git commit -m "Carry column tooltips onto the aerodrome pages"
```

---

## Task 5: Halve the rankings page prose, and add the style guard

**Files:**
- Modify: `site/index.qmd`
- Create: `tests/test_style.py`

**Interfaces:**
- Produces for Tasks 6–8: `tests/test_style.py` with a `FILES` list that later tasks extend. The budgets are in the Global Constraints table and must not be relaxed to make a file pass — the file is what changes.

**Target:** `site/index.qmd` prose from 812 words to ≤ 420, and from 34 em-dash asides to ≤ 4.

- [ ] **Step 1: Write the failing test**

Create `tests/test_style.py`:

```python
"""Budgets on the constructions that make the copy read as machine-written.

Not a style opinion for its own sake. A reviewer asked for prose that sounds
like a person, and "sounds like a person" is unreviewable as a diff comment.
These are the specific tics, counted, with a per-file ceiling -- so the ask
becomes something a test can hold.

Only reader-facing prose is counted: markdown outside code chunks, plus the
strings the chunks display. Code, comments and docstrings are exempt; they are
not what the reviewer read.
"""

import re
from pathlib import Path

import pytest

SITE = Path(__file__).resolve().parent.parent / "site"

#: Extended by later tasks as each file is trimmed.
FILES = ["index.qmd"]

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

WORD_BUDGET = {"index.qmd": 420}


def prose(name: str) -> str:
    """Markdown outside code chunks, plus the strings those chunks display.

    A page's framing text lives in both places -- `index.qmd` builds most of
    its paragraphs inside `display(Markdown(...))` so it can interpolate a
    count -- and a budget that saw only one of them would be trivially evaded.
    """
    text = (SITE / name).read_text()
    chunks = re.findall(r"```\{python\}(.*?)```", text, re.S)
    outside = re.sub(r"```.*?```", "", text, flags=re.S)
    displayed = []
    for c in chunks:
        displayed += re.findall(r'(?:f?"""(.*?)"""|f?"((?:[^"\\]|\\.)*)")',
                                c, re.S)
    flat = "".join(a or b for a, b in displayed)
    return outside + "\n" + flat


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
```

- [ ] **Step 2: Run to verify it fails**

Run: `OPDI_REPO=/home/jupyter/work/opdi-workspace/opdi python -m pytest tests/test_style.py -q`

Expected: FAIL — roughly 34 em-dash asides against a budget of 4, and ~812 words against 420.

- [ ] **Step 3: Rewrite the intro chunk**

Replace the whole `display(Markdown(f"""…"""))` intro with:

```python
    display(Markdown(f"""
When an aircraft moves at a European airport, how much of that movement do
OpenSky's receivers actually see?

Usually the flight is spotted somewhere: detection is above 99% almost
everywhere. But being spotted once in the air is not the same as being followed
across the apron and down the runway, and that is what these rankings measure.

Both tables cover **{LATEST}** only. Each aerodrome's own page adds 2025 and
2024 side by side, sampled on the same three days, with the change between
them. Some aerodromes gained ground coverage between samples and others lost
it.

Hover any column heading for what it measures. [Metrics](metrics.qmd) has the
full definitions; click an aerodrome for its map and history.
"""))
```

- [ ] **Step 4: Rewrite the fleet-summary prose**

Replace with:

```python
    display(Markdown(
        "How the aerodromes sit as a group. Each row is one measure; the "
        "columns are its spread across aerodromes: the middle value, the "
        "middle half, and the worst and best tenths.\n\n"
        "Half the measured aerodromes receive less than a fifth of a typical "
        "taxi-out. The two “seen” rows are near 100% for most aerodromes, "
        "reaching down to 87% only in the worst tenth, which is why they are "
        "not the headline."
    ))
```

- [ ] **Step 5: Rewrite the measured-table preamble**

Replace with:

```python
    display(Markdown(
        f"{len(a)} aerodromes where the airport's own records supply all four "
        f"milestones: off the stand, wheels off, wheels on, on the stand. "
        f"That is what makes ground coverage computable here.\n\n"
        f"Ranked best first on the **coverage index**: the share of movements "
        f"seen at all, multiplied by how much of a typical ground movement "
        f"arrives. Hover a heading for the detail."
    ))
```

- [ ] **Step 6: Rewrite the all-aerodromes preamble**

Replace with:

```python
    display(Markdown(
        f"All {len(b)} aerodromes with at least 20 movements, including the "
        f"{len(a)} above. Whether a flight was seen at all is the one question "
        f"answerable everywhere, so this is the complete ranking of it.\n\n"
        f"For the {len(b) - len(a)} aerodromes with no measured times, the last "
        f"column estimates taxi-out coverage against the taxi duration Network "
        f"Manager predicted. That window is unbiased but loose, so read the "
        f"column as a median across an aerodrome, not as a fact about one "
        f"flight. It is blank (“—”) for the {len(a)} measured aerodromes, whose "
        f"real figure is in the table above.\n\n"
        f"Four in five of these aerodromes score exactly 0.000. Outside the "
        f"airports that keep their own records, the network usually hears "
        f"nothing from an aircraft on the ground."
    ))
```

- [ ] **Step 7: Rewrite the map preamble**

Replace with:

```python
    display(Markdown(
        "The outlined box is the area whose position reports were ingested. "
        "Every ranked aerodrome is inside it, coloured by its coverage band; "
        "grey means only detection could be measured. An aerodrome outside the "
        "box does not appear at all: its movements were never sampled, so any "
        "number for it would describe the boundary, not the receiver network."
    ))
```

- [ ] **Step 8: Rewrite the two closing markdown sections**

Replace the whole of `## What "coverage" means here` with:

```markdown
## What "coverage" means here

Two questions, and the difference between them is what the site is about.

**How much of its time on the ground was received?** The taxi is bounded by
real stand and runway times, the feed should deliver a report every 5 seconds,
and we count how many of those expected reports arrived. Answerable only where
those times are recorded, and the answer varies enormously.

**Was the flight seen at all?** One position report anywhere between take-off
and landing. Answerable everywhere, and almost everywhere in Europe the answer
is yes above 99% of the time, so on its own it separates almost nothing.

The coverage index multiplies the two. An aerodrome can score 99% on the second
and near zero on the first, and several do: tracked in the air, invisible on
the ground.

Between them sits a third question. Network Manager predicts a taxi duration
for every European departure, and the prediction is unbiased even though it is
loose, so for an aerodrome with no measured times the *median* share of its
taxi-out that arrived can still be estimated. That is the last column of the
second table. Nothing equivalent exists for arrivals: no in-block time is
recorded outside APDF, so there is no window to measure a taxi-in against.
```

Replace the whole of `## What the ranking does not say` with:

```markdown
## What the ranking does not say

- An aerodrome outside the ingested area is **absent**, not ranked last. See
  the map above. Flights *to* those aerodromes still count at their European
  end.
- **A low coverage index has two possible causes, needing different fixes.**
  Position reports arrive as one continuous stream per aircraft, with nothing
  marking where one flight ends and the next begins, so flights have to be cut
  out of that stream first. When the cut goes wrong, coverage looks worse than
  the receivers deserve:
  - *split*: one flight cut into several tracks. Coverage is measured against
    the largest piece, and within an aerodrome a split departure's track starts
    a median 392 seconds later than a clean one.
  - *merged*: two flights left in one track. Only one comes out, so the other
    is absent from the output entirely. The survivor's own coverage shows no
    consistent shift, and merged movements are 0.8% of the sample.

  The **tracking errors** column adds the two together. A high figure means
  coverage is probably understated and some movements are missing, neither of
  which is a reception problem. Each aerodrome's page separates them.
- The two tiers are not comparable and are never merged into one table.
```

- [ ] **Step 9: Run the style guard and the suite**

Run: `OPDI_REPO=/home/jupyter/work/opdi-workspace/opdi python -m pytest tests/ -q`

Expected: PASS. If the word budget is still exceeded, cut further rather than raising the budget — the remaining slack is in the third paragraph of the intro and the closing bullets.

- [ ] **Step 10: Commit**

```bash
git add site/index.qmd tests/test_style.py
git commit -m "Halve the rankings page prose and guard the constructions that bloated it"
```

---

## Task 6: Trim the aerodrome page prose

**Files:**
- Modify: `src/oac/page.py`
- Test: `tests/test_style.py`

**Target:** a generated Tier A page's prose from 1,706 words to ≤ 450, and from 38 em-dash asides to ≤ 8. Task 3 already removed most of the words by deleting the six `explain_block` callouts; what remains is `page.py`'s own writing, measured at roughly 700 words.

**Why 8 em dashes and not 4.** One aerodrome page carries what the hand-written site splits across several files: a storyline, two side sections, a map note, a fleet comparison, and two table preambles. The per-file budget is applied per document, and this document is larger.

- [ ] **Step 1: Extend the style guard to generated pages**

Add to `tests/test_style.py`:

```python
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
```

The `aerodrome_page` fixture is the one added to `tests/conftest.py` in Task 4.

- [ ] **Step 2: Run to verify it fails**

Run: `OPDI_REPO=/home/jupyter/work/opdi-workspace/opdi python -m pytest tests/test_style.py -q`

Expected: FAIL on both. Roughly 20 em-dash asides against 8, and roughly 700 words against 450. (Before Task 3 it was 38 and 1,706; the `explain_block` removal accounts for the difference. If the numbers are still near the higher figures, Task 3 did not land.)

- [ ] **Step 3: Trim `_storyline`**

The Tier B branch currently returns a four-sentence paragraph plus a three-branch `est` string. Replace the returned string with:

```python
        return (
            f"Coverage here is judged on **estimated** reference times. What "
            f"can be said firmly is whether flights were seen at all: {seen}. "
            f"{est} There is no arrival figure, so this page carries no "
            f"coverage index.\n"
        )
```

and shorten the third `est` branch to:

```python
            est = (f"Across its departures, a median of **{_f(sig)}** of the "
                   f"taxi-out reached the network, estimated against a "
                   f"predicted taxi duration. Read it as a tendency for this "
                   f"aerodrome, not a fact about one flight.")
```

- [ ] **Step 4: Trim `_context_section`'s explanatory paragraph**

Replace with:

```python
    out.append(
        f"How this aerodrome compares with {tier_name}. **Typical aerodrome** "
        f"is the median across all of them. **Rank** is this aerodrome's "
        f"position among them, 0 (lowest) to 100 (highest).\n"
    )
```

and the closing italic line with:

```python
    out.append("*Higher rank is better everywhere except track start vs "
               "take-off, where a low value is the good case.*\n")
```

- [ ] **Step 5: Trim `_map_section`**

Replace the two prose lines with:

```python
        "Each position report is placed on a hexagonal grid over the "
        "aerodrome, on a log colour scale: one apron cell can hold thousands "
        "of reports while a runway threshold holds tens. Empty ground is "
        "surface the receivers do not reach.\n",
        "Use the legend to add the **airborne** layer and any **example "
        "flights**. Scroll to zoom.\n",
```

- [ ] **Step 6: Trim `_side_section`'s histogram caption**

The overflow sentence currently runs to three clauses. Replace with:

```python
            cap += (f" {total} movement(s) fall outside +/-{CLIP_S} s and are "
                    f"excluded from the plot ({parts}). They are included in "
                    f"every percentile below.")
```

- [ ] **Step 7: Run the tests**

Run: `OPDI_REPO=/home/jupyter/work/opdi-workspace/opdi python -m pytest tests/ -q`

Expected: PASS.

- [ ] **Step 8: Regenerate and confirm the tree is clean**

Run: `PYTHONPATH="$(pwd)/src:$(pwd)" python scripts/gen_pages.py` then `git status --short`

Expected: only the generated aerodrome pages change. `site/airports/index.qmd` is tracked and must come back byte-identical.

- [ ] **Step 9: Commit**

```bash
git add src/oac/page.py tests/test_style.py site/airports/
git commit -m "Trim the aerodrome page prose to what the tables do not already say"
```

---

## Task 7: Trim Metrics, About and Pipeline

**Files:**
- Modify: `site/metrics.qmd`, `site/about.qmd`, `site/pipeline.qmd`
- Test: `tests/test_style.py`

**Targets:** metrics 2,027 → ≤ 1,200; about 838 → ≤ 500; pipeline 344 → ≤ 250.

**Note:** `metrics.qmd` is the reference page and the destination for everything moved off the other pages. Its budget is the loosest for that reason. Trim its *commentary*, not its table rows: every row of every column table stays.

- [ ] **Step 1: Extend the guard**

In `tests/test_style.py`, change:

```python
FILES = ["index.qmd"]
WORD_BUDGET = {"index.qmd": 420}
```

to:

```python
FILES = ["index.qmd", "metrics.qmd", "about.qmd", "pipeline.qmd"]
WORD_BUDGET = {"index.qmd": 420, "metrics.qmd": 1200,
               "about.qmd": 500, "pipeline.qmd": 250}
```

The `metrics.qmd` figure counts its prose only. The generated column reference added in Task 3 renders `EXPLAIN` at runtime and is not in the file's source, so it does not count against this budget — `EXPLAIN` has its own budget in Task 8.

- [ ] **Step 2: Run to verify it fails**

Run: `OPDI_REPO=/home/jupyter/work/opdi-workspace/opdi python -m pytest tests/test_style.py -q`

Expected: FAIL on all three new files.

- [ ] **Step 3: Trim `metrics.qmd`**

Specific cuts, in file order:

1. **"Sign conventions" preamble.** Replace the two sentences with: `Both quantities are signed on purpose. An absolute value merges a track that started early with one that started late, which are opposite conditions.`
2. **The `t_source` callout.** Keep the numbers, drop the second explanation of them. Replace the body's last two paragraphs with: `The per-endpoint flags `dep_measured` and `arr_measured` carry the answer. `t_source` is left untouched so nothing already published on it moves.`
3. **The estimated-times paragraph** after the tier table. Cut from "That distinction decides what may be asked of them…" through "…already say." and replace with: `An accurate estimate of a *duration* supports a median taxi-out figure. An arrival time reconstructed from two predicted durations supports nothing, because it contains no measurement of the landing: `ARVT_3` reproduces as `AOBT_3 + TAXI_TIME_3 + FLT_DUR_3` to within 7 s at the median.`
4. **"Spanned is not observed" callout.** Keep all three definitions; cut the closing paragraph to: `The coverage index uses **signal**. Continuity sits beside it as a diagnostic, because high continuity with low signal is a thin but unbroken stream. Reach is kept because high reach with low continuity is the failure continuity was added to catch.`
5. **The `dep_signal_est` paragraph.** Replace with: `Signal, reach and continuity above are computed only from measured milestones. `dep_signal_est` reuses the taxi-out computation over `[AOBT_3, AOBT_3 + TAXI_TIME_3]`, a window bounded by a predicted taxi time, for aerodromes whose times are not measured. It is not comparable with a measured figure, so the two never share a column.`
6. **"Segmentation quality" preamble.** Keep both measured findings (392 s; −0.009 across twelve aerodromes) and the confound sentence. Cut the opening sentence to: `Present so a poor coverage number can be attributed to reception or to the algorithm. Every flight falls in exactly one class; a flight that is both merged and fragmented counts as **merged**.`
7. **"The coverage index, spelled out".** Keep the formula, the four bullets and the blank-not-zero rule. Delete the paragraph beginning "`coverage_index` is **NaN**, not zero, when no continuity term exists" — it restates the preceding paragraph — and the closing line "Every component stays a visible column…".

- [ ] **Step 4: Trim `about.qmd`**

1. **"What changed from the first version".** Cut to three sentences: `The coverage measure was replaced. It used to be **reach**: how far before wheels-off a track's first position report lay, which let a single report at the stand count as a fully covered taxi. It is now **continuity**: the ground phase is cut into 30-second slices and each is asked whether anything was heard in it.` Then keep: `Every number on this site changed, and the two versions are not comparable. Reach is still in the published CSVs as `dep_reach_p50` and `arr_reach_p50`.`
2. **Limitations.** Keep every bullet — each one bounds a claim. Trim each to at most two sentences. The *Segmentation errors bias the reach figure* bullet is the longest and reduces to: `**Segmentation errors bias the reach figure in both directions**, though reach appears on no page and does not touch the headline. A merged track spans two flights so its reach clips optimistically to 1.0; a fragmented flight is measured against its dominant track so its reach is understated. On the 2025 sample that is 0.8% merged against 8.2% fragmented. Continuity is far less exposed, because it counts observations inside a fixed window.`
3. **The provenance paragraph** after the table reduces to: `This matters more here than in a report that re-runs its own analysis. The site renders offline, which is exactly the condition under which a stale CSV renders cleanly and says nothing about being stale.`

- [ ] **Step 5: Trim `pipeline.qmd`**

Four specific cuts. The mermaid diagram and the "What runs where" table are untouched.

1. **"Two edges that carry the whole result" preamble.** Replace with: `Both are silent failure modes: they produce complete, plausible numbers rather than errors, so the diagram is drawn to make them visible.`
2. **First callout body** (``track_extents`` is fed from the assignment table). Replace with: ``` `overlap_join` clips every sample to `[t_off, t_land]`. Extents taken after it could only land *inside* the interval, so boundary error would be one-sided: a track starting before take-off or ending after landing would be invisible, and a track merging two flights would score near-zero error for the merge. ``` This drops the "what the number measured would be sampling cadence" clause, which restates the sentence it sits in.
3. **Second callout body** (Detection needs ground truth). Replace the closing sentence with: `Recovering it needs a left join from the full ground-truth table.`
4. **Closing paragraph.** Replace with: `Only the first three stages need access to anything. From the per-flight table onward the site rebuilds from committed data alone, which is what lets CI republish it on every push.` ("The split is the point" is a banned construction.)

**Cut 3 is a correctness fix as well as a trim, and is the one thing in this plan that changes a claim rather than its length.** `pipeline.qmd` currently ends that callout by calling detection "the strongest coverage signal on this site". `index.qmd` and the `detection_pct` explanation both call it a floor that separates almost nothing, and the fleet summary shows why: it is above 99% at four measured aerodromes in five. The two statements cannot both stand. Keep the `index.qmd` framing, which the data supports, and delete the claim rather than rewriting it.

- [ ] **Step 6: Run the tests**

Run: `OPDI_REPO=/home/jupyter/work/opdi-workspace/opdi python -m pytest tests/ -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add site/metrics.qmd site/about.qmd site/pipeline.qmd tests/test_style.py
git commit -m "Cut the commentary from Metrics, About and Pipeline"
```

---

## Task 8: Trim the explanations themselves

**Files:**
- Modify: `src/oac/labels.py`
- Test: `tests/test_style.py`, `tests/test_labels.py`

**Targets:** `EXPLAIN` 2,135 → ≤ 1,500 words; `TIERS_EXPLAINED` 324 → ≤ 150.

**Why 1,500 and not lower.** `EXPLAIN` is now the *reference*, not the inline
copy: the tooltips carry the one-line version, and this is what a reader gets
when they follow the link. Squeezing it to half would mean a 22-word average
across 51 entries, which would gut the page the tooltips point at. The
arithmetic: the four rewrites in Step 4 take the total from 2,135 to 1,780; the
seven entries named in Step 5 come down from 554 words to about 350; small
trims across the rest reach roughly 1,450. The large reduction the reviewer
asked for is delivered by *removal from every table*, not by shortening the
reference. Site-wide the budgets in Global Constraints total a 45% cut.

**Note:** this runs last on purpose. Tasks 1–4 moved `EXPLAIN` to one rendering location and gave every column a short tip; only now is it clear which sentences the tip already carries and which the reader still needs.

- [ ] **Step 1: Extend the guard**

Add to `tests/test_style.py`:

```python
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
    assert words(TIERS_EXPLAINED) <= 150, (
        f"TIERS_EXPLAINED is {words(TIERS_EXPLAINED)} words, budget 150")


def test_no_single_explanation_is_a_wall_of_text():
    """The longest entry was 249 words, which is a page, not a definition."""
    from oac.labels import EXPLAIN
    long = {c: words(v) for c, v in EXPLAIN.items() if words(v) > 90}
    assert not long, f"explanations over 90 words: {long}"
```

- [ ] **Step 2: Run to verify it fails**

Run: `OPDI_REPO=/home/jupyter/work/opdi-workspace/opdi python -m pytest tests/test_style.py -q`

Expected: FAIL on three counts — `EXPLAIN` is 2,135 words against 1,500, `tracking_err_pct` alone is 249 against the 90-word per-entry ceiling, and there are 24 em-dash asides against an allowance of 16.

- [ ] **Step 3: Rewrite `TIERS_EXPLAINED`**

```python
TIERS_EXPLAINED = """\
::: {.callout-note collapse="true"}
## Measured or estimated?

**Tier A (measured).** The airport operator reports the real times: off the
stand, wheels off, wheels on, on the stand. The taxi has exact bounds, so how
much of it was received can be measured.

**Tier B (estimated).** Network Manager covers all of Europe, but records no
runway or stand times. Take-off is an off-block time plus a predicted taxi.

That prediction is unbiased but imprecise, so it supports a **median** taxi-out
figure across a few hundred movements and says nothing about any one flight.
Estimated aerodromes therefore carry an estimated departure figure in its own
column, never mixed into the measured ranking.

Arrivals have no fallback: no in-block time exists outside the airport's own
records, so nothing marks the end of a taxi-in. The coverage index needs both
sides and appears only in the measured table.
:::
"""
```

- [ ] **Step 4: Rewrite the four longest `EXPLAIN` entries**

Word counts below are measured, not estimated, and all four clear the 90-word
ceiling asserted in Step 1.

`tracking_err_pct` (249 -> 88):

```python
    "tracking_err_pct": "The share of this aerodrome's movements the "
                        "track-building step got wrong: split and merged "
                        "added together.\n\n"
                        "**Split** understates coverage, because only the "
                        "largest piece is scored. A split departure's track "
                        "starts a median **392 seconds later** than a clean "
                        "one, at 182 of 206 aerodromes.\n\n"
                        "**Merged** costs a whole flight: two share a track, "
                        "one survives, the other is absent downstream. No "
                        "measurable effect on the survivor (median −0.009, on "
                        "0.8% of movements).\n\n"
                        "So a high figure means coverage understated and "
                        "movements missing, not poor reception.",
```

`detection_pct` (205 -> 86):

```python
    "detection_pct": "Movements seen divided by movements the reference data "
                     "records. **Read it as a floor, not a coverage figure**: "
                     "above 99% at four measured aerodromes in five, it "
                     "separates \u201cinvisible to the network\u201d from "
                     "\u201cseen, but only partly\u201d and says nothing about how "
                     "much was tracked.\n\n"
                     "A flight counts as seen if one position report comes "
                     "from the same airframe, matched on the ICAO address, "
                     "and falls between its take-off and landing. That window "
                     "is the **airborne** one, which is why this says nothing "
                     "about ground coverage.",
```

`coverage_index` (125 -> 82):

```python
    "coverage_index": "The share of movements seen at all, multiplied by the "
                      "share of a typical ground movement received (the "
                      "average of the taxi-out and taxi-in medians).\n\n"
                      "Read it as the expected share of one movement the "
                      "network captures. 1.00 is perfect; 0.00 means the "
                      "surface is invisible even where the aircraft is "
                      "tracked once airborne.\n\n"
                      "Left **blank**, never zero, where the ground figures "
                      "are unavailable. Falling back to detection alone would "
                      "rank an unmeasurable aerodrome as though it were well "
                      "covered.",
```

`dep_signal_p50` (111 -> 79):

```python
    "dep_signal_p50": "The taxi-out is the interval between two measured "
                      "times: off the stand, and wheels off the runway. The "
                      "feed delivers about one position report every 5 "
                      "seconds, so a taxi of *n* seconds should produce about "
                      "*n*/5 reports. We count how many arrived and divide by "
                      "how many were expected, then take the median across "
                      "this aerodrome's departures.\n\n"
                      "1.00 means the aircraft was tracked the whole way out. "
                      "0.10 means nine reports in ten never arrived.",
```

Facts kept in each: the 392 s and 182-of-206 findings, the -0.009 and 0.8%
figures, the >99% detection level, the ICAO-address match rule, the airborne
window, the blank-not-zero rule, and the 5-second cadence. What went is the
second pass at each of them.

- [ ] **Step 5: Trim the remaining entries to the ≤ 90-word ceiling**

Apply the same rule throughout: one statement of what the column is, one of how to read it, and any measured number. Drop the sentence explaining why the definition is interesting. These seven are over or near the line and together account for 554 words; bring each to about 50:

| Entry | Now | Target | Cut |
|---|---|---|---|
| `dep_reach_p50` | 94 | ≤ 55 | Keep the definition and the "one report at the stand scores 1.00" example. Drop the above-1.00/below-0 paragraph, which the Metrics domain column states. |
| `n_gt` | 92 | ≤ 50 | Keep what is counted and the ≥ 20 floor. Drop the sentence justifying the floor. |
| `dep_continuity_p50` | 78 | ≤ 50 | Keep the 30-second-bin definition and the "read it against received" contrast. Drop the reverse case. |
| `measured_pct` | 77 | ≤ 45 | Keep the definition and the 50% threshold. Drop the "not a close call" observation. |
| `rating` | 75 | ≤ 45 | Keep the five thresholds. Drop the paragraph on why they are round numbers. |
| `n_detected` | 70 | ≤ 45 | Keep the match rule. Drop the callsign rationale, which `detection_pct` already carries. |
| `merged_pct_dep` | 68 | ≤ 45 | Keep the unrecoverability point and the −0.009 figure. Drop the framing sentence. |

Then trim the remaining entries by roughly 15% each, applying the same rule: one statement of what the column is, one of how to read it, and any measured number.

- [ ] **Step 6: Run the whole suite**

Run: `OPDI_REPO=/home/jupyter/work/opdi-workspace/opdi python -m pytest tests/ -q`

Expected: PASS.

- [ ] **Step 7: Full render check**

Build a clean venv matching CI and render, because a missing dependency or a broken import only shows here:

```bash
/home/jupyter/work/opdi-workspace/opdi/.venv310/bin/python3.10 -m venv /tmp/oacci
/tmp/oacci/bin/pip install -q -e .
PATH=/tmp/oacci/bin:$PATH PYTHONPATH="$(pwd)/src:$(pwd)" python scripts/gen_pages.py
PATH=/tmp/oacci/bin:$PATH PYTHONPATH="$(pwd)/src:$(pwd)" quarto render site/index.qmd
PATH=/tmp/oacci/bin:$PATH PYTHONPATH="$(pwd)/src:$(pwd)" quarto render site/metrics.qmd
```

Then confirm in the rendered HTML:
- `data-bs-toggle="tooltip"` appears on `index.html` at least 15 times.
- `bootstrap.Tooltip` appears at least once (the include reached the page).
- `callout` blocks titled "What these columns mean" appear **zero** times.
- The four download links still resolve to `downloads/…`.

Note: project-wide `quarto render site` no-ops in this sandbox — confirmed generic against a throwaway minimal project — so render single files. The full project build is only confirmable in CI.

- [ ] **Step 8: Commit**

```bash
git add src/oac/labels.py tests/test_style.py tests/test_labels.py
git commit -m "Cut the column explanations to what the tooltips do not already say"
```

---

## Verification checklist

Run after the last task, before opening the PR:

- [ ] `OPDI_REPO=/home/jupyter/work/opdi-workspace/opdi python -m pytest tests/ -q` — all green.
- [ ] `grep -rn "explain_block" src/ site/ tests/` returns nothing.
- [ ] `grep -c 'data-bs-toggle' site/index.html` ≥ 15.
- [ ] Downloads unchanged: `tests/test_tables.py` passes without having been edited, and the CSV header line contains no `<`.
- [ ] `python scripts/gen_pages.py` leaves `site/airports/index.qmd` byte-identical.
- [ ] Word counts hit the Global Constraints table. Re-measure, do not assume.
- [ ] Hover a heading, a rating value, and a heading in the last (rightmost) column of the all-aerodromes table — the last one is where `container: "body"` earns its place, because `scrollX` would otherwise clip it.

## Known risks

1. **Tooltips on a sortable header.** DataTables makes the whole `<th>` a sort control. Clicking the tooltip span sorts the column. That is expected behaviour and not a defect; the tooltip opens on hover and focus, not click, so the two do not fight.
2. **Duplicate display names.** `clean_pct_dep` and `clean_pct_arr` share the display name "One flight, one track", which `page.py` already works around for markdown tables. Their tips differ, so tooltip headers are distinct strings and the collision disappears. Do not rely on this in a table showing both.
3. **`search.json`.** Quarto indexes rendered page text. Header markup may appear in the search index. Cosmetic, and worth a look at the end.
4. **The project render cannot be verified locally.** Single-file renders work; `quarto render site` no-ops in this sandbox. Whether `include-after-body` is applied to all 352 generated aerodrome pages in a full project build is confirmable only in CI. `quarto inspect site` parsing the key correctly is the strongest local signal.
