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

# Release notes

## 2026.09 - first release (published 2026-09-25)

**NOAA tide flooding prediction dataset.** 122 NOS stations, 2006-2025, 2,440 station-years, in two
levels that are each a complete task instance: `temporal` and `station_disjoint`.

Verified before packaging:

- Complete panel: **122/122 stations, 2,440/2,440 station-years, 4,880 requests, 0 errors.** The
  builder exits non-zero on a single lost station-year, so an incomplete panel cannot be scored as
  the frozen one.
- Qualification gate **PASSED, 32 checks per level, 0 failed**, on the full artifacts (both levels),
  run on a worker.
- Baseline through the benchmark's own contract: **temporal 0.8633**, **station_disjoint 0.8690**,
  `CONTRACT OK` on both.
- Persistence floor measured: **0.8265** and **0.8454** from one unlearned feature, on the
  superseded artifact's eval split, which carries the same rows and positives as the released
  one.

### Known limitations, stated rather than discovered later

- **Narrow headroom.** The trained model beats a single stock feature by about +0.0368
  (temporal) and +0.0236 (station-disjoint). The task is real and transfers across unseen stations, but a
  one-feature rule gets most of the way. Recorded in `measurements.persistence_calibration`.
- **Class imbalance.** ~2% positive rate; a constant answer agrees 96% of the time. Score AUC.
- **The recorded baseline is one measurement, not a constant.** The independent clean-room
  reproduction on the published bytes (`noaa-consumer-003`, release 396698120) returned the recorded
  pair itself, 0.8633 and 0.8690; the earlier 2026-09-20 pass gave 0.8651 and 0.8687 and ran against
  the superseded artifact. xgboost with default threading is not bit-reproducible. Recorded in
  `measurements.baseline.independent_reproduction`.
- **The baseline job did not record its dependency versions.** The runner's own output is recorded,
  and the version gap is stated in `VERIFICATION.md`. Fixed in the report generator afterwards, so
  later baselines will carry them.
- **`latitude` is declared both as a feature and as a carry column** in the artifact's
  `quality.json`. The runner drops carry columns, so it is not used, but the declaration is
  internally inconsistent and should be corrected in a future build.
- **No agent or harness comparison was run.** None is implied.
- Two earlier builds were **not** shipped: `noaa-001` lost 13 stations and `noaa-002` lost 60
  station-years to fetch errors its retry treated as permanent. Both were coverage failures, both
  were fixed in the builder's error reporting and retry policy, and the qualification gates passed
  those incomplete artifacts anyway - which is why coverage is now a hard condition in the builder
  rather than something the gates were expected to catch. `noaa-003` was built from the corrected
  panel but still carried the label name copied from the Austin task (`late`); it was superseded by
  `noaa-004`, whose only schema change is the label column `minor_flood`.

### Versioning

Assets are immutable once published. A data correction ships as a new version; earlier versions
are preserved and never edited in place. Document-only corrections - prose, figures, publication
records - move no asset digest and are applied in place.
