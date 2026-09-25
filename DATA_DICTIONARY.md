# Data dictionary

Two levels, each a complete task instance: **temporal** (all 122 stations, disjoint windows in time) and **station_disjoint** (41 stations held out of training entirely). Each level ships `public/train.csv`, `public/eval.csv`, `private/holdout.csv`, `meta.json` and `quality.json`.

**Prediction time.** The end of the local day before the target day. Every feature is knowable then; nothing from the target day is.

**Features are observations only.** NOAA tide predictions and model guidance are excluded: they are model output, not observations, and including them would hand the task over.

| column | meaning |
| --- | --- |
| `row_id` | Stable row identifier. |
| `station_id` | NOS station id. Identifier, not a feature. |
| `station_name` | Human-readable station name. Carried for interpretation; dropped before training. |
| `date` | Local calendar day of the observation window. Identifier and the split's time column. |
| `latitude` | Station latitude. Declared both as a feature and as a carry column by the artifact; the runner drops carry columns, so it is not used. |
| `longitude` | Station longitude. Carried for interpretation; dropped before training. |
| `threshold_ft` | The station's published NOS minor flood threshold, in feet on station datum (STND). Carried: it is the label's definition, so it is not a predictor. |
| `margin_ft` | Feature. `observed_max_ft` of the last completed day minus the station's threshold, in feet. Positive means the previous day already exceeded. |
| `margin_ratio` | Feature. The same margin as a ratio of the station's threshold. |
| `trailing7_mean` | Feature. Mean of the station's own daily maxima over the trailing 7 days, ending the day before the target. |
| `trailing30_mean` | Feature. Trailing 30-day mean of the same. |
| `trailing30_std` | Feature. Trailing 30-day standard deviation - the station's recent variability. |
| `exceed_last7` | Feature. Count of exceedance days in the trailing 7 days. |
| `days_since_exceedance` | Feature. Days since the station last exceeded its threshold. |
| `day_of_year` | Feature. Calendar position of the target day (seasonal signal). |
| `threshold_rank` | Feature. The station's threshold ranked among the frozen 122 - a station's general exposure. |
| `observed_max_ft` | The target day's maximum observed water level. **This is the label source and must never be used as a feature** - the gate tests that it is absent from what a model sees. |
| `late` | **Label.** 1 when the target day's maximum observed water level exceeded the station's published minor threshold, 0 otherwise. |

## Splits

**temporal** - `All 122 frozen stations; disjoint windows in time.`

| split | rows | positives | positive rate | window |
| --- | --- | --- | --- | --- |
| train | 697,373 | 11,774 | 1.6880% | 2006-01-01 to 2022-01-01 |
| eval | 89,038 | 1,815 | 2.0380% | 2022-01-01 to 2024-01-01 |
| holdout | 88,841 | 2,850 | 3.2080% | 2024-01-01 to 2026-01-01 |

Stations: train 122, eval/holdout 122.

**station_disjoint** - `Evaluation on stations that training never sees (group0 by station-id order), so this level measures transfer rather than recall of a station's own behaviour.`

| split | rows | positives | positive rate | window |
| --- | --- | --- | --- | --- |
| train | 461,580 | 7,513 | 1.6280% | 2006-01-01 to 2022-01-01 |
| eval | 29,930 | 788 | 2.6330% | 2022-01-01 to 2024-01-01 |
| holdout | 29,930 | 1,090 | 3.6420% | 2024-01-01 to 2026-01-01 |

Stations: train 81, eval/holdout 41.

## Class imbalance, and why it matters here

Only about 2% of station-days are positive, so **accuracy is not a usable score**. The plain rule "it flooded yesterday" agrees with the label roughly 96% of the time while carrying almost no ranking signal. The runner contract scores AUC, and the persistence floor in `measurements.persistence_calibration` is what a single unlearned feature achieves.

## The holdout

The holdout is **labelled and published** on both destinations. It is a reported result, not a hidden test set. It stays outside the workspace an evaluated agent is given, and no split is reconstructed from another.
