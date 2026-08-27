#!/usr/bin/env Rscript
# ---------------------------------------------------------------------------
# Fetch one month of EUROCONTROL ground truth for the airport-coverage study.
#
# RUNS ONLY ON THE WORK LAPTOP. It needs ROracle and PRISME access via
# PRU_READ_USR / PRU_READ_PWD / PRU_READ_DBNAME. Never run it from the
# pipeline, from the cluster, or from a Quarto render -- the site must build
# with no credentials and no database.
#
#   Rscript scripts/fetch_reference.R 2026-06
#   Rscript scripts/fetch_reference.R 2026-06 --days 05,06,07
#
# Writes reference/apdf_<YYYYMM>.parquet and reference/flights_<YYYYMM>.parquet,
# then validates them against what this study actually needs -- which is more
# than the pipeline needs, because coverage is measured from block times and
# per-aerodrome sample sizes rather than from flight counts.
#
# This is a study-scoped sibling of `opdi/reference/extract.R`. It issues the
# same two `eurocontrol` queries, deliberately: the monthly-window trap below
# is a property of `apdf_tidy`, not of either caller, and a second way of
# querying would be a second way to get it wrong. What is added here is the
# validation, which is specific to this study and does not belong in opdi.
# ---------------------------------------------------------------------------

#: Where the extracts land. NOT this repo: ground truth lives in
#: `opdi/reference/` under git-lfs, which is what `mirror_reference.py` uploads
#: to S3 and what the cluster reads. The *script* belongs here; the *data*
#: belongs in its established home, and splitting them is what keeps one copy.
#: Override with --out if your checkout is laid out differently.
OUT_DIR <- "../opdi/reference"

#: Aerodromes below this many movements in the sampled days cannot carry a
#: meaningful per-aerodrome percentile. Must match `oac.aggregate.MIN_N`.
MIN_N <- 20

suppressPackageStartupMessages({
  library(eurocontrol)
  library(arrow)
  library(dplyr)
  library(lubridate)
})


parse_args <- function(args) {
  if (length(args) < 1) {
    stop("Usage: Rscript scripts/fetch_reference.R YYYY-MM ",
         "[--days DD,DD,DD] [--out DIR]")
  }
  month <- suppressWarnings(ymd(paste0(args[[1]], "-01")))
  if (is.na(month)) {
    stop("Could not parse '", args[[1]], "'. Expected YYYY-MM, e.g. 2026-06.")
  }
  out <- OUT_DIR
  j <- which(args == "--out")
  if (length(j) == 1 && length(args) > j) out <- args[[j + 1]]

  days <- NULL
  i <- which(args == "--days")
  if (length(i) == 1 && length(args) > i) {
    dd <- strsplit(args[[i + 1]], ",")[[1]]
    days <- as.Date(sprintf("%s-%s", format(month, "%Y-%m"), trimws(dd)))
    if (any(is.na(days))) stop("Could not parse --days '", args[[i + 1]], "'.")
  }
  list(month = month, days = days, out = out)
}


extract_one <- function(label, query, path) {
  message("  ", label, " ...")
  # collect() is required: these are lazy Oracle-backed tables and
  # write_parquet needs them materialised.
  df <- collect(query)
  n <- nrow(df)
  if (n == 0L) {
    warning(
      label, " returned 0 rows. Either the month has not been delivered yet, ",
      "or the window tripped the SRC_DATE_FROM filter described below.",
      immediate. = TRUE
    )
  }
  write_parquet(df, path)
  message("    ", format(n, big.mark = ","), " rows -> ", path)
  list(rows = n, data = df)
}


# -- validation -------------------------------------------------------------
#
# Each check below corresponds to something that, if wrong, produces a
# complete and plausible-looking coverage site that is quietly false. They are
# printed rather than thrown, except where a zero makes the month unusable.

