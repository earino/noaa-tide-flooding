#!/usr/bin/env python3
"""How much of the baseline's AUC is just persistence?

The full-model baseline scored 0.8638 (temporal) and 0.8688 (station-disjoint) on the eval split.
But the strongest feature is yesterday's maximum against the station's own threshold, and flood days
arrive in runs, so a model that has learned almost nothing may still score well. This measures the
floor: what a *single stock feature* achieves, with no training at all.

Deliberately stdlib only. The eval splits are ~17 MB together - a bounded sample, not the artifact -
and a rank-based AUC needs nothing more than sorted ranks, so no dependency is installed on the
coordinator to answer one question.

  python3 persistence_baseline.py            # uses the cached eval splits
  python3 persistence_baseline.py --fetch    # re-download them from the staging release
"""

import argparse
import csv
import json
import math
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / "eval_cache"
RESULT = HERE / "persistence_baseline_result.json"
STAGING_RELEASE = 392230750  # job-noaa-003: the accepted artifact
SPLITS = {"temporal": "output/extract/temporal/public/eval.csv",
          "station_disjoint": "output/extract/station_disjoint/public/eval.csv"}


def fetch_splits():
    """Fetch only the two eval splits, via the release manifest, and only if not already cached."""
    CACHE.mkdir(exist_ok=True)
    release = json.loads(subprocess.run(
        ["gh", "api", f"repos/earino/dataset-factory-staging/releases/{STAGING_RELEASE}"],
        capture_output=True, text=True).stdout)
    assets = {a["name"]: a["id"] for a in release["assets"]}
    manifest = json.loads(subprocess.run(
        ["gh", "api", "-H", "Accept: application/octet-stream",
         f"repos/earino/dataset-factory-staging/releases/assets/{assets['manifest.json']}"],
        capture_output=True).stdout)
    by_file = {a["file"]: a["name"] for a in manifest["assets"]}
    for level, logical in SPLITS.items():
        target = CACHE / f"{level}.eval.csv"
        if target.is_file():
            print(f"  {level}: cached ({target.stat().st_size:,} bytes)")
            continue
        data = subprocess.run(
            ["gh", "api", "-H", "Accept: application/octet-stream",
             f"repos/earino/dataset-factory-staging/releases/assets/{assets[by_file[logical]]}"],
            capture_output=True).stdout
        target.write_bytes(data)
        print(f"  {level}: fetched {len(data):,} bytes")


def auc(labels, scores):
    """Rank-based AUC (Mann-Whitney), with ties averaged. No dependency required."""
    paired = sorted(zip(scores, labels))
    ranks = [0.0] * len(paired)
    index = 0
    while index < len(paired):
        end = index
        while end + 1 < len(paired) and paired[end + 1][0] == paired[index][0]:
            end += 1
        average = (index + end) / 2 + 1
        for position in range(index, end + 1):
            ranks[position] = average
        index = end + 1
    positives = [r for r, (_, label) in zip(ranks, paired) if label == 1]
    negatives = [r for r, (_, label) in zip(ranks, paired) if label == 0]
    if not positives or not negatives:
        return None
    return (sum(positives) - len(positives) * (len(positives) + 1) / 2) / (len(positives) * len(negatives))


def r2(value):
    """round(), but a column with no rankable spread stays None rather than crashing the report."""
    return None if value is None else round(value, 4)


def measure(level, path):
    rows = []
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            rows.append(row)
    labels = [int(row["minor_flood"]) for row in rows]
    base = sum(labels) / len(labels)
    single = {}
    for column in ("margin_ft", "margin_ratio", "trailing7_mean", "trailing30_mean",
                   "days_since_exceedance", "exceed_last7"):
        scores = [float(row[column]) for row in rows]
        single[column] = r2(auc(labels, scores))
    # "Did it flood yesterday?" as a plain yes/no rule: positive margin means yesterday exceeded.
    persistence = [1 if float(row["margin_ft"]) > 0 else 0 for row in rows]
    return {"rows": len(rows), "positives": sum(labels), "positive_rate": round(base, 6),
            "auc_by_single_feature": single,
            "auc_of_yesterdays_exceedance_alone": r2(auc(labels, persistence)),
            "agreement_of_yesterdays_exceedance": round(
                sum(1 for label, pred in zip(labels, persistence) if label == pred) / len(labels), 4)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args()
    if args.fetch or not CACHE.is_dir():
        print("fetching eval splits from staging:")
        fetch_splits()

    result = {"question": "how much of the baseline's AUC is persistence rather than prediction",
              "method": "single stock features and a plain 'yesterday exceeded' rule, no training; "
                        "rank-based AUC; the eval split only",
              "source": f"staging release {STAGING_RELEASE} (job-noaa-003), public/eval.csv per level",
              "levels": {}}
    full = {"temporal": 0.8638, "station_disjoint": 0.8688}
    for level in ("temporal", "station_disjoint"):
        measured = measure(level, CACHE / f"{level}.eval.csv")
        measured["full_model_eval_auc"] = full[level]
        best = max(v for v in measured["auc_by_single_feature"].values() if v is not None)
        measured["best_single_feature_auc"] = best
        measured["headroom_over_best_single_feature"] = round(full[level] - best, 4)
        result["levels"][level] = measured
        print(f"\n{level}: {measured['rows']:,} rows, {measured['positive_rate']:.4%} positive")
        for column, value in sorted(measured["auc_by_single_feature"].items(),
                                   key=lambda item: -(item[1] or 0)):
            print(f"   {column:24} AUC {value}")
        print(f"   {'yesterday exceeded (rule)':24} AUC {measured['auc_of_yesterdays_exceedance_alone']}"
              f"  agreement {measured['agreement_of_yesterdays_exceedance']:.4f}")
        print(f"   {'full model':24} AUC {full[level]}")
        print(f"   headroom over the best single feature: {measured['headroom_over_best_single_feature']}")
    RESULT.write_text(json.dumps(result, indent=2) + "\n")
    print(f"\nwrote {RESULT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())