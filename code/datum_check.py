#!/usr/bin/env python3
"""Datum handling for NOAA CO-OPS water levels, with the Boston event as a regression.

Why this module exists
----------------------
The CO-OPS metadata API publishes NOS flood thresholds with **no datum field**. Comparing
`hourly_height&datum=MLLW` against `nos_minor` produces **zero exceedance at every
station**, which reads as "this task has no positive class" and is entirely an artefact.
The published thresholds are expressed in the **station datum (STND)**.

`REQUIRED_DATUM` below is the rule the rest of the project must use. `datum_regression.json`
records the evidence, and `tests/test_noaa_datum.py` turns it into an offline test, so the
bug cannot be reintroduced silently.

Running this module directly re-checks the recorded peaks against the live API:

    python3 candidates/noaa-tide-flooding/datum_check.py

It exits 0 when every recorded peak still matches within tolerance.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REQUIRED_DATUM = "STND"
REJECTED_DATUM = "MLLW"
APPLICATION = "scout-dataset-factory"
API = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
USER_AGENT = {"User-Agent": "scout-dataset-factory/0.1 (bounded research probe)"}
FIXTURE = Path(__file__).with_name("datum_regression.json")


def load_fixture(path: Path = FIXTURE) -> dict:
    return json.loads(Path(path).read_text())


def peak(observations) -> tuple[str, float] | None:
    """Return (timestamp, value) for the highest observation, or None if there are none."""
    best = None
    for row in observations:
        value = row.get("v")
        if value in (None, ""):
            continue
        value = float(value)
        if best is None or value > best[1]:
            best = (row["t"], value)
    return best


def exceeds(value: float, threshold: float) -> bool:
    return value > threshold


def classify(peak_value: float, threshold: float, tolerance: float = 0.0) -> str:
    """Classify a peak against a threshold, tolerating a small distance when asked."""
    if peak_value > threshold + tolerance:
        return "above"
    if peak_value < threshold - tolerance:
        return "below"
    return "within_tolerance"


def fetch_observations(station: str, begin: str, end: str, datum: str,
                       product: str = "hourly_height") -> list[dict]:
    params = {
        "product": product,
        "application": APPLICATION,
        "begin_date": begin,
        "end_date": end,
        "datum": datum,
        "station": station,
        "time_zone": "gmt",
        "units": "english",
        "format": "json",
    }
    url = API + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(urllib.request.Request(url, headers=USER_AGENT),
                                timeout=120) as response:
        payload = json.load(response)
    return payload.get("data", []) or []


def check_live(fixture: dict | None = None) -> int:
    fixture = fixture or load_fixture()
    station = fixture["station"]["id"]
    threshold = fixture["thresholds_ft"]["nos_minor"]
    tolerance = fixture.get("peak_tolerance_ft", 0.05)
    failures = []

    print(f"Boston datum regression - station {station}, nos_minor {threshold} ft")
    print(f"required datum: {REQUIRED_DATUM} (rejected: {REJECTED_DATUM})")
    print()

    for case in fixture["cases"]:
        begin, end = case["window"].split("..")
        begin = begin.replace("-", "")
        end = end.replace("-", "")
        print(f"{case['name']} ({case['window']}) - expected exceeds: "
              f"{case['expected_exceeds_nos_minor']}")
        for datum, recorded in case["datums"].items():
            try:
                rows = fetch_observations(station, begin, end, datum)
            except (urllib.error.URLError, TimeoutError) as exc:
                print(f"  {datum:5s} live fetch failed: {exc}")
                continue
            live = peak(rows)
            if live is None:
                print(f"  {datum:5s} live fetch returned no rows")
                continue
            time_live, value_live = live
            delta = abs(value_live - recorded["peak_ft"])
            ok = delta <= tolerance
            verdict = classify(value_live, threshold)
            print(f"  {datum:5s} live peak {value_live:8.3f} ft at {time_live} "
                  f"| recorded {recorded['peak_ft']:8.3f} | delta {delta:.3f} "
                  f"{'OK' if ok else 'MISMATCH'} | {verdict} threshold")
            if not ok:
                failures.append(f"{case['name']}/{datum}: live {value_live} vs "
                                f"recorded {recorded['peak_ft']}")
        # The rule the project depends on.
        stnd = case["datums"][REQUIRED_DATUM]["peak_ft"]
        mllw = case["datums"][REJECTED_DATUM]["peak_ft"]
        if exceeds(stnd, threshold) != case["expected_exceeds_nos_minor"]:
            failures.append(f"{case['name']}: {REQUIRED_DATUM} peak {stnd} disagrees with "
                            f"the recorded expectation")
        if exceeds(mllw, threshold):
            failures.append(f"{case['name']}: {REJECTED_DATUM} peak {mllw} unexpectedly "
                            f"exceeds the threshold, so the datum trap no longer reproduces")
        print()

    if failures:
        print("FAILURES:")
        for f in failures:
            print("  -", f)
        return 1
    print("All recorded peaks reproduced and the datum rule holds.")
    return 0


def main() -> int:
    return check_live()


if __name__ == "__main__":
    sys.exit(main())
