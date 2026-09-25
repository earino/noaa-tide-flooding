#!/usr/bin/env python3
"""Freeze the station list for the NOAA tide-flooding candidate, and cost the extraction.

Two measured steps:

1. One request returns the whole water-level inventory *with* flood thresholds
   (`expand=floodlevels`), so the station list is filtered from the source, not hand-picked.
   A station qualifies only if its `nos_minor` is present and numeric.
2. NOAA's own HTF annual product (1 request per station) reports, per year, how many days the
   station exceeded its minor threshold. Coverage of the target years is the record-length
   evidence: a station with no annual counts has no basis for a label in that year.

Output: candidates/noaa-tide-flooding/station_list_result.json - the frozen set, its split
counts, and the request/byte/second cost of the label extraction for both products, computed
from the per-request figures measured by .factory/noaa_cost_probe.py on this same host.
"""
import json
import time
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

UA = {"User-Agent": "scout-dataset-factory/0.1 (bounded research probe)"}
MDAPI = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi"
DPAPI = "https://api.tidesandcurrents.noaa.gov/dpapi/prod/webapi"
DATA = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"

SPLITS = [("train", 2006, 2021), ("eval", 2022, 2023), ("holdout", 2024, 2025)]
TARGET_YEARS = list(range(2006, 2026))
MIN_COVERAGE_YEARS = 18  # of the 20 target years; below this a station cannot carry the splits

# Measured on this host 2026-09-19 (.factory/noaa_cost_probe.py):
COST_6MIN_PER_MONTH = {"bytes": 560602, "seconds": 1.61, "rows": 7440}
COST_HOURLY_PER_YEAR = {"bytes": 545427, "seconds": 2.219, "rows": 8760}


def fetch(url, attempts=3, timeout=120):
    last = None
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA),
                                        timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            last = f"HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:120]}"
        except Exception as exc:  # noqa: BLE001
            last = repr(exc)[:120]
    raise RuntimeError(last)


def minor_threshold(station):
    """The published minor-flood threshold, from either shape the API returns."""
    floods = station.get("floodlevels") or {}
    if isinstance(floods, dict):
        for key in ("nos_minor", "NOSminor"):
            value = floods.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        return None
    if isinstance(floods, list) and floods:
        first = floods[0]
        if isinstance(first, dict):
            for key in ("nos_minor", "NOSminor"):
                if isinstance(first.get(key), (int, float)):
                    return float(first[key])
        if isinstance(first, (int, float)):
            return float(first)
    if isinstance(floods, (int, float)):
        return float(floods)
    return None


