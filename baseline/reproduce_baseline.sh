#!/bin/sh
# Reproduce the recorded baseline: the benchmark's own train.py and validate.py, unmodified, against
# this dataset, for each of the two levels.
#
#   sh baseline/reproduce_baseline.sh [dataset-dir] [level|both]      (default: ./task both)
#
# <dataset-dir> is what get_dataset.py produces: temporal/ and station_disjoint/, each holding
# public/, private/, meta.json, quality.json. The private holdout is deliberately not copied into the
# working directory - the contract scores train and eval only.
set -eu

DATASET=$(cd "${1:-task}" && pwd)
LEVELS="${2:-both}"
HERE=$(cd "$(dirname "$0")" && pwd)

if [ "$LEVELS" = "both" ]; then
    LIST="temporal station_disjoint"
else
    LIST="$LEVELS"
fi

if ! python3 -c "import pandas, numpy, xgboost, sklearn" 2>/dev/null; then
    echo "installing the benchmark's declared dependency ranges ..."
    python3 -m pip install --quiet "pandas>=2.2,<3" "numpy>=1.26" "xgboost>=3.0" "scikit-learn>=1.5"
fi

for LEVEL in $LIST; do
    if [ ! -f "$DATASET/$LEVEL/meta.json" ]; then
        echo "no $LEVEL/meta.json in $DATASET - run get_dataset.py first" >&2
        exit 1
    fi
    WORK="${WORK:-/tmp/noaa-baseline-$LEVEL}"
    rm -rf "$WORK"
    mkdir -p "$WORK"
    cp "$HERE/train.py" "$HERE/validate.py" "$HERE/validate.sh" "$WORK/"
    python3 "$HERE/../code/materialize.py" "$DATASET" "$WORK" "$LEVEL"

    cd "$WORK"
    echo "== $LEVEL: contract: python train.py =="
    python3 train.py
    echo "== $LEVEL: contract: sh validate.sh =="
    sh validate.sh
    cd - >/dev/null
done

echo
echo "Compare against the recorded values in MANIFEST.json: temporal 0.8638, station_disjoint 0.8688."
echo "Both are eval AUC from the runner's own output, on the published bytes."