check_block_times <- function(apdf) {
  # BLOCK_TIME_UTC is AOBT on a DEP row and AIBT on an ARR row. It is the
  # denominator of every capture fraction: without it there is no Tier A, and
  # the study degrades to detection rate alone.
  message("\n[1/4] Block-time completeness (the capture denominator)")
  for (ph in c("DEP", "ARR")) {
    sub <- filter(apdf, SRC_PHASE == ph)
    if (nrow(sub) == 0L) {
      warning("No ", ph, " rows at all -- Tier A cannot be built for this month.",
              immediate. = TRUE)
      next
    }
    miss <- mean(is.na(sub$BLOCK_TIME_UTC))
    lbl <- if (ph == "DEP") "AOBT" else "AIBT"
    message(sprintf("      %s rows: %s | %s missing: %.3f%%",
                    ph, format(nrow(sub), big.mark = ","), lbl, 100 * miss))
    if (miss > 0.05) {
      warning(sprintf(
        "%s is missing on %.1f%% of %s rows. Prior months ran at 0.02%%. ",
        100 * miss, ph), "Capture fractions for this month will be thin.",
        immediate. = TRUE)
    }
  }
}


check_ground_phase_sign <- function(apdf) {
  # A non-positive ground phase is bad reference data, not zero coverage, and
  # `oac.aggregate.capture` excludes it rather than clipping. If the rate is
  # high the exclusion stops being a footnote and starts moving medians.
  message("\n[2/4] Ground-phase sign (AOBT < ATOT, AIBT > ALDT)")
  dep <- filter(apdf, SRC_PHASE == "DEP", !is.na(BLOCK_TIME_UTC), !is.na(MVT_TIME_UTC))
  arr <- filter(apdf, SRC_PHASE == "ARR", !is.na(BLOCK_TIME_UTC), !is.na(MVT_TIME_UTC))
  if (nrow(dep) > 0L) {
    bad <- mean(dep$BLOCK_TIME_UTC >= dep$MVT_TIME_UTC)
    message(sprintf("      DEP with AOBT >= ATOT: %.3f%% (excluded from capture)",
                    100 * bad))
  }
  if (nrow(arr) > 0L) {
    bad <- mean(arr$BLOCK_TIME_UTC <= arr$MVT_TIME_UTC)
    message(sprintf("      ARR with AIBT <= ALDT: %.3f%% (excluded from capture)",
                    100 * bad))
  }
}


check_airport_counts <- function(apdf, flights, days) {
  # Per-aerodrome percentiles need per-aerodrome sample sizes. A month that
  # looks fine in total can still be unusable per airport.
  message("\n[3/4] Per-aerodrome sample sizes over the sampled days")
  if (is.null(days)) {
    message("      (no --days given; counting the whole month)")
    dep <- filter(apdf, SRC_PHASE == "DEP")
    nm <- flights
  } else {
    message("      days: ", paste(format(days, "%Y-%m-%d"), collapse = ", "))
    dep <- filter(apdf, SRC_PHASE == "DEP", as.Date(MVT_TIME_UTC) %in% days)
    nm <- filter(flights, as.Date(AOBT_3) %in% days)
  }
  a <- count(dep, ADEP_ICAO, name = "n")
  b <- count(nm, ADEP, name = "n")
  message(sprintf("      Tier A (APDF): %d aerodromes, %d at n >= %d",
                  nrow(a), sum(a$n >= MIN_N), MIN_N))
  message(sprintf("      Tier B (NM):   %d aerodromes, %d at n >= %d",
                  nrow(b), sum(b$n >= MIN_N), MIN_N))
  if (sum(a$n >= MIN_N) < 50) {
    warning("Fewer than 50 Tier A aerodromes clear the threshold. ",
            "Earlier samples cleared 94. Check the day list.", immediate. = TRUE)
  }
}


