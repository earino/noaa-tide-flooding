#!/usr/bin/env python3
"""Which label route actually reproduces NOAA's own flood-day counts?

The candidate validated its reconstruction on 2025, where the 12 sampled stations had few positive
days in total (Boston: 2). Building on `daily_max_min` at `time_zone=GMT` gives Boston **32** days
above the minor threshold in 2024 while NOAA's own annual product reports **25** - so the routes
disagree on a year with real signal, and the disagreement has to be located before a 2,440-request
build is spent.

Three hypotheses, measured per station-year:

  A. time zone: a GMT calendar day is not the station's local day, so the high tide that decides a
     flood day can land on the neighbouring date.
  B. resolution: hourly sampling misses brief exceedances (the candidate measured ~6% undercount),
     so a 6-minute route should catch *more* days than an hourly one, not fewer.
  C. something else in the product (completeness, quality flags, datum handling).

    python3 label_route_check.py --year 2024 --stations 8443970,8518750
"""

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
API = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
HTF = "https://api.tidesandcurrents.noaa.gov/dpapi/prod/webapi"
UA = {"User-Agent": "scout-dataset-factory/0.1 (bounded research probe)"}
RESULT = HERE / "label_route_result.json"


def fetch(url, attempts=3, timeout=180):
    last = None
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA),
                                        timeout=timeout) as response:
                return json.loads(response.read().decode())
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            last = exc
    raise RuntimeError(f"GET {url} failed: {last}")


def threshold(station_id):
    payload = fetch(f"https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations.json"
                    f"?type=waterlevels&expand=floodlevels")
    for station in payload.get("stations") or []:
        if str(station.get("id")) == str(station_id):
            flood = station.get("floodlevels") or {}
            minor = flood.get("nos_minor")
            if isinstance(minor, dict):
                minor = minor.get("nos_minor")
            return float(minor), station.get("name")
    raise SystemExit(f"no numeric nos_minor for {station_id}")


def days_above(values_by_day, limit):
    return sorted(day for day, value in values_by_day.items() if value > limit)


def via_daily_max_min(station_id, year, time_zone):
    payload = fetch(f"{API}?begin_date={year}0101&end_date={year}1231&station={station_id}"
                    f"&product=daily_max_min&interval=6&datum=STND&time_zone={time_zone}"
                    f"&units=english&application=dataset-factory&format=json")
    block = (payload.get("data") or [{}])[0]
    out = {}
    for row in block.get("dailyMax6Min") or []:
        day, value = str(row.get("date6Min") or ""), row.get("value6Min")
        if len(day) == 8 and day.isdigit():
            day = f"{day[:4]}-{day[4:6]}-{day[6:]}"
        if value in (None, "", "null"):
            continue
        out[day] = float(value)
    return out


def via_hourly(station_id, year, time_zone):
    payload = fetch(f"{API}?begin_date={year}0101&end_date={year}1231&station={station_id}"
                    f"&product=hourly_height&datum=STND&time_zone={time_zone}&units=english"
                    f"&application=dataset-factory&format=json")
    out = {}
    for row in payload.get("data") or []:
        stamp, value = str(row.get("t") or ""), row.get("v")
        if value in (None, "", "null"):
            continue
        day = stamp.split()[0].split("T")[0]
        if len(day) == 8 and day.isdigit():
            day = f"{day[:4]}-{day[4:6]}-{day[6:]}"
        out[day] = max(out.get(day, -99.0), float(value))
    return out



def via_htf_daily(station_id, year):
    """NOAA's own flood days for the station-year, with `minFlag` marking a minor flood day."""
    payload = fetch(f"{HTF}/htf/htf_daily.json?station={station_id}"
                    f"&start_date={year}0101&end_date={year}1231")
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


def noaa_count(station_id, year):
    """NOAA's own count, read from the extract of the all-station annual product."""
    extract = json.loads((HERE / "annual_counts_extract.json").read_text())
    rows = extract.get("counts", {}).get(str(station_id), {})
    return rows.get(str(year)), None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--stations", default="8443970,8518750")
    args = parser.parse_args()

    result = {"year": args.year, "question": "which label route reproduces NOAA's own counts",
              "noaa_source": f"{HTF}/htf/annual.json (minCount)", "routes": {}, "per_station": {}}
    totals = {}
    for station_id in args.stations.split(","):
        station_id = station_id.strip()
        limit, name = threshold(station_id)
        annual, completeness = noaa_count(station_id, args.year)
        gmt = days_above(via_daily_max_min(station_id, args.year, "GMT"), limit)
        lst = days_above(via_daily_max_min(station_id, args.year, "LST"), limit)
        hourly = days_above(via_hourly(station_id, args.year, "LST"), limit)
        publisher = via_htf_daily(station_id, args.year)
        entry = {"name": name, "threshold_ft": limit, "noaa_minor_days": annual,
                 "noaa_percent_completeness": completeness,
                 "daily_max_min_gmt": len(gmt), "daily_max_min_lst": len(lst),
                 "hourly_lst": len(hourly), "htf_daily_flags": len(publisher),
                 "htf_daily_matches_noaa": len(publisher) == annual,
                 "gmt_only_days": sorted(set(gmt) - set(lst))[:8],
                 "lst_not_gmt_days": sorted(set(lst) - set(gmt))[:8],
                 "matches_noaa": {"daily_max_min_gmt": len(gmt) == annual,
                                  "daily_max_min_lst": len(lst) == annual,
                                  "hourly_lst": len(hourly) == annual}}
        result["per_station"][station_id] = entry
        for route, value in (("daily_max_min_gmt", len(gmt)), ("daily_max_min_lst", len(lst)),
                             ("hourly_lst", len(hourly)), ("htf_daily_flags", len(publisher))):
            totals[route] = totals.get(route, 0) + value
        print(f"{station_id} {name}: NOAA {annual} | 6-min GMT {len(gmt)} | 6-min LST {len(lst)} "
              f"| hourly LST {len(hourly)} | publisher flags {len(publisher)}")
    noaa_total = sum(v["noaa_minor_days"] or 0 for v in result["per_station"].values())
    result["totals"] = {"noaa": noaa_total, **totals}
    result["closest_route"] = min(totals, key=lambda key: abs(totals[key] - noaa_total))
    result["conclusion"] = (f"totals vs NOAA {noaa_total}: " +
                            ", ".join(f"{route} {value}" for route, value in sorted(totals.items())))
    RESULT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("\n" + result["conclusion"])
    print("closest route:", result["closest_route"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())