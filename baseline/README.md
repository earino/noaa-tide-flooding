# The baseline runner, and why it is shipped here

`train.py`, `validate.py` and `validate.sh` are **copied verbatim** from `earino/harness_benchmark`
(file set `task_template/`). They are included so the baseline in `MANIFEST.json` is reproducible
from this repository alone, without access to that project.

| file | sha256 (must match `MANIFEST.json`) |
|---|---|
| `train.py` | `a3c6bcf13735bc85c52129ded68f839090dffdc266ebc3810dc61b2e6ea5e7e8` |
| `validate.py` | `b597e7f84fed614e64b4a86fbecbd6ec0145916a24d0d221a796586976418e7b` |
| `validate.sh` | `3f06ca48f11c2e05d331b4d8394284925de660c1d4b086d2f8243959e83b7e6d` |

**Provenance and permission.** Source: `earino/harness_benchmark`, file set `task_template/`,
retrieved 2026-09-18. That project is the copyright holder's own work, developed with Claude and
Szilard; the holder confirmed permission to release these copies here under MIT, with credits
preserved. They are distributed unchanged - the digests above are identical to the ones the
benchmark holds.

## Running it

    sh baseline/reproduce_baseline.sh ./task both        # or: temporal | station_disjoint

The script materialises each level into the runner's expected layout (`task.json`, `data/train.csv`,
`data/eval.csv`), runs the contract, and prints the eval AUC. The holdout is not copied into the
working directory: the contract scores train and eval only, and the labelled holdout stays outside
the workspace an evaluated agent is given.

## Reproducing the numbers from a clean checkout

1. `python3 get_dataset.py --dest ./task` - downloads the release assets, verifies them against
   `SHA256SUMS`, and restores the layout.
2. `sh baseline/reproduce_baseline.sh ./task both` - expect **temporal 0.8638** and
   **station_disjoint 0.8688** eval AUC.

The exact command, the expected values and the values actually obtained on the published bytes are
recorded in `MANIFEST.json` (`measurements.baseline`). The runner's own output is the evidence; no
number here was produced by a different procedure.

## What this baseline is not

One baseline through the training and validation contract. **No coding agent and no harness
comparison was run, and none is implied.** The persistence floor - what a single unlearned feature
achieves - is a separate measurement, recorded in `measurements.persistence_calibration`; it is
deliberately *not* called a baseline here, because it does not use the contract.
