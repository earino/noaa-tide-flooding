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
