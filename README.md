<!-- dataset-factory:links -->
**Dataset Factory · v2026.09**

[Dataset website](https://earino.github.io/noaa-tide-flooding/versions/v2026.09/) · [GitHub release](https://github.com/earino/noaa-tide-flooding/releases/tag/v2026.09) · [Hugging Face](https://huggingface.co/datasets/earino/noaa-tide-flooding/tree/v2026.09) · [Catalogue](https://earino.github.io/dataset-factory-site/)

Artifact: fb49f932c7b4ea5ab532c20f7dce59a7d733de925d1e172054ff1d38abe1eeed

### Suitability and evaluation requirements

Retained for retrospective model-development research with documented timing limitations. Later evaluation rows expose earlier outcomes; predictions require restricted access.

**Supported uses:** Retrospective train/validation model-development experiments under the documented timing and selection limitations; Final evaluation only under a protocol that isolates holdout data from development and prevents later rows influencing earlier predictions

**Not supported:** Claims of verified real-time or operational forecasting validity; Treating development/validation scores as untouched final-test results; Forecasting scores from unrestricted cross-row access to this artifact

**Evaluation access:** chronological. The labeled eval split is development/validation data. Keep the final holdout outside agent development; prevent later rows from influencing earlier predictions.

**Historical availability:** assumed. **Training-label timing:** unverified. **Vintage:** current snapshot. **Selection:** unverified.

**Cross-row audit:** recovery demonstrated. Both split designs (temporal, station-disjoint) tested; temporal 88,915/89,038 covered AUC 0.99929 with 423 binary mismatches; station-disjoint 29,889/29,930 AUC 0.99922 with 191; a D+2 margin_ft variant still ranks ~0.9993, so deleting the obvious column is not a fix Holdout recovery was not tested by this audit.

Structural qualification and baseline scores do not certify operational forecasting validity.

- Near-perfect future-outcome ranking in both split designs (see cross_row_audit scope).
- Dictionary/build day-definition conflict: release/noaa-tide-flooding/code/build.py assigns the official minFlag to date+1 while DATA_DICTIONARY.md describes the target-day value.
- One calendar week straddles train/eval in each design (244 temporal, 82 station-disjoint eval rows).
- Historical feature/label availability is assumed from current snapshots, not verified against release vintages.
- The current scorer passes the complete feature frame; isolation is not mechanically enforced.

**Corrections to the historical documentation:**

- For row date D, observed_max_ft is the measurement on D; margin_ft and trailing summaries use observations preceding D (through D-1 when consecutive). The label is NOAA’s official minor-flood flag for D+1. It is not the same-day flag and is not defined by simply thresholding observed_max_ft. Historical verification/publication timing remains unverified.
- The original dictionary says carry columns are dropped. The bundled template excludes only target and id_columns; observed_max_ft and threshold_ft are therefore available to that baseline. This does not by itself expose its own D+1 label, but the documentation must not claim those columns were excluded.

Review: 2026-10-24; applies to v2026.09 / `fb49f932c7b4ea5ab532c20f7dce59a7d733de925d1e172054ff1d38abe1eeed`. Frozen data and tags are unchanged.
<!-- /dataset-factory:links -->

# NOAA tide flooding prediction dataset

**Version 2026.09** · artifact `bb051dc304a4ee63…` (temporal), `92297a5b62f86b29…` (station-disjoint)

**Status: public since 2026-09-25**, published after explicit operator authorisation - [dataset website](https://earino.github.io/noaa-tide-flooding/versions/v2026.09/) · [GitHub release](https://github.com/earino/noaa-tide-flooding/releases/tag/v2026.09) · [Hugging Face](https://huggingface.co/datasets/earino/noaa-tide-flooding)

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
| temporal | **0.8633** | 697,373 / 89,038 / 88,841 |
| station_disjoint | **0.8690** | 461,580 / 29,930 / 29,930 |

The station-disjoint level scores the same as the temporal one **on stations the model never saw**,
so the signal is not station-specific memorisation.

**And the floor, measured without training:** a single stock feature - yesterday's maximum against
the station's own threshold - already reaches **0.8265** (temporal) and **0.8454** (station-disjoint),
so the trained model's headroom is about **+0.0368** and **+0.0236**. This is published because a
reviewer should see it, not discover it. The floor was measured on the superseded artifact's eval
split, which carries the same rows and positives as the released one; see
`measurements.persistence_calibration`.

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
# recorded: 0.8633 (temporal) and 0.8690 (station-disjoint); the independent
# clean-room reproduction on the published bytes returned the same pair - the
# runner's training is not bit-reproducible, so read either as one result
```

The release is public, so nothing here needs a credential: `get_dataset.py` fetches the assets anonymously.

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
