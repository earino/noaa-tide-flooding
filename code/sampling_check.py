#!/usr/bin/env python3
"""Does hourly sampling miss brief exceedances?

The base rates above were computed from the hourly product, which is the only one that
allows long ranges. The 6-minute product resolves a tide cycle far better but is limited
to one month per request. For the stations and months with the most flood days, compare
the two sampling rates day by day and count days where the 6-minute maximum crosses the
threshold but the hourly maximum does not.
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

UA = {"User-Agent": "scout-dataset-factory/0.1 (bounded research probe)"}
APP = "scout-dataset-factory"
API = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
DPAPI = "https://api.tidesandcurrents.noaa.gov/dpapi/prod/webapi"
MDAPI = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi"
YEAR = 2025

STATIONS = [
    ("8638610", "Sewells Point, VA"),
    ("1612340", "Honolulu, HI"),
    ("8518750", "The Battery, NY"),
]


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


def levels(product, station, begin, end, datum="STND"):
    params = {
        "product": product, "application": APP, "begin_date": begin, "end_date": end,
        "datum": datum, "station": station, "time_zone": "gmt",
        "units": "english", "format": "json",
    }
    raw = get(API + "?" + urllib.parse.urlencode(params))
    out = []
    for r in raw.get("data", []):
        v = r.get("v")
        if v in (None, ""):
            continue
        out.append((r["t"], float(v)))
    return out, raw.get("error")


def daily_max(pairs):
    d: dict[str, float] = {}
    for t, v in pairs:
        day = t[:10]
        if day not in d or v > d[day]:
            d[day] = v
    return d


report = []
print(f"Hourly vs 6-minute sampling, station-year {YEAR}, datum=STND")
print()

for sid, name in STATIONS:
    fl = get(f"{MDAPI}/stations/{sid}/floodlevels.json")
    minor = fl.get("nos_minor")
    daily = get(f"{DPAPI}/htf/htf_daily.json?"
                + urllib.parse.urlencode({"station": sid, "start_date": f"{YEAR}0101",
                                          "end_date": f"{YEAR}1231"}))
    detail = daily.get("DailyFloodCount") or []
    flood_days = []

    def is_flood(rec):
        for key in ("minFlag", "minorFlood", "minor"):
            if key in rec:
                return str(rec[key]).strip().lower() in ("1", "true", "yes", "t")
        return False

    for rec in detail:
        if is_flood(rec):
            raw_day = str(rec.get("day") or rec.get("date") or "")
            # htf_daily reports MM/DD/YYYY.
            if "/" in raw_day:
                mm, dd, yyyy = raw_day.split("/")
                raw_day = f"{yyyy}-{mm}-{dd}"
            flood_days.append(raw_day[:10])

    by_month = defaultdict(int)
    for d in flood_days:
        if len(d) >= 7:
            by_month[d[:7]] += 1
    if not by_month:
        print(f"{name}: htf_daily returned {len(detail)} rows but no parseable flood days; "
              f"sample={json.dumps(detail[:1])[:200]}")
        continue

    month = max(by_month, key=by_month.get)
    y, m = month.split("-")
    last_day = 31 if m in ("01", "03", "05", "07", "08", "10", "12") else (30 if m != "02" else 28)
    begin, end = f"{y}{m}01", f"{y}{m}{last_day:02d}"

    h6, err6 = levels("water_level", sid, begin, end)
    h1, err1 = levels("hourly_height", sid, begin, end)
    d6, d1 = daily_max(h6), daily_max(h1)
    days = sorted(set(d6) | set(d1))

    missed = [d for d in days
              if d in d6 and d in d1 and d6[d] > minor >= d1[d]]
    both = [d for d in days if d in d6 and d in d1 and d6[d] > minor and d1[d] > minor]
    agree_under = [d for d in days if d in d6 and d in d1 and d6[d] <= minor and d1[d] <= minor]

    print(f"{name} ({sid}), nos_minor {minor} ft")
    print(f"  flood days in {YEAR} by month: {dict(sorted(by_month.items()))}")
    print(f"  busiest month: {month} -> fetching {begin}..{end}")
    print(f"  6-minute rows {len(h6)} (err {err6}), hourly rows {len(h1)} (err {err1})")
    print(f"  days compared            : {len(days)}")
    print(f"  both cross threshold     : {len(both)}")
    print(f"  MISSED by hourly         : {len(missed)} {missed}")
    print(f"  both under threshold     : {len(agree_under)}")
    worst = None
    for d in days:
        if d in d6 and d in d1:
            gap = d6[d] - d1[d]
            if worst is None or gap > worst[1]:
                worst = (d, gap, d6[d], d1[d])
    if worst:
        print(f"  largest 6min-minus-hourly daily-max gap: {worst[1]:.3f} ft on {worst[0]} "
              f"(6min {worst[2]:.3f}, hourly {worst[3]:.3f})")
    print()

    report.append({
        "station": name, "id": sid, "nos_minor_ft": minor, "year": YEAR,
        "flood_days_by_month": dict(sorted(by_month.items())),
        "month_examined": month, "days_compared": len(days),
        "days_crossing_in_both": len(both),
        "days_missed_by_hourly_sampling": len(missed),
        "missed_days": missed,
        "days_under_in_both": len(agree_under),
        "six_minute_rows": len(h6), "hourly_rows": len(h1),
        "largest_daily_max_gap_ft": round(worst[1], 3) if worst else None,
        "largest_gap_day": worst[0] if worst else None,
    })

out = Path(__file__).with_name("sampling_check_result.json")
out.write_text(json.dumps({
    "question": "Does hourly sampling miss brief threshold exceedances?",
    "method": "daily maximum from 6-minute water_level vs daily maximum from hourly_height, same month, same datum=STND",
    "measured_on": "2026-09-18",
    "stations": report,
}, indent=1) + "\n")
print(f"wrote {out}")
sys.exit(0)
