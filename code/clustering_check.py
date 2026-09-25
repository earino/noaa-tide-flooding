#!/usr/bin/env python3
"""How independent are those positive station-days?

A count of 256 positive station-days does not buy the same statistical power as 256
independent events, because a single storm day floods several stations at once. This
counts, per year, both the positive station-days and the distinct calendar days carrying
at least one flood, so the clustering is measured rather than assumed.
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

UA = {"User-Agent": "scout-dataset-factory/0.1 (bounded research probe)"}
BASE = "https://api.tidesandcurrents.noaa.gov/dpapi/prod/webapi"

STATIONS = [
    ("8418150", "Portland, ME"),
    ("8443970", "Boston, MA"),
    ("8518750", "The Battery, NY"),
    ("8531680", "Sandy Hook, NJ"),
    ("8534720", "Atlantic City, NJ"),
    ("8638610", "Sewells Point, VA"),
    ("8665530", "Charleston, SC"),
    ("8724580", "Key West, FL"),
    ("8771450", "Galveston Pier 21, TX"),
    ("9414290", "San Francisco, CA"),
    ("9447130", "Seattle, WA"),
    ("1612340", "Honolulu, HI"),
]

WINDOWS = [("eval", 2022, 2023), ("holdout", 2024, 2025)]


def get(url, attempts=3):
    last = None
    for i in range(attempts):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:120]}"
        except Exception as e:  # noqa: BLE001
            last = repr(e)
    raise RuntimeError(last)


def main():
    per_year_days = defaultdict(lambda: defaultdict(set))  # year -> day -> {station}
    positive_station_days = defaultdict(int)
    per_year_pos = defaultdict(int)

    print("Counting positive station-days and distinct flood days")
    for sid, name in STATIONS:
        for label, y0, y1 in WINDOWS:
            for year in (y0, y1):
                data = get(f"{BASE}/htf/htf_daily.json?"
                           + urllib.parse.urlencode({"station": sid,
                                                     "start_date": f"{year}0101",
                                                     "end_date": f"{year}1231"}))
                for rec in data.get("DailyFloodCount") or []:
                    if str(rec.get("minFlag")) not in ("1", "1.0"):
                        continue
                    raw = str(rec.get("day") or "")
                    if "/" in raw:
                        mm, dd, yyyy = raw.split("/")
                        raw = f"{yyyy}-{mm}-{dd}"
                    per_year_days[year][raw[:10]].add(name)
                    per_year_pos[year] += 1
        print(f"  {name:<24} done")

    print()
    print(f"{'year':<6} {'positive station-days':>21} {'distinct flood days':>20} "
          f"{'mean stations/day':>18}")
    print("-" * 70)
    out_years = []
    for year in sorted(per_year_days):
        days = per_year_days[year]
        distinct = len(days)
        pos = per_year_pos[year]
        mean_st = (pos / distinct) if distinct else 0.0
        print(f"{year:<6} {pos:>21} {distinct:>20} {mean_st:>18.2f}")
        out_years.append({"year": year, "positive_station_days": pos,
                          "distinct_flood_days": distinct,
                          "mean_flooding_stations_per_flood_day": round(mean_st, 3)})

    print()
    for label, y0, y1 in WINDOWS:
        pos = sum(per_year_pos[y] for y in (y0, y1))
        days = set()
        for y in (y0, y1):
            days |= set(per_year_days[y])
        print(f"{label} {y0}-{y1}: {pos} positive station-days spread over "
              f"{len(days)} distinct calendar days "
              f"({pos / len(days) if days else 0:.2f} stations per flood day)")

    out = Path(__file__).with_name("clustering_result.json")
    out.write_text(json.dumps({
        "question": "How temporally clustered are the positive events in each split?",
        "station_set": [n for _, n in STATIONS],
        "years": out_years,
        "measured_on": "2026-09-18",
    }, indent=1) + "\n")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
