#!/usr/bin/env python3
"""Cross-check the computed 2025 base rates against NOAA's own historical product.

NOAA's High Tide Flooding daily/annual products give the authoritative number of days
each station exceeded the minor threshold, with NOAA doing its own datum handling:

  * `htf/daily.json` reports `count` = the number of DAYS RETURNED, not flood days. Its
    `DailyFloodCount` list is the per-day detail. Reading `count` as a flood count makes
    every station look like it flooded 365 times, which is why the annual product is used
    for the comparison here.
  * `htf/annual.json` reports, per year, `minCount` / `modCount` / `majCount` - the
    authoritative flood-day counts at each threshold.

If the STND reconstruction is right, my per-station 2025 counts must equal NOAA's
`minCount`, and the rejected MLLW reconstruction must match nothing.
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = {"User-Agent": "scout-dataset-factory/0.1 (bounded research probe)"}
BASE = "https://api.tidesandcurrents.noaa.gov/dpapi/prod/webapi"
YEAR = 2025

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

# My own reconstruction for 2025 (candidates/noaa-tide-flooding/notes.md).
MINE_STND = {
    "8418150": 0, "8443970": 2, "8518750": 7, "8531680": 7, "8534720": 4,
    "8638610": 17, "8665530": 7, "8724580": 0, "8771450": 4, "9414290": 0,
    "9447130": 0, "1612340": 12,
}
# The rejected MLLW comparison produced zero at every station.
MINE_MLLW = {sid: 0 for sid, _ in STATIONS}


def get(url, attempts=3):
    last = None
    for i in range(attempts):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:120]}"
        except Exception as e:  # noqa: BLE001
            last = repr(e)
    raise RuntimeError(last)


def main():
    rows = []
    print(f"NOAA htf/annual vs my reconstruction, station-year {YEAR}")
    print()
    print(f"{'station':<24} {'id':<9} {'NOAA min':>8} {'mine STND':>10} {'match':>6} "
          f"{'mine MLLW':>10} {'NOAA mod':>8} {'NOAA maj':>8}")
    print("-" * 92)

    noaa_total = stnd_total = mllw_total = mismatches = 0
    for sid, name in STATIONS:
        ann = get(f"{BASE}/htf/htf_annual.json?station={sid}")
        entries = ann.get("AnnualFloodCount") or []
        year_rows = [e for e in entries if str(e.get("year")) == str(YEAR)]
        if not year_rows:
            print(f"{name:<24} {sid:<9} no {YEAR} entry")
            continue
        e = year_rows[0]
        noaa, mod, maj = int(e.get("minCount") or 0), int(e.get("modCount") or 0), int(e.get("majCount") or 0)
        mine_s, mine_m = MINE_STND[sid], MINE_MLLW[sid]
        noaa_total += noaa
        stnd_total += mine_s
        mllw_total += mine_m
        ok = noaa == mine_s
        mismatches += 0 if ok else 1
        print(f"{name:<24} {sid:<9} {noaa:>8} {mine_s:>10} {str(ok):>6} "
              f"{mine_m:>10} {mod:>8} {maj:>8}")
        rows.append({
            "station": name, "id": sid, "year": YEAR,
            "noaa_minor_flood_days": noaa, "noaa_moderate_flood_days": mod,
            "noaa_major_flood_days": maj,
            "mine_stnd_minor_flood_days": mine_s,
            "mine_mllw_minor_flood_days": mine_m,
            "stnd_matches_noaa": ok,
            "noaa_percent_completeness": e.get("percent_completeness"),
        })

    print("-" * 92)
    print(f"{'TOTAL':<24} {'':<9} {noaa_total:>8} {stnd_total:>10} "
          f"{str(noaa_total == stnd_total):>6} {mllw_total:>10}")
    print()
    print(f"stations compared      : {len(rows)}")
    print(f"station-row mismatches : {mismatches}")
    print(f"STND reconstruction    : {'VALIDATED' if mismatches == 0 else 'DISAGREES'}")
    print(f"MLLW reconstruction    : produced {mllw_total} flood days vs NOAA's {noaa_total}")

    out = Path(__file__).with_name("htf_crosscheck_result.json")
    out.write_text(json.dumps({
        "year": YEAR,
        "source": f"{BASE}/htf/annual.json (minCount/modCount/majCount)",
        "endpoint_note": "htf/daily.json 'count' is the number of days returned, not a flood count",
        "stations_compared": len(rows),
        "noaa_minor_flood_days_total": noaa_total,
        "mine_stnd_minor_flood_days_total": stnd_total,
        "mine_mllw_minor_flood_days_total": mllw_total,
        "station_row_mismatches": mismatches,
        "stnd_reconstruction_validated": mismatches == 0,
        "per_station": rows,
        "measured_on": "2026-09-18",
    }, indent=1) + "\n")
    print(f"\nwrote {out}")
    return 0 if mismatches == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