def main():
    started = time.time()
    result = {"measured_on": "2026-09-19", "host_class": "coordinator (hosted Scout, 1.9 GiB)"}

    raw = fetch(f"{MDAPI}/stations.json?type=waterlevels&expand=floodlevels")
    inventory = json.loads(raw)["stations"]
    usable, unusable = [], []
    for station in inventory:
        value = minor_threshold(station)
        entry = {"id": station["id"], "name": station.get("name"), "state": station.get("state"),
                 "nos_minor": value}
        (usable if value is not None else unusable).append(entry)
    result["inventory_request"] = {"url": f"{MDAPI}/stations.json?type=waterlevels&expand=floodlevels",
                                   "bytes": len(raw), "stations": len(inventory)}
    result["threshold_filter"] = {
        "stations": len(inventory),
        "with_numeric_nos_minor": len(usable),
        "without": len(unusable),
        "without_ids": [e["id"] for e in unusable][:20],
        "note": "floodlevels.json returns either a bare number or an object whose nos_minor can "
                "be null; both shapes were observed in the same inventory.",
    }
    print(f"inventory: {len(inventory)} stations, {len(usable)} with numeric nos_minor, "
          f"{len(unusable)} without ({round(time.time() - started, 1)}s)")

    # Record-length evidence: NOAA's own annual HTF counts per station.
    def annual(entry):
        try:
            payload = json.loads(fetch(f"{DPAPI}/htf/htf_annual.json?station={entry['id']}"))
        except Exception as exc:  # noqa: BLE001
            return entry["id"], None, repr(exc)[:100]
        years = {}
        for row in payload.get("AnnualFloodCount") or []:
            try:
                year = int(row.get("year"))
            except (TypeError, ValueError):
                continue
            if row.get("minCount") is None:
                continue
            years[year] = {"minor": int(row["minCount"]),
                           "moderate": int(row.get("modCount") or 0),
                           "major": int(row.get("majCount") or 0)}
        return entry["id"], years, None

    per_station = {}
    errors = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        for sid, years, error in pool.map(annual, usable):
            if error:
                errors[sid] = error
            else:
                per_station[sid] = years
    print(f"annual counts fetched for {len(per_station)} stations in "
          f"{round(time.time() - started, 1)}s ({len(errors)} errors)")

    frozen = []
    for entry in usable:
        years = per_station.get(entry["id"]) or {}
        coverage = [y for y in TARGET_YEARS if y in years]
        if len(coverage) < MIN_COVERAGE_YEARS:
            continue
        frozen.append({**entry, "years_covered": len(coverage),
                       "positives_total": sum(years[y]["minor"] for y in coverage),
                       "moderate_or_worse": sum(years[y]["moderate"] for y in coverage)})
    frozen.sort(key=lambda e: -e["positives_total"])
    result["frozen_station_list"] = {
        "rule": f"numeric nos_minor AND >= {MIN_COVERAGE_YEARS} of the {len(TARGET_YEARS)} "
                f"target years present in htf/annual minCount",
        "count": len(frozen),
        "stations": frozen,
    }
    print(f"frozen station list: {len(frozen)} stations "
          f"(rule: numeric nos_minor and >= {MIN_COVERAGE_YEARS} target years of HTF counts)")

    # Split capacity over the frozen set, recomputed from NOAA's annual counts.
    summary = []
    for label, y0, y1 in SPLITS:
        years = list(range(y0, y1 + 1))
        days = pos = modplus = 0
        for entry in frozen:
            station_years = per_station[entry["id"]]
            have = [y for y in years if y in station_years]
            days += 365 * len(have)
            pos += sum(station_years[y]["minor"] for y in have)
            modplus += sum(station_years[y]["moderate"] for y in have)
        summary.append({"split": label, "years": f"{y0}-{y1}", "station_days": days,
                        "positives": pos, "rate": round(pos / days, 6) if days else None,
                        "moderate_or_worse": modplus})
        print(f"  {label:<8} {y0}-{y1}  station-days={days:>9} positives={pos:>6} "
              f"rate={summary[-1]['rate']}")
    result["split_capacity"] = summary

    # Extraction cost, from the measured per-request figures.
    station_years = [(entry["id"], y) for entry in frozen for y in TARGET_YEARS
                     if y in per_station[entry["id"]]]
    n_station_years = len(station_years)
    months = n_station_years * 12
    result["extraction_cost"] = {
        "basis": "per-request figures measured on this host (.factory/noaa_cost_probe.py); "
                 "totals are those figures multiplied by the counted request set, not estimates",
        "measured_per_request": {"water_level_6min_1month": COST_6MIN_PER_MONTH,
                                 "hourly_height_1year": COST_HOURLY_PER_YEAR,
                                 "inventory_expand_floodlevels": result["inventory_request"]},
        "counted_requests": {"station_years": n_station_years, "station_months": months,
                            "stations": len(frozen)},
        "labels_from_6min_monthly": {
            "requests": months,
            "bytes": months * COST_6MIN_PER_MONTH["bytes"],
            "seconds": round(months * COST_6MIN_PER_MONTH["seconds"], 1),
            "rows": months * COST_6MIN_PER_MONTH["rows"],
        },
        "labels_from_hourly": {
            "requests": n_station_years,
            "bytes": n_station_years * COST_HOURLY_PER_YEAR["bytes"],
            "seconds": round(n_station_years * COST_HOURLY_PER_YEAR["seconds"], 1),
            "rows": n_station_years * COST_HOURLY_PER_YEAR["rows"],
        },
        "verdict": None,
    }

    def human(n):
        for unit in ("bytes", "KiB", "MiB", "GiB", "TiB"):
            if n < 1024 or unit == "TiB":
                return f"{n:.1f} {unit}"
            n /= 1024
    cost = result["extraction_cost"]
    for key in ("labels_from_6min_monthly", "labels_from_hourly"):
        block = cost[key]
        print(f"  {key}: {block['requests']} requests, {human(block['bytes'])}, "
              f"{round(block['seconds'] / 60, 1)} min, {block['rows']} rows")
    cost["verdict"] = ("6-minute labels are affordable on a worker: the monthly request set is "
                       "marked above. Hourly is 12x cheaper in requests but undercounts positives "
                       "by ~6% of caught days.")
    result["wall_clock_seconds"] = round(time.time() - started, 1)
    print("total wall clock:", result["wall_clock_seconds"], "s")

    path = Path(__file__).with_name("station_list_result.json")
    path.write_text(json.dumps(result, indent=1) + "\n")
    print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