check_join_key <- function(flights) {
  # AIRCRAFT_ADDRESS *is* icao24 and is the only join key to ADS-B. If it is
  # largely NULL every flight reads as undetected, which is indistinguishable
  # in the output from genuinely absent coverage.
  message("\n[4/4] ADS-B join key")
  miss <- mean(is.na(flights$AIRCRAFT_ADDRESS))
  message(sprintf("      AIRCRAFT_ADDRESS (= icao24) missing: %.2f%%", 100 * miss))
  if (miss > 0.02) {
    warning(sprintf(
      "icao24 missing on %.1f%% of NM rows. Those flights cannot be matched ",
      100 * miss),
      "to any track and will read as undetected -- a coverage number that is ",
      "really a ground-truth gap.", immediate. = TRUE)
  }
}


main <- function(args) {
  cfg <- parse_args(args)
  month <- cfg$month
  out_dir <- cfg$out

  if (!dir.exists(out_dir)) {
    stop("Directory '", out_dir, "' not found. Ground truth belongs in the ",
         "opdi checkout's reference/ (git-lfs). Pass --out to override.")
  }

  # ONE CALENDAR MONTH AT A TIME. This is a correctness requirement, not a
  # convention: apdf_tidy() filters on MVT_TIME_UTC *and* SRC_DATE_FROM against
  # the same window. APDF is delivered monthly, so SRC_DATE_FROM tracks the
  # delivery month -- widen the window and every movement whose source record
  # starts outside it is dropped, with no error and no warning.
  wef <- format(month, "%Y-%m-%d")
  til <- format(month %m+% months(1), "%Y-%m-%d")
  tag <- format(month, "%Y%m")

  message("Extracting ", wef, " -> ", til, " (exclusive)")

  conn <- db_connection(schema = "PRU_READ")
  on.exit({
    message("\nClosing DB connection.")
    try(DBI::dbDisconnect(conn), silent = TRUE)
  }, add = TRUE)

  apdf_path <- file.path(out_dir, sprintf("apdf_%s.parquet", tag))
  flights_path <- file.path(out_dir, sprintf("flights_%s.parquet", tag))

  apdf <- extract_one("apdf_tidy", apdf_tidy(conn = conn, wef = wef, til = til),
                      apdf_path)
  flights <- extract_one("flights_tidy",
                         flights_tidy(conn = conn, wef = wef, til = til),
                         flights_path)

  if (apdf$rows == 0L || flights$rows == 0L) {
    stop("One of the extracts is empty. The month is not usable; stopping ",
         "before the validation would report on nothing.")
  }

  message("\n", strrep("-", 70))
  message("Validating for the airport-coverage study")
  message(strrep("-", 70))
  check_block_times(apdf$data)
  check_ground_phase_sign(apdf$data)
  check_airport_counts(apdf$data, flights$data, cfg$days)
  check_join_key(flights$data)

  message("\n", strrep("-", 70))
  message("Done. Next, on this laptop, in the opdi checkout:")
  message("  1. Confirm both parquet files went through git-lfs, not in as blobs:")
  message("       git add reference/apdf_", tag, ".parquet reference/flights_",
          tag, ".parquet")
  message("       git cat-file -p :reference/apdf_", tag, ".parquet | head -3")
  message("     Expect 'version https://git-lfs.github.com/spec/v1' + oid + size.")
  message("  2. Record both rows in reference/MANIFEST.md:")
  message(sprintf(
    "       | apdf_%s.parquet | apdf_tidy(wef=\"%s\", til=\"%s\") | %s | %s |",
    tag, wef, til, Sys.Date(), format(apdf$rows, big.mark = ",")))
  message(sprintf(
    "       | flights_%s.parquet | flights_tidy(wef=\"%s\", til=\"%s\") | %s | %s |",
    tag, wef, til, Sys.Date(), format(flights$rows, big.mark = ",")))
  message("  3. Commit and push.")
  message("\nThen, on the OSN cluster (pull opdi first):")
  message("     python benchmarks/mirror_reference.py --include '*_", tag,
          ".parquet'")
  message("     python scripts/run_offsets.py --period ", tag)
  message(strrep("-", 70))

  invisible(NULL)
}


main(commandArgs(trailingOnly = TRUE))
