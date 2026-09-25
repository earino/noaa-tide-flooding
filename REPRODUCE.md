# Reproducing this dataset from a clean checkout

Nothing below needs the private repository that built it. This package is self-contained: the
runner files are shipped verbatim, the construction code is in `code/`, and every number is
checkable against `SHA256SUMS` and `MANIFEST.json`.

## 1. Get the data

```bash
python3 get_dataset.py --dest ./task          # all 10 assets, ~184 MB
python3 get_dataset.py --dest ./task --level temporal
```

The repository is private, so authenticate first: `gh auth login`, or export `GITHUB_TOKEN`.

`get_dataset.py` verifies each file against the release's own `size` and against `SHA256SUMS`, and
refuses the download on any mismatch. It restores the layout the runner expects:

```
task/temporal/public/train.csv      task/temporal/public/eval.csv
task/temporal/private/holdout.csv   task/temporal/meta.json       task/temporal/quality.json
task/station_disjoint/...           (same shape)
```

## 2. Check the bytes

```bash
# the ten assets, under their flat names
sha256sum -c SHA256SUMS        # after copying the asset names back to their paths
python3 -c "import json;print(json.load(open('MANIFEST.json'))['artifact_version'])"
```

`MANIFEST.json.levels` carries the **gate-produced** artifact version of each level, and
`artifact_version` names the two together. The digests in `expected_artifact.json` were cross-checked
against the bytes preserved in the staging release, so the report and the uploaded files agree.

## 3. Re-run the qualification gate

The gate is shipped at `code/qualify_dataset.py` (version 1.3.0).

```bash
python3 code/qualify_dataset.py ./task/temporal
python3 code/qualify_dataset.py ./task/station_disjoint
```

Expect `ok: true`, **32 checks per level**, 0 failed. The gate is what makes a number from this
dataset usable: it tests leakage, prediction timing, units and reference frames, the splits, and the
runner's input contract. A number quoted from an artifact the gate has not passed is not usable.

## 4. Reproduce the baseline

```bash
sh baseline/reproduce_baseline.sh ./task both
```

Expect **temporal ~0.864** and **station_disjoint ~0.869** eval AUC from the runner's own output.
The recorded values are 0.8638 and 0.8688; an independent clean-room reproduction on the published
bytes gave 0.8651 and 0.8687. The runner's training is not bit-reproducible (xgboost with default
threading on identical bytes), so the last decimal moves between runs. The artifact digests do not
move, and `measurements.baseline.independent_reproduction` records both pairs. The runner files are the benchmark's, copied verbatim; their digests are
in `baseline/README.md` and `MANIFEST.json`, and they match what the benchmark holds.

## 5. Reproduce the persistence floor

```bash
python3 code/persistence_baseline.py            # needs the eval splits cached; see --fetch
```

Expect `margin_ft` alone at about 0.8265 (temporal) and
0.8454 (station-disjoint). This is the number that keeps the
baseline honest: the trained model's headroom over it is small, and the dataset card says so.

## What is deliberately not here

- The raw NOAA 6-minute series. The build uses the publisher's verified daily maxima
  (`daily_max_min`) and their own HTF daily flags: **4,880 requests, ~184 MB** rather than 29,160
  requests and about 15.2 GiB. Re-deriving the panel from the raw series is not necessary to check
  anything in this package.
- Any agent or harness run. None was performed.
