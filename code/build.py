#!/usr/bin/env python3
"""Build the NOAA tide-flooding task from NOAA's verified daily maxima.

Target: does a station's daily maximum observed water level exceed that station's published NOS
*minor* flood threshold on the following local day?

Two contract-complete levels are emitted from one row set, because the runner's contract is one
task (`task.json` + `data/train.csv` + `data/eval.csv` + a private holdout) with one eval set:

  * `temporal`          - all 122 stations, train 2006-2021, eval 2022-2023, holdout 2024-2025.
  * `station_disjoint`  - the station holdout (group0, by station-id order) is never in training;
                          train on group1+group2, eval on group0 2022-2023, holdout on group0 2024-2025.

Source route: `product=daily_max_min`, `interval=6`, `datum=STND`, `time_zone=GMT`, one request per
station-year (~2,440 requests, ~178 MB for 122 stations x 20 years). Verified maxima with a
completeness percentage, not preliminary rows, and not the 29,160-request raw-series route.

Datum matters: the published `nos_minor` threshold is in the station datum (STND). Comparing an
MLLW series against it rejects Boston's record 2018 tide, which is how the trap was found.

Features are observations only and station-relative, and every one of them uses data up to the
previous local day - station statistics come from *trailing* windows, so the future cannot leak into
a row. NOAA tide predictions and model guidance are deliberately excluded: they are not
observations, and including them is the way an agent defeats the task.

  python3 build.py --probe 8443970 --year 2024      # one station-year, parses and prints rows
  python3 build.py --out <dir> [--stations N]       # the build (intended for a worker)
"""

import argparse
import concurrent.futures
import csv
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
API = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
UA = {"User-Agent": "scout-dataset-factory/0.1 (bounded research build)"}
YEARS = list(range(2006, 2026))
TRAIN_YEARS = (2006, 2021)
EVAL_YEARS = (2022, 2023)
HOLDOUT_YEARS = (2024, 2025)
LOOKBACK = 30           # trailing window for station-relative scale
FLOOD_WINDOW = 7        # trailing window for recent exceedance count

FEATURES = ["margin_ft", "margin_ratio", "trailing7_mean", "trailing30_mean", "trailing30_std",
            "exceed_last7", "days_since_exceedance", "day_of_year", "latitude", "threshold_rank"]
# `latitude` is both a base column and a declared feature, so the shipped header is de-duplicated:
# a repeated column name makes a column-wise reader see twice as many values as labels, which
# surfaced as an unrelated crash inside the qualification gate rather than as a named finding.
COLUMNS = list(dict.fromkeys(
    ["row_id", "station_id", "station_name", "date", "latitude", "longitude", "threshold_ft"]
    + FEATURES + ["observed_max_ft", "minor_flood"]))
# The entity that must not cross a split is the station-day, not the station: a temporal split of a
# station panel deliberately reuses stations, so the station alone is not an entity key.
ID_COLUMNS = ["row_id", "station_id", "date"]


# The API rate-limits, and the worker's log shows 429s at 6 concurrent requests. Two runs taught
# the pacing: 3 attempts with a short linear backoff lost 594 station-years, and 6 attempts with an
# uncapped exponential backoff (up to 160 s per attempt, so minutes per request) turned the same
# losses into a run that could not finish inside its 120-minute job timeout.
PACE_LOCK = threading.Lock()
LAST_REQUEST = [0.0]
MIN_INTERVAL = 0.25          # seconds between request starts, across all threads
MAX_WAIT = 30.0              # a single wait never exceeds this
RATE_LIMIT_COOLDOWN = 20.0   # after a 429, hold every thread back this long


def _throttled_sleep(seconds):
    """Serialise the inter-request delay so concurrency cannot outrun the pace."""
    with PACE_LOCK:
        now = time.monotonic()
        wait = max(0.0, LAST_REQUEST[0] + MIN_INTERVAL - now)
        LAST_REQUEST[0] = now + wait
    if wait:
        time.sleep(wait)


def _cooldown(seconds):
    with PACE_LOCK:
        LAST_REQUEST[0] = max(LAST_REQUEST[0], time.monotonic() + seconds)


