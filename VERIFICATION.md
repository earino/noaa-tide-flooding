# Verification

What was verified, on what, and by which command. Nothing here is asserted from memory: each line
names the evidence.

| what | how | result |
| --- | --- | --- |
| Artifact qualified | `python3 code/qualify_dataset.py ./task/temporal` and `.../station_disjoint`, on the worker (job `noaa-004`) | **PASSED - 32 checks per level, 0 failed** |
| Panel completeness | `code/build.py` coverage gate, recorded in `output/build_summary.json` | **122/122 stations, 2,440/2,440 station-years, 0 errors** |
| Report describes the uploaded bytes | gate report digests vs the staging release manifest, all ten files | **10/10 match** |
| Baseline | `sh baseline/reproduce_baseline.sh ./task both`, runner files copied verbatim | temporal **0.8633**, station_disjoint **0.8690**, `CONTRACT OK` both |
| Persistence floor | `code/persistence_baseline.py --fetch` | **0.8265** and **0.8454**, no training |
| Package consistency | `python3 scripts/check-package.py release/noaa-tide-flooding` | **OK** |
| Consumer verification | clean-room container, no build-repo access, no credential (job `noaa-consumer-003`, on the published bytes) | **PASSED** - see below |
| CI for the construction commit | GitHub Actions run for the pushed SHA | recorded in `STATE.md` |

## Consumer verification: PASSED on the published bytes

Run in a clean-room container on a worker (job `noaa-consumer-003`): **no access to the building
repository, no credential**. It was given the published package tree and the release assets exactly
as a consumer receives them - fetched by the worker host from the release the dataset is published
in (`earino/noaa-tide-flooding`, release 396698120, tag `v2026.09`: 10 of 10 files, 196,018,020
bytes, each against the digest `artifacts[0].levels` records) - then hashed the cloned package
against `MANIFEST.json`, verified the assets with `sha256sum -c`, ran the published gate on both
levels, and reproduced the baseline through the published contract.

| step | result |
| --- | --- |
| published package vs `MANIFEST.json` | every listed file matched its recorded hash |
| `sha256sum -c SHA256SUMS` | OK |
| published gate, temporal | exit 0, `QUALIFICATION PASSED`, artifact `bb051dc304a4ee63` |
| published gate, station_disjoint | exit 0, `QUALIFICATION PASSED`, artifact `92297a5b62f86b29` |
| baseline, temporal | `CONTRACT OK`, eval AUC **0.8633** |
| baseline, station_disjoint | `CONTRACT OK`, eval AUC **0.8690** |

Both gate artifact versions equal the versions recorded for the accepted artifact, so the bytes a
consumer receives are the gated bytes. The reproduction returned **the recorded pair itself** (0.8633
/ 0.8690): on these bytes the independent run and the recorded measurement agree to the digit, so
the spread described below does not apply to this pass.

The 2026-09-20 pass (`noaa-consumer-002`) returned 0.8651 / 0.8687 against that artifact's recorded 0.8638 /
0.8688 and ran against the **superseded** artifact (`noaa-003`, label `late`); it is kept in the
candidate record rather than averaged in. Two of its results are properties of the runner rather
than of the artifact, and carry over: training is not bit-reproducible (a reproduction lands within
about 0.002 of a figure taken the same way), and the dependencies resolve to pandas 2.3.3, numpy
2.5.3, xgboost 3.4.1, scikit-learn 1.9.1.

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
  A second documentation pass, on 2026-09-26, corrected the label column name in
  `DATA_DICTIONARY.md` (the shipped target is `minor_flood`, not the `late` copied from the Austin
  task), this document's baseline row and job reference, and the superseded figures that were still
  carried in `README.md`, `RELEASE_NOTES.md`, `REPRODUCE.md`, `baseline/README.md`,
  `baseline/reproduce_baseline.sh` and `code/persistence_baseline.py`. Again no asset byte changed
  and no digest moved.
- **The datum trap was measured, not assumed.** Comparing MLLW-referenced heights to `nos_minor`
  silently yields zero positives; `code/datum_check.py` records the regression that shows it, which
  is why `datum=STND` is a requirement rather than a note.
