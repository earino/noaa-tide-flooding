#!/usr/bin/env python3
"""Lay one level out the way the runner's contract expects.

    python3 code/materialize.py <dataset-dir> <work-dir> <level>

Reads <dataset-dir>/<level>/{meta.json,quality.json,public/train.csv,public/eval.csv} and writes
<work-dir>/task.json plus data/train.csv and data/eval.csv. The private holdout is deliberately not
copied: the contract scores train and eval only.

task.json carries the keys the runner reads - `target`, `positive_label`, `id_columns` - and the
`id_columns` list is extended with the artifact's declared *carry* columns. quality.json marks some
shipped columns as present for interpretation rather than as predictors (`station_name` is a
description of the station), and the runner has no such concept, so without this a string column
would reach the model.
"""

import json
import shutil
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit("usage: materialize.py <dataset-dir> <work-dir> <level>")
    dataset, work, level = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3].rstrip("/")
    source = dataset / level
    meta = json.loads((source / "meta.json").read_text())
    quality = json.loads((source / "quality.json").read_text()) if (source / "quality.json").is_file() else {}

    drop = list(meta.get("id_columns", []))
    for column in quality.get("carry_columns", []):
        if column not in drop:
            drop.append(column)
    task = dict(meta, id_columns=drop, carry_columns=quality.get("carry_columns", []))

    (work / "data").mkdir(parents=True, exist_ok=True)
    (work / "task.json").write_text(json.dumps(task, indent=2) + "\n")
    for split in ("train", "eval"):
        shutil.copy2(source / "public" / f"{split}.csv", work / "data" / f"{split}.csv")
    features = [c for c in meta.get("columns", []) if c not in drop]
    print(f"[materialize] {level}: {len(features)} features, {len(drop)} identifier/carry columns dropped")
    print(f"[materialize] dropped: {drop}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