def fetch_json(url, attempts=5, timeout=120):
    """Paced fetch: report the *cause* rather than the URL, and never wait for minutes.

    A `429` holds every thread back briefly and then retries, which recovers the station-year
    without spending the job's whole budget on one request.
    """
    last = None
    for attempt in range(attempts):
        _throttled_sleep(0)
        try:
            request = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            last = f"HTTPError {exc.code}"
            if exc.code in (429, 403):
                # NOAA answers 403 as well as 429 when a client exceeds its limit: the second run
                # lost 60 station-years to 403s that my retry treated as permanent and retried
                # immediately.
                _cooldown(RATE_LIMIT_COOLDOWN)
                delay = min(MAX_WAIT, 5.0 * (attempt + 1))
            elif exc.code in (500, 502, 503, 504):
                delay = min(MAX_WAIT, 2.0 * (attempt + 1))
            else:
                delay = 0.0          # any other 4xx will not improve by waiting
            if delay:
                time.sleep(delay)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = f"{type(exc).__name__}: {str(exc)[:120]}"
            time.sleep(min(MAX_WAIT, 2.0 * (attempt + 1)))
    raise RuntimeError(f"failed after {attempts} attempts ({last})")


def daily_maxima(station_id, year):
    """One request: a whole station-year of 6-minute daily maxima, verified, with completeness."""
    url = (f"{API}?begin_date={year}0101&end_date={year}1231&station={station_id}"
           f"&product=daily_max_min&interval=6&datum=STND&time_zone=GMT&units=english"
           f"&application=dataset-factory&format=json")
    payload = fetch_json(url)
    block = (payload.get("data") or [{}])[0]
    out = {}
    for row in block.get("dailyMax6Min") or []:
        # The product answers an ISO date ("2024-01-01"); YYYYMMDD is accepted defensively. A
        # length-8 digit check here silently dropped all 366 rows, so both forms are parsed.
        raw = str(row.get("date6Min") or "").strip()
        if len(raw) == 8 and raw.isdigit():
            raw = f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
        if len(raw) != 10 or raw[4] != "-" or raw[7] != "-":
            continue
        value = row.get("value6Min")
        if value in (None, "", "null"):
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        try:
            complete = float(row.get("pcComplete6Min"))
        except (TypeError, ValueError):
            complete = None
        out[raw] = {"max_ft": value, "complete_pct": complete,
                    "flag": str(row.get("flag6Min") or "")}
    return out


def flood_days(station_id, year):
    """NOAA's own minor-flood days for the station-year, one request per station-year.

    Measured against the annual product on four stations for 2024: these flags match NOAA's counts
    exactly (25/26/23/20 = 94), where a reconstruction from 6-minute daily maxima gave 113-114 and
    an hourly reconstruction 98. The label is therefore the publisher's own determination rather
    than a competing definition of ours.
    """
    url = (f"https://api.tidesandcurrents.noaa.gov/dpapi/prod/webapi/htf/htf_daily.json"
           f"?station={station_id}&start_date={year}0101&end_date={year}1231")
    payload = fetch_json(url)
    out = set()
    for row in payload.get("DailyFloodCount") or []:
        if str(row.get("minFlag")) not in ("1", "1.0"):
            continue
        raw = str(row.get("day") or "")
        if "/" in raw:
            month, day, year_part = raw.split("/")
            raw = f"{year_part}-{month}-{day}"
        out.add(raw[:10])
    return out


def _safe_year(one_year, year, station_id, errors):
    """Fetch one station-year, recording a failure instead of losing the whole station."""
    try:
        return one_year(year)
    except RuntimeError as exc:
        errors.append({"station": station_id, "year": year, "error": str(exc)[:160]})
        return year, None, set()


def station_metadata(station_ids):
    """Published thresholds and coordinates. nos_minor is the label's threshold - kept physical."""
    url = ("https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations.json"
           "?type=waterlevels&expand=floodlevels")
    payload = fetch_json(url)
    wanted = {str(s) for s in station_ids}
    meta = {}
    for station in payload.get("stations") or []:
        station_id = str(station.get("id"))
        if station_id not in wanted:
            continue
        flood = station.get("floodlevels") or {}
        minor = flood.get("nos_minor")
        if isinstance(minor, dict):
            minor = minor.get("nos_minor")
        if not isinstance(minor, (int, float)):
            continue
        meta[station_id] = {"name": station.get("name"), "state": station.get("state"),
                            "latitude": station.get("lat"), "longitude": station.get("lng"),
                            "threshold_ft": float(minor)}
    return meta


