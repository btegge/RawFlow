#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -f "$project_dir/work/local-env.sh" ]; then
    . "$project_dir/work/local-env.sh"
fi
export PYTHONPATH="$project_dir${PYTHONPATH:+:$PYTHONPATH}"
exec "${RAWFLOW_PYTHON:-python3}" -m rawflow.cli "$@"
