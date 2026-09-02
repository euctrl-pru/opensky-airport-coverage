"""Extract a few example trajectories per aerodrome, for the maps.

    ../opdi/.venv310/bin/python scripts/run_examples.py --period 2026

Writes `data/example_tracks_<period>.parquet`: the position reports of a
handful of movements per aerodrome, chosen to span that aerodrome's own range
of coverage quality.

**Chosen, not sampled at random.** At an aerodrome where 90% of movements look
alike, six random tracks show the same thing six times. Picking the
best-covered, the median and the worst-covered puts the range on one map, so a
reader sees what good and bad reception look like *here* rather than in the
abstract.

**Departures for every aerodrome, arrivals only where the times are
measured.** NM supplies both ends of a departure window for flights APDF never
saw, so a Tier B aerodrome can still have its taxi-out ranked -- against a
*predicted* taxi duration rather than a measured one, which is why each pick
carries `measured`. No such estimate exists on the arrival side: that window
ends at the in-block time and NM has no in-block column at all.
"""

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from oac._opdi import bootstrap  # noqa: E402

bootstrap()

import osn_sample  # noqa: E402
import provenance  # noqa: E402
import track_methods  # noqa: E402
from pyspark.sql import Window  # noqa: E402
from pyspark.sql import functions as F  # noqa: E402

from oac.positions import positioned  # noqa: E402

DATA = REPO / "data"

#: Movements per aerodrome per side. Three is enough for best/median/worst
#: without turning the map into spaghetti.
PER_SIDE = 3

#: Position reports kept per movement. A 40-minute flight at 5 s is ~480
#: reports; thinning to this keeps the shape and bounds the page weight.
MAX_POINTS = 220


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--period", choices=sorted(track_methods.PERIODS), required=True)
    ap.add_argument("--executors", type=int, default=10)
    args = ap.parse_args()

    sys.stdout.reconfigure(line_buffering=True)
    osn_sample.load_dotenv()
    osn_sample.RESEARCH_EXECUTORS = args.executors
    spark = osn_sample.build_spark(cores=8, driver_memory="8g")

    p = track_methods.PERIODS[args.period]
    days = p["days"]
    print(f"period {args.period}, {args.executors} executors")

    import pandas as pd

    off = pd.read_parquet(DATA / f"flight_offsets_{args.period}.parquet")
    off = off[off["detected"].fillna(False).astype(bool)]

    # Rank each aerodrome's own movements by how well observed they were, then
    # take the best, the middle and the worst.
    #
    # **Departures are picked for every aerodrome, arrivals only where the
    # times are measured**, and the asymmetry is structural rather than a
    # choice about thoroughness. A departure window is `[aobt, t_off]` and NM
    # supplies both ends -- an off-block time and a predicted taxi duration --
    # for flights APDF never saw. An arrival window ends at the in-block time,
    # and NM has no in-block column at all, so there is nothing to estimate
    # from. Restricting both sides to measured flights left 717 of the 807
    # ranked aerodromes with no example trajectory at all, and the map is the
    # one place a reader can see *where* reception fails rather than by how
    # much -- which is exactly what the aerodromes with no APDF coverage most
    # need shown.
    picks = []
    for side, key, measured, seen, total in (
        ("dep", "gt_adep", "dep_measured", "dep_bins_seen", "dep_bins_total"),
        ("arr", "gt_ades", "arr_measured", "arr_bins_seen", "arr_bins_total"),
    ):
        s = off.copy()
        if side == "arr":
            s = s[s[measured].fillna(False).astype(bool)]
        s = s[s[total].notna() & (s[total] > 0)]
        if s.empty:
            continue
        s["q"] = s[seen] / s[total]
        # Travels with the pick rather than being re-derived per aerodrome: a
        # single aerodrome can have both kinds of flight, so "is this example
        # ranked against a measured taxi or a predicted one" is a property of
        # the movement and not of the page it lands on.
        s["_measured"] = s[measured].fillna(False).astype(bool)
        for icao, g in s.groupby(key):
            g = g.sort_values("q")
            n = len(g)
            idx = sorted({0, n // 2, n - 1})[:PER_SIDE]
            for rank_pos, i in enumerate(idx):
                r = g.iloc[i]
                picks.append({
                    "icao": icao, "side": side, "track_id": r["track_id"],
                    "flight_key": r["flight_key"], "quality": float(r["q"]),
                    "measured": bool(r["_measured"]),
                    "label": ["worst", "median", "best"][
                        min(rank_pos, 2) if len(idx) == 3
                        else (0 if rank_pos == 0 else 2)
                    ],
                })
    sel = pd.DataFrame(picks).dropna(subset=["track_id"])
    print(f"{len(sel):,} example movements across {sel.icao.nunique()} "
          f"aerodromes ({int(sel.measured.sum()):,} against measured times, "
          f"{int((~sel.measured).sum()):,} against NM-estimated ones)")

    sel_sdf = spark.createDataFrame(sel[["icao", "side", "track_id", "label",
                                         "quality", "measured"]])
    # The same read-time filter the metrics path applies, from the same
    # definition -- an example map drawn from a different population than the
    # numbers beside it would misattribute every gap it shows.
    sv = positioned(
        spark.read.parquet(p["tracks"])
        .filter(F.to_date("event_time").isin(days))
    ).select("track_id", "event_time", "lat", "lon", "on_ground",
             "baro_altitude_c")
    j = sv.join(F.broadcast(sel_sdf), "track_id", "inner")

    # Thin each track evenly rather than truncating it: a truncated track stops
    # mid-flight and reads as lost coverage, which is the very thing these maps
    # are used to judge.
    w = Window.partitionBy("track_id", "icao", "side").orderBy("event_time")
    cnt = Window.partitionBy("track_id", "icao", "side")
    j = (
        j.withColumn("_i", F.row_number().over(w))
        .withColumn("_n", F.count(F.lit(1)).over(cnt))
        .withColumn("_step", F.greatest(F.ceil(F.col("_n") / MAX_POINTS), F.lit(1)))
        .filter((F.col("_i") % F.col("_step")) == 0)
        .drop("_i", "_n", "_step")
    )

    out = j.toPandas()
    out["period"] = args.period
    name = f"example_tracks_{args.period}.parquet"
    out.to_parquet(DATA / name, index=False)
    mb = (DATA / name).stat().st_size / 1e6
    print(f"wrote {len(out):,} points for {out.track_id.nunique():,} tracks "
          f"to data/{name} ({mb:.1f} MB)")

    provenance.record(
        DATA, name, script="scripts/run_examples.py", argv=sys.argv[1:],
        code_paths=[REPO / "scripts" / "run_examples.py"],
        inputs={"points": len(out), "tracks": int(out.track_id.nunique()),
                "aerodromes": int(out.icao.nunique()),
                "estimated_windows": int((~out["measured"]).sum())},
        input_tables=[p["tracks"]],
        notes=(f"{PER_SIDE} movements per aerodrome per side, spanning that "
               f"aerodrome's own coverage range; thinned to <= {MAX_POINTS} "
               f"points per track. Departures are picked for every aerodrome, "
               f"ranked against an NM-estimated taxi duration where APDF has "
               f"no measured one (`measured` says which); arrivals only where "
               f"the in-block time is measured, since NM has no such column. "
               f"State vectors without a lat/lon are dropped at read time."),
    )
    print("provenance recorded")


if __name__ == "__main__":
    main()