def frozen_stations():
    data = json.loads((HERE / "station_list_result.json").read_text())
    return [str(station["id"]) for station in data["frozen_station_list"]["stations"]]


def group_of(station_id, order):
    """The recorded rule: sort by station id, every third station is the station holdout (group0)."""
    return order.index(station_id) % 3


def features_for(series, threshold, latitude, threshold_rank):
    """Station-relative features from trailing data only. `series` is date-ordered observations."""
    rows = []
    maxima = [point["max_ft"] for point in series]
    for index, point in enumerate(series):
        if index < LOOKBACK:                            # no trailing window yet: drop, do not guess
            continue
        previous = maxima[index - 1]
        window30 = maxima[index - LOOKBACK:index]
        window7 = maxima[index - 7:index]
        mean30 = sum(window30) / len(window30)
        mean7 = sum(window7) / len(window7)
        variance = sum((value - mean30) ** 2 for value in window30) / len(window30)
        exceed_last7 = sum(1 for value in window7 if value > threshold)
        days_since = None
        for back in range(1, LOOKBACK + 1):
            if maxima[index - back] > threshold:
                days_since = back - 1
                break
        if days_since is None:
            days_since = LOOKBACK                        # censored: "at least LOOKBACK days"
        day = date.fromisoformat(point["date"])
        rows.append({
            "row_id": f"{point['station_id']}:{point['date']}",
            "station_id": point["station_id"],
            "station_name": point["station_name"],
            "date": point["date"],
            "latitude": latitude,
            "longitude": point["longitude"],
            "threshold_ft": threshold,
            "margin_ft": round(previous - threshold, 4),
            "margin_ratio": round(previous / threshold, 6) if threshold else None,
            "trailing7_mean": round(mean7, 4),
            "trailing30_mean": round(mean30, 4),
            "trailing30_std": round(variance ** 0.5, 4),
            "exceed_last7": exceed_last7,
            "days_since_exceedance": days_since,
            "day_of_year": day.timetuple().tm_yday,
            "threshold_rank": threshold_rank,
            "observed_max_ft": point["max_ft"],
            "label_date": (day + timedelta(days=1)).isoformat(),
        })
    return rows


