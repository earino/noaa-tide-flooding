# Verification

What was verified, on what, and by which command. Nothing here is asserted from memory: each line
names the evidence.

| what | how | result |
| --- | --- | --- |
| Artifact qualified | `python3 code/qualify_dataset.py ./task/temporal` and `.../station_disjoint`, on the worker (job `noaa-003`) | **PASSED - 32 checks per level, 0 failed** |
| Panel completeness | `code/build.py` coverage gate, recorded in `output/build_summary.json` | **122/122 stations, 2,440/2,440 station-years, 0 errors** |
| Report describes the uploaded bytes | gate report digests vs the staging release manifest, all ten files | **10/10 match** |
| Baseline | `sh baseline/reproduce_baseline.sh ./task both`, runner files copied verbatim | temporal **0.8638**, station_disjoint **0.8688**, `CONTRACT OK` both |
| Persistence floor | `code/persistence_baseline.py --fetch` | **0.8265** and **0.8454**, no training |
| Package consistency | `python3 scripts/check-package.py release/noaa-tide-flooding` | **OK** |
| Consumer verification | clean-room container, no build-repo access, no credential | **PASSED** - see below |
| CI for the construction commit | GitHub Actions run for the pushed SHA | recorded in `STATE.md` |

## Consumer verification: PASSED

Run in a clean-room container on a worker: **no access to the building repository, no credential**.
It cloned the published repository, hashed every file against `MANIFEST.json`, verified the release
assets with `sha256sum -c`, ran the published gate on both levels, and reproduced the baseline.

| step | result |
| --- | --- |
| published package vs `MANIFEST.json` | 28 files checked, every one matched |
| `sha256sum -c SHA256SUMS` | OK on all ten assets |
| published gate, temporal | exit 0, `QUALIFICATION PASSED`, artifact `8896c4423c53cb14` |
| published gate, station_disjoint | exit 0, `QUALIFICATION PASSED`, artifact `e6aff23f394ddfe4` |
| baseline, temporal | `CONTRACT OK`, eval AUC 0.8651 |
| baseline, station_disjoint | `CONTRACT OK`, eval AUC 0.8687 |

Both gate artifact versions match the ones recorded at build time, so the published bytes are the
gated bytes. The first attempt (`noaa-consumer-001`) failed during its dependency step and left no
log to diagnose; the step was instrumented and the rerun is the record above.

### The baseline is reproducible to about 0.002, not to the digit

The recorded baseline is **0.8638 / 0.8688**; the independent reproduction gave **0.8651 / 0.8687**.
Nothing else moved: the artifact digests are identical, both gate reports name the same artifact
versions, and the dependencies resolve to the same versions (pandas 2.3.3, numpy 2.5.3, xgboost
3.4.1, scikit-learn 1.9.1).

The cause is the runner's training: xgboost with default threading on identical bytes is not
bit-reproducible. So the recorded figure is **one measurement, not a constant**, and the card and
reproduction guide say so. A reproduction within about 0.002 is the same result; a reproduction
outside 0.02 would be a real difference, and the consumer check now compares values instead of only
checking exit codes.

## What this verification does **not** cover

- **The holdout was never scored.** No model selection, threshold choice or tuning used it. It ships
  labelled, as a reported result, not as a hidden test set.
- **No agent or harness comparison.** The baseline is one pass through the training and validation
  contract; nothing about coding-agent performance is measured or implied.
- **Dependency versions of the original baseline run are missing.** That job's report recorded the
  runner's output but not the installed package versions; the generator has since been corrected.
  The consumer reproduction *did* record them (pandas 2.3.3, numpy 2.5.3, xgboost 3.4.1,
  scikit-learn 1.9.1), which is what makes the 0.002 difference attributable to the training rather
  than to a version change.
- **The 6-minute raw series was not re-derived.** The build uses NOAA's verified daily maxima and
  their own daily flood flags. Re-deriving the panel from raw observations is possible but is not
  part of this verification, and the label route was separately checked against NOAA's own counts
  (`code/label_route_check.py`).
- **The documentation was revised after the consumer check ran.** The data assets were not touched:
  their digests are unchanged and the gate still names the same artifact versions. What changed is
  this document, the card and the reproduction guide, to record the reproduction and its spread.
- **The datum trap was measured, not assumed.** Comparing MLLW-referenced heights to `nos_minor`
  silently yields zero positives; `code/datum_check.py` records the regression that shows it, which
  is why `datum=STND` is a requirement rather than a note.
