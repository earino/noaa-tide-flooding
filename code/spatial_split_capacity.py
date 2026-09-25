#!/usr/bin/env python3
"""Can a station-disjoint split carry a score?

The candidate's splits so far are temporal. The contribution that makes this dataset *not* a mirror
of NOAA's own products is a **station-disjoint** evaluation: train on some stations, evaluate on
stations the model has never seen, so an agent has to learn something transferable instead of
remembering one station's local tidal behaviour.

That only works if the held-out stations contain enough positives. This measures it from NOAA's own
annual product, which returns every station-year in one request:

    https://api.tidesandcurrents.noaa.gov/dpapi/prod/webapi/htf/htf_annual.json

Nothing is inferred: `minCount` is NOAA's count of minor-flood days for that station-year, the same
field the candidate's temporal capacity was validated against.

  python3 spatial_split_capacity.py            # fetch, measure, write spatial_split_result.json
  python3 spatial_split_capacity.py --cached   # reuse the extracted copy instead of re-fetching
"""

import argparse
import json
import urllib.request
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ANNUAL_URL = "https://api.tidesandcurrents.noaa.gov/dpapi/prod/webapi/htf/htf_annual.json"
EXTRACT = HERE / "annual_counts_extract.json"
RESULT = HERE / "spatial_split_result.json"
YEARS = list(range(2006, 2026))
PERIODS = {"train": range(2006, 2022), "eval": range(2022, 2024), "holdout": range(2024, 2026)}


def frozen_stations():
    data = json.loads((HERE / "station_list_result.json").read_text())
    return data["frozen_station_list"]["stations"]


def extract_counts(stations, cached):
    """Only the 122 frozen stations and the 20 target years, so this stays a compact artifact."""
    if cached:
        return json.loads(EXTRACT.read_text())
    wanted = {str(station["id"]) for station in stations}
    request = urllib.request.Request(ANNUAL_URL, headers={"User-Agent": "dataset-factory"})
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = json.loads(response.read())
    rows = {}
    meta = {}
    for record in payload["AnnualFloodCount"]:
        station_id = str(record.get("stnId"))
        year = record.get("year")
        if station_id not in wanted or year not in YEARS:
            continue
        rows.setdefault(station_id, {})[str(year)] = record.get("minCount")
        meta[station_id] = {"name": record.get("stnName"),
                            "lat": float(record["lat"]) if record.get("lat") else None,
                            "lon": float(record["lon"]) if record.get("lon") else None}
    stored = {"source": ANNUAL_URL, "field": "minCount (minor flood days)",
              "years": YEARS, "counts": rows, "meta": meta}
    EXTRACT.write_text(json.dumps(stored, indent=1, sort_keys=True) + "\n")
    return stored


def periods_for(counts):
    """Positives per period, counting missing station-years as zero rather than dropping them."""
    totals = {}
    for name, years in PERIODS.items():
        positives = 0
        station_days = 0
        stations_with_positives = 0
        for rows in counts.values():
            here = sum(rows.get(str(year)) or 0 for year in years)
            positives += here
            station_days += len(years) * 365
            stations_with_positives += 1 if here else 0
        totals[name] = {"positives": positives, "station_days": station_days,
                        "rate": round(positives / station_days, 5),
                        "stations_with_positives": stations_with_positives}
    return totals


def partition(stations, meta, rule):
    if rule == "id-round-robin":
        ordered = sorted(stations, key=lambda s: str(s["id"]))
    elif rule == "latitude-round-robin":
        ordered = sorted(stations, key=lambda s: meta.get(str(s["id"]), {}).get("lat") or 0)
    else:
        raise SystemExit(f"unknown rule {rule}")
    groups = defaultdict(list)
    for index, station in enumerate(ordered):
        groups[index % 3].append(station)
    return groups, ordered


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cached", action="store_true")
    args = parser.parse_args()

    stations = frozen_stations()
    stored = extract_counts(stations, args.cached)
    meta, counts = stored["meta"], stored["counts"]
    all_stations = {str(s["id"]): s for s in stations}

    result = {"question": "Does a station-disjoint split contain enough positives to score?",
              "source": ANNUAL_URL, "field": stored["field"],
              "frozen_stations": len(stations), "years": [YEARS[0], YEARS[-1]],
              "periods": {name: list(years) for name, years in PERIODS.items()},
              "partitions": {}}

    for rule in ("id-round-robin", "latitude-round-robin"):
        groups, ordered = partition(stations, meta, rule)
        entry = {}
        for index, members in sorted(groups.items()):
            ids = [str(s["id"]) for s in members]
            subset = {i: counts.get(i, {}) for i in ids}
            latitudes = [meta.get(i, {}).get("lat") for i in ids if meta.get(i, {}).get("lat")]
            entry[f"group{index}"] = {
                "stations": len(members),
                "latitude_range": [round(min(latitudes), 2), round(max(latitudes), 2)] if latitudes else None,
                "totals_by_period": periods_for(subset),
            }
        result["partitions"][rule] = entry

    # The spread matters: if every station behaved the same, a held-out station would be trivial.
    rates = []
    for station in stations:
        rows = counts.get(str(station["id"]), {})
        positives = sum(rows.get(str(y)) or 0 for y in YEARS)
        rates.append(positives / (len(YEARS) * 365))
    rates.sort()
    result["per_station_rate_spread"] = {
        "min": round(rates[0], 5), "p25": round(rates[len(rates) // 4], 5),
        "median": round(rates[len(rates) // 2], 5), "p75": round(rates[3 * len(rates) // 4], 5),
        "max": round(rates[-1], 5),
        "zero_positive_stations": sum(1 for r in rates if r == 0),
        "note": "a station-disjoint split is only informative if stations differ this much",
    }
    result["clustering"] = ("distinct flood days per group is NOT measured here: the annual product "
                            "returns counts, not dates. Measure it from htf/daily.json for the "
                            "chosen held-out stations before quoting an event count - the temporal "
                            "splits cluster about 5.5-6.7 stations per flood day.")
    RESULT.write_text(json.dumps(result, indent=2) + "\n")

    print(json.dumps({"wrote": str(RESULT.relative_to(HERE.parent.parent)),
                      "spread": result["per_station_rate_spread"],
                      "id_round_robin": {g: {p: t["positives"]
                                             for p, t in v["totals_by_period"].items()}
                                         for g, v in result["partitions"]["id-round-robin"].items()},
                      "latitude_round_robin": {g: {p: t["positives"]
                                                   for p, t in v["totals_by_period"].items()}
                                               for g, v in result["partitions"]["latitude-round-robin"].items()}},
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())