def build(out_dir, limit=None, years=None, concurrency=4, max_errors=0):
    stations = frozen_stations()
    order = sorted(stations)
    meta = station_metadata(stations)
    thresholds = sorted(entry["threshold_ft"] for entry in meta.values())
    rows_by_station = {}
    station_days = {}
    quality = {}
    requests = 0
    errors = []
    targets = stations[:limit] if limit else stations
    for station_id in targets:
        info = meta.get(station_id)
        if not info:
            errors.append({"station": station_id, "error": "no published numeric nos_minor"})
            continue
        series = []
        flood = set()
        # A few station-years in flight at once: 4,880 requests serial is over an hour and a half,
        # and this stays a modest, polite rate against a public API.
        def one_year(year):
            return year, daily_maxima(station_id, year), flood_days(station_id, year)

        station_years = list(years or YEARS)
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
            fetched = list(pool.map(lambda year: _safe_year(one_year, year, station_id, errors),
                                    station_years))
        for year, maxima, flags in fetched:
            if maxima is None:
                continue
            requests += 2
            flood |= flags
            for day, value in sorted(maxima.items()):
                # Incomplete days are kept and counted. Dropping them would quietly delete positive
                # days, so the count is reported instead and the sensitivity is measured separately.
                series.append({"station_id": station_id, "station_name": info["name"], "date": day,
                               "max_ft": value["max_ft"], "longitude": info["longitude"],
                               "complete_pct": value["complete_pct"], "flag": value["flag"]})
        series.sort(key=lambda point: point["date"])
        incomplete = [point for point in series
                      if point["complete_pct"] is not None and point["complete_pct"] < 100]
        flagged = [point for point in series if point["flag"] not in ("", "0")]
        quality.setdefault(station_id, {"days": len(series), "incomplete_days": len(incomplete),
                                        "incomplete_above_threshold":
                                            sum(1 for point in incomplete
                                                if point["max_ft"] > info["threshold_ft"]),
                                        "flagged_days": len(flagged)})
        rank = (thresholds.index(info["threshold_ft"]) + 1) / len(thresholds)
        for row in features_for(series, info["threshold_ft"], info["latitude"], round(rank, 5)):
            rows_by_station.setdefault(station_id, []).append(row)
        # The publisher's flood days for this station, kept beside its rows for the labelling step.
        station_days.setdefault(station_id, set()).update(flood)
        print(f"  {station_id} {info['name'][:28]:28} {len(series):5} days", flush=True)

    # Attach the next-day label from the same station's series, then split.
    labelled = []
    for station_id, rows in rows_by_station.items():
        flags = station_days.get(station_id, set())
        for row in rows:
            # The label is the publisher's flag for the *next* local day. A row whose next day is
            # outside the fetched window is dropped rather than labelled from nothing.
            if not (row["label_date"][:4].isdigit() and int(row["label_date"][:4]) in YEARS):
                continue
            row = dict(row)
            row["minor_flood"] = 1 if row["label_date"] in flags else 0
            row.pop("label_date")
            labelled.append(row)

    levels = {}
    temporal = {"train": [], "eval": [], "holdout": []}
    station_disjoint = {"train": [], "eval": [], "holdout": []}
    for row in labelled:
        year = int(row["date"][:4])
        group = group_of(row["station_id"], order)
        if TRAIN_YEARS[0] <= year <= TRAIN_YEARS[1]:
            temporal["train"].append(row)
            if group != 0:
                station_disjoint["train"].append(row)
        elif EVAL_YEARS[0] <= year <= EVAL_YEARS[1]:
            temporal["eval"].append(row)
            if group == 0:
                station_disjoint["eval"].append(row)
        elif HOLDOUT_YEARS[0] <= year <= HOLDOUT_YEARS[1]:
            temporal["holdout"].append(row)
            if group == 0:
                station_disjoint["holdout"].append(row)
    levels["temporal"] = temporal
    levels["station_disjoint"] = station_disjoint

    out_dir.mkdir(parents=True, exist_ok=True)
    emitted = emit_levels(out_dir, levels, meta, order, station_days)
    expected_station_years = len(targets) * len(years or YEARS)
    coverage = {
        "stations_expected": len(targets),
        "stations_built": len(rows_by_station),
        "station_years_expected": expected_station_years,
        "station_years_fetched": expected_station_years - len(errors),
        "missing_station_years": len(errors),
        "note": "an incomplete panel must not be scored as if it were the frozen panel",
    }
    summary = {"stations": len(rows_by_station), "requests": requests, "errors": errors,
               "coverage": coverage,
               "emitted_levels": emitted,
               "label_source": "NOAA HTF daily product, minFlag (the publisher's own minor-flood "
                               "days), one request per station-year; features come from "
                               "daily_max_min observations",
               "requests_per_station_year": 2,
               "levels": {}, "features": FEATURES, "columns": COLUMNS,
               "day_quality": {
                   "days": sum(v["days"] for v in quality.values()),
                   "incomplete_days": sum(v["incomplete_days"] for v in quality.values()),
                   "incomplete_days_above_threshold":
                       sum(v["incomplete_above_threshold"] for v in quality.values()),
                   "flagged_days": sum(v["flagged_days"] for v in quality.values()),
                   "rule": "incomplete days are kept; the label uses the reported maximum. The "
                           "counts are reported so the choice is visible rather than silent."}}
    summary["levels"] = {}
    for level, splits in levels.items():
        summary["levels"][level] = {}
        for split, rows in splits.items():
            positives = sum(row["minor_flood"] for row in rows)
            summary["levels"][level][split] = {
                "rows": len(rows), "positives": positives,
                "rate": round(positives / len(rows), 5) if rows else None,
                "stations": len({row["station_id"] for row in rows}),
            }
    (out_dir / "build_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary["levels"], indent=2))
    print(json.dumps({"coverage": coverage}, indent=2))

    # A run that lost station-years is incomplete, and an incomplete artifact must not pass silently
    # as if it were the frozen panel: the gate checks leaks, timing, splits and units, not coverage.
    if len(errors) > max_errors:
        print(f"INCOMPLETE: {len(errors)} station-years failed, {len(rows_by_station)} of "
              f"{len(targets)} stations built (limit {max_errors})", file=sys.stderr)
        return 1
    return 0



LEVEL_NOTES = {
    "temporal": "All 122 frozen stations; disjoint windows in time.",
    "station_disjoint": "Evaluation on stations that training never sees (group0 by station-id "
                        "order), so this level measures transfer rather than recall of a station's "
                        "own behaviour.",
}
PREDICTION_TIME = ("At the end of the previous local day. Every feature is a trailing summary of "
                   "that station's own observed daily maxima up to and including the previous day; "
                   "no feature uses the label day or later, and NOAA tide predictions and model "
                   "guidance are excluded because they are not observations.")
# The gate requires a known-event fixture when the label rests on an external threshold. This is
# Boston's documented record: the 2018-01-04 bomb-cyclone tide, which is also the datum regression
# test - under MLLW it would deny flooding during the record storm.
KNOWN_EVENT = {"name": "Boston 2018-01-04 bomb-cyclone tide (the documented record tide)",
               "expected_verdict": "exceeds",
               "source": "NOAA CO-OPS observations, datum=STND; the same event is the candidate's "
                         "datum regression test (candidates/noaa-tide-flooding/datum_regression.json)",
               "station": "8443970", "station_name": "Boston, MA", "date": "2018-01-04",
               "threshold_ft_stnd": 15.85, "observed_max_ft_stnd": 18.547}


def emit_levels(out_dir, levels, meta_by_station, order, counts_by_station):
    """Write each level in the runner's layout, with the descriptors qualification checks."""
    import json as _json

    written = {}
    for level, splits in levels.items():
        level_dir = out_dir / level
        (level_dir / "public").mkdir(parents=True, exist_ok=True)
        (level_dir / "private").mkdir(parents=True, exist_ok=True)
        paths = {"train": "public/train.csv", "eval": "public/eval.csv",
                 "holdout": "private/holdout.csv"}
        # The gate requires per-split start/end objects and recomputes them against the rows.
        # Half-open: the gate requires every row to fall strictly before the declared end.
        windows = {
            "train": {"start": f"{TRAIN_YEARS[0]}-01-01", "end": f"{TRAIN_YEARS[1] + 1}-01-01"},
            "eval": {"start": f"{EVAL_YEARS[0]}-01-01", "end": f"{EVAL_YEARS[1] + 1}-01-01"},
            "holdout": {"start": f"{HOLDOUT_YEARS[0]}-01-01",
                        "end": f"{HOLDOUT_YEARS[1] + 1}-01-01"},
        }
        rows_total = 0
        positives_total = 0
        stations = set()
        for split, rows in splits.items():
            rows.sort(key=lambda row: (row["station_id"], row["date"]))
            path = level_dir / paths[split]
            with path.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=COLUMNS)
                writer.writeheader()
                writer.writerows(rows)
            rows_total += len(rows)
            positives_total += sum(row["minor_flood"] for row in rows)
            stations |= {row["station_id"] for row in rows}
        # meta.json is the runner's task descriptor: `rows` and `positive_rate` are per split, and
        # `columns` must match the header order exactly, because the gate compares them.
        meta = {"target": "minor_flood", "positive_label": 1, "id_columns": ID_COLUMNS,
                "columns": COLUMNS,
                "rows": {split: len(rows) for split, rows in splits.items()},
                "positive_rate": {split: (round(sum(row["minor_flood"] for row in rows) / len(rows), 6)
                                           if rows else None)
                                  for split, rows in splits.items()},
                "level": level, "note": LEVEL_NOTES[level]}
        (level_dir / "meta.json").write_text(_json.dumps(meta, indent=2) + "\n")

        # Clustered event counts: rows sharing a flood day are one event, so the count is what a
        # score's uncertainty is quoted against.
        # The gate recounts both of these from the rows, so they are computed the same way it does:
        # positives are positive rows; distinct events are the distinct event-key dates among them.
        events = {}
        for split, rows in splits.items():
            positive_rows = [row for row in rows if row["minor_flood"]]
            events[split] = {"positives": len(positive_rows),
                             "distinct_events": len({row["date"] for row in positive_rows})}
        quality = {
            "target": "minor_flood",
            "positive_label": 1,
            "features": FEATURES,
            "carry_columns": ["station_id", "station_name", "latitude", "longitude",
                              "threshold_ft", "observed_max_ft"],
            "id_columns": ID_COLUMNS,
            "high_cardinality_columns": [],
            "label_source_columns": [],
            "post_hoc_columns": [],
            "splits": paths,
            "split_windows": windows,
            "time_column": "date",
            "event_key_column": "date",
            "positive_events": events,
            "id_columns_are_entity_keys": False,
            "expected_duplicate_ids": None,
            "external_threshold": True,
            "known_event": KNOWN_EVENT,
            "task": {"prediction_time": PREDICTION_TIME,
                     "target": "will this station's daily maximum observed water level exceed its "
                               "published NOS minor flood threshold tomorrow",
                     "label_source": "NOAA HTF daily product, minFlag (the publisher's own "
                                     "minor-flood days)"},
            "features_documented_at": "prediction_time",
            # Every measured column declares its unit and reference frame. The frame is the
            # station datum, which is the trap that cost this candidate a whole measurement pass:
            # the published threshold is in STND, and an MLLW series denies flooding during
            # Boston's record tide.
            "measurements": [
                {"column": "observed_max_ft", "unit": "feet",
                 "frame": "STND (the station's own datum, as requested from CO-OPS)"},
                {"column": "threshold_ft", "unit": "feet",
                 "frame": "STND, NOAA's published nos_minor threshold for that station"},
                {"column": "margin_ft", "unit": "feet",
                 "frame": "STND, previous day's maximum minus that station's threshold"},
                {"column": "trailing7_mean", "unit": "feet", "frame": "STND, trailing 7 days"},
                {"column": "trailing30_mean", "unit": "feet", "frame": "STND, trailing 30 days"},
                {"column": "trailing30_std", "unit": "feet", "frame": "STND, trailing 30 days"},
            ],
            "evidence": [
                {"what": "label route compared against NOAA's own annual counts, 2024",
                 "result": "NOAA htf_daily flags match exactly (25/26/23/20 = 94 over four "
                           "stations); a 6-minute reconstruction gave 113-114 and hourly 98",
                 "path": "candidates/noaa-tide-flooding/label_route_result.json"},
                {"what": "station-disjoint capacity",
                 "result": "group0 (held-out stations) carries 1,090 positive station-days over "
                           "337 distinct flood days in the holdout window",
                 "path": "candidates/noaa-tide-flooding/spatial_split_result.json"},
            ],
        }
        (level_dir / "quality.json").write_text(_json.dumps(quality, indent=2) + "\n")
        written[level] = {"rows": rows_total, "positives": positives_total,
                          "stations": len(stations), "dir": str(level_dir)}
    return written


