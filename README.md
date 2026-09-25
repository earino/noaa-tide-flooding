# NOAA tide flooding prediction dataset

**Version 2026.09** · artifact `8896c4423c53cb14…` (temporal), `e6aff23f394ddfe4…` (station-disjoint)

**Status: private.** Prepared for review. Publication requires explicit authorisation.

## What this is

A prediction task built from NOAA's own verified water-level observations: **will a station's daily
maximum observed water level exceed its published minor flood threshold tomorrow?**

- **122 NOS stations**, 2006-2025, **2,440 station-years**, one row per station-day.
- The label uses **NOAA's own minor-flood days** (the HTF daily product's `minFlag`), not our
  reduction of the raw observations. Our reduction disagreed with the publisher by about 20% on a
  year with real signal, and a label that contradicts the publisher's own product has to be
  justified - so we ship theirs.
- The threshold is the **physical published `nos_minor` value**. It is not a quantile chosen to
  balance the classes.
- Features are **observations only**, station-normalised with trailing windows, so the future cannot
  leak into a feature. Tide predictions and model guidance are excluded: they are model output, and
  including them would hand the task over.

## Two levels, each a complete task instance

| level | train | eval | holdout | what it asks |
| --- | --- | --- | --- | --- |
| `temporal` | 2006-2021, all 122 stations | 2022-2023 | 2024-2025 | the benchmark-typical panel split |
| `station_disjoint` | 2006-2021, 81 stations | 2022-2023, **41 unseen stations** | 2024-2025, the same 41 | whether an agent learned something transferable rather than one station's local behaviour |

The station-disjoint level is the reason this dataset exists. NOAA publishes the observations, the
verified maxima and the annual counts - **access is not the contribution**. A frozen multi-station
panel, an observations-only feature contract, a station-disjoint generalisation split and a
leakage gate around all of it are not things NOAA's products package.

## The numbers, including the uncomfortable one

Baseline, through the benchmark's own `train.py`/`validate.py` copied verbatim:

| level | eval AUC | rows (train/eval/holdout) |
| --- | --- | --- |
| temporal | **0.8638** | 697,373 / 89,038 / 88,841 |
| station_disjoint | **0.8688** | 461,580 / 29,930 / 29,930 |

The station-disjoint level scores the same as the temporal one **on stations the model never saw**,
so the signal is not station-specific memorisation.

**And the floor, measured without training:** a single stock feature - yesterday's maximum against
the station's own threshold - already reaches **0.8265**
(temporal) and **0.8454** (station-disjoint). The
trained model's real headroom is **+0.0373** and
**+0.0234**. This is published because a reviewer should see it, not
discover it. See `measurements.persistence_calibration`.

About **2% of station-days are positive**, and a constant "no flood" answer agrees with the label
about 96% of the time. Score AUC, not accuracy.

## Contents

| file | what |
| --- | --- |
| `get_dataset.py` | downloads the release assets, verifies `SHA256SUMS`, restores the runner layout |
| `code/` | construction, the frozen station list, the label-route and datum checks, the persistence measurement, and the qualification gate |
| `baseline/` | the benchmark's runner files, copied verbatim, plus `reproduce_baseline.sh` |
| `DATA_DICTIONARY.md` | every shipped column, the splits and the label |
| `REPRODUCE.md` | a clean-checkout reproduction, command by command |
| `VERIFICATION.md` | what was verified, and what was **not** |
| `measurements.json` | every measured figure with the command that produced it |
| `MANIFEST.json`, `SHA256SUMS` | hashes, splits, licence block, baseline record |

The data itself is in the release assets, not in this repository: `temporal-public-train.csv` and
nine more, flat because GitHub rejects `/` in asset names. `get_dataset.py` restores
`<dest>/<level>/public|private/…`.

## Quick start

```bash
python3 get_dataset.py --dest ./task
sh baseline/reproduce_baseline.sh ./task both
# recorded: 0.8638 (temporal) and 0.8688 (station-disjoint); an independent
# reproduction on the published bytes gave 0.8651 and 0.8687 - the runner's
# training is not bit-reproducible, so read these as the same result, not a constant
```

The repository is private, so a credential is needed: the `gh` CLI, or `GITHUB_TOKEN`.

## Licence, attribution and provenance

Our code and documentation: **MIT**. Our rights in the derived compilation (the frozen station list,
the row selection, the derived label, the two partitions, the feature construction): **CC0-1.0**.
NOAA's data itself is a **US Government work in the public domain**, preserved unchanged.

**This is a derived dataset and not an official NOAA, NOS or NWS product.** NOAA's own constraint -
modified content must not be presented as official government material - is honoured throughout, and
attribution is given as requested. Source: NOAA CO-OPS verified water levels and flood thresholds,
<https://tidesandcurrents.noaa.gov/>, accessed 2026-09-18. See `LICENSE.md` for the full terms.

## What this release is not

No coding agent and no harness comparison was run against this dataset, and none is implied. One
baseline through the training contract, plus the persistence floor, is the whole of the machine
learning here.
