#!/usr/bin/env python3
"""How many *independent* flood days does the station-disjoint holdout contain?

`spatial_split_capacity.py` measured positive station-days for a station-disjoint partition, but
flood days cluster: several stations flood on the same day. The number a score's uncertainty has to
be quoted against is therefore the distinct calendar days, not the station-days.

Measured for the held-out station group from NOAA's HTF daily product - the same product and the
same rule used for the temporal splits, so the two capacities are comparable:

    {DPAPI}/htf/htf_daily.json?station=<id>&start_date=<year>0101&end_date=<year>1231

One request per station-year, serial. Output goes into spatial_split_result.json.

  python3 spatial_clustering.py [--group 0] [--years eval,holdout]
"""

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
UA = {"User-Agent": "scout-dataset-factory/0.1 (bounded research probe)"}
DPAPI = "https://api.tidesandcurrents.noaa.gov/dpapi/prod/webapi"
RESULT = HERE / "spatial_split_result.json"
EXTRACT = HERE / "annual_counts_extract.json"
PERIOD_YEARS = {"train": range(2006, 2022), "eval": range(2022, 2024),
                "holdout": range(2024, 2026)}


def fetch(url, attempts=3, timeout=120):
    last = None
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA),
                                        timeout=timeout) as response:
                return response.read().decode()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            last = exc
    raise SystemExit(f"GET {url} failed after {attempts} attempts: {last}")


def flood_days(station_id, year):
    payload = json.loads(fetch(f"{DPAPI}/htf/htf_daily.json?station={station_id}"
                               f"&start_date={year}0101&end_date={year}1231"))
    out = set()
    for row in payload.get("DailyFloodCount") or []:
        if str(row.get("minFlag")) not in ("1", "1.0"):
            continue
        raw = str(row.get("day") or "")
        if "/" in raw:                      # the product answers M/D/YYYY
            month, day, year_part = raw.split("/")
            raw = f"{year_part}-{month}-{day}"
        out.add(raw[:10])
    return out


def group_members(group):
    """The same deterministic partition as spatial_split_capacity.py: station id order, index % 3."""
    stations = json.loads((HERE / "station_list_result.json").read_text())["frozen_station_list"]["stations"]
    ordered = sorted(stations, key=lambda station: str(station["id"]))
    return [str(station["id"]) for index, station in enumerate(ordered) if index % 3 == group]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", type=int, default=0)
    parser.add_argument("--years", default="holdout")
    args = parser.parse_args()

    members = group_members(args.group)
    counts = json.loads(EXTRACT.read_text())["counts"]
    result = json.loads(RESULT.read_text())

    measured = {}
    for period in args.years.split(","):
        days = {}
        errors = []
        for station_id in members:
            for year in PERIOD_YEARS[period]:
                if not counts.get(station_id, {}).get(str(year)):
                    continue                      # NOAA reports no count: nothing to cluster
                try:
                    for day in flood_days(station_id, year):
                        days.setdefault(day, set()).add(station_id)
                except SystemExit as exc:
                    errors.append(str(exc)[:120])
        sizes = sorted(len(v) for v in days.values())
        positives = sum(sizes)
        measured[period] = {
            "years": [min(PERIOD_YEARS[period]), max(PERIOD_YEARS[period])],
            "held_out_stations": len(members),
            "positive_station_days": positives,
            "distinct_flood_days": len(days),
            "mean_stations_per_flood_day": round(positives / len(days), 2) if days else None,
            "busiest_day_stations": sizes[-1] if sizes else 0,
            "stations_with_no_flood_day_in_window": sum(
                1 for station_id in members
                if not any(counts.get(station_id, {}).get(str(year))
                           for year in PERIOD_YEARS[period])),
            "errors": errors,
        }
        print(f"{period}: {positives} positive station-days over {len(days)} distinct flood days "
              f"(mean {measured[period]['mean_stations_per_flood_day']} stations/day)")

    result.setdefault("station_disjoint_clustering", {})[f"group{args.group}"] = measured
    result["station_disjoint_clustering"]["note"] = (
        "Independent-event counts for the station-disjoint split, measured from the HTF daily "
        "product exactly as the temporal splits were, so the two are comparable. A score on "
        "held-out stations is quoted against distinct_flood_days, not positive_station_days.")
    RESULT.write_text(json.dumps(result, indent=2) + "\n")
    print("wrote", RESULT.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())