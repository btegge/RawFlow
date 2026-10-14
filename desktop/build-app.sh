#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
mkdir -p "$project_dir/RawFlow.app/Contents/MacOS" "$project_dir/work" "$project_dir/RawFlow.app/Contents/Resources"
/usr/bin/clang -x objective-c -framework Cocoa -Wl,-export_dynamic -Wall -Wextra "$project_dir/desktop/launcher.c" -o "$project_dir/work/RawFlow-launcher"
mv "$project_dir/work/RawFlow-launcher" "$project_dir/RawFlow.app/Contents/MacOS/RawFlow"
printf '%s\n' "$project_dir" > "$project_dir/RawFlow.app/Contents/Resources/project-path.txt"
if [ -n "${RAWFLOW_PYTHONHOME:-}" ]; then
    printf '%s\n' "$RAWFLOW_PYTHONHOME" > "$project_dir/RawFlow.app/Contents/Resources/python-home.txt"
elif [ ! -f "$project_dir/RawFlow.app/Contents/Resources/python-home.txt" ]; then
    echo 'Set RAWFLOW_PYTHONHOME to a Python 3.12 installation containing lib/libpython3.12.dylib.' >&2
    exit 1
fi