def probe(station_id, year):
    info = station_metadata([station_id]).get(str(station_id))
    if not info:
        sys.exit(f"no published nos_minor for {station_id}")
    maxima = daily_maxima(station_id, year)
    print(f"{station_id} {info['name']}: {len(maxima)} days returned for {year}, "
          f"threshold {info['threshold_ft']} ft STND, lat {info['latitude']}")
    days = sorted(maxima.items())
    print("  first:", days[0], "last:", days[-1])
    above = [day for day, value in days if value["max_ft"] > info["threshold_ft"]]
    print(f"  days above the minor threshold: {len(above)} {above[:6]}")
    series = [{"station_id": str(station_id), "station_name": info["name"], "date": day,
               "max_ft": value["max_ft"], "longitude": info["longitude"]} for day, value in days]
    rows = features_for(series, info["threshold_ft"], info["latitude"], 0.5)
    print(f"  feature rows from one station-year: {len(rows)}")
    if rows:
        print("  sample:", json.dumps(rows[-1], indent=None)[:400])
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--limit", type=int, help="first N frozen stations, for a bounded run")
    parser.add_argument("--probe", help="one station id: fetch one year and print parsed rows")
    parser.add_argument("--year", type=int, default=2024, help="year for --probe")
    parser.add_argument("--years", help="comma-separated years, e.g. 2024,2025")
    parser.add_argument("--max-errors", type=int, default=0,
                        help="station-years allowed to fail before the build reports INCOMPLETE")
    parser.add_argument("--concurrency", type=int, default=4,
                        help="station-years in flight at once (default 4; modest on purpose)")
    args = parser.parse_args()
    if args.probe:
        return probe(args.probe, args.year)
    if not args.out:
        raise SystemExit("--out is required for a build (or use --probe)")
    years = [int(y) for y in args.years.split(",")] if args.years else None
    return build(args.out, limit=args.limit, years=years, concurrency=args.concurrency,
                 max_errors=args.max_errors)


if __name__ == "__main__":
    raise SystemExit(main())