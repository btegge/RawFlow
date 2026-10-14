#!/bin/bash
# Install a per-user RawFlow runtime and a Finder launcher.
set -euo pipefail

fail() { printf 'RawFlow installer: %s\n' "$*" >&2; exit 1; }
[[ "$(uname -s)" == Darwin ]] || fail 'This installer requires macOS.'
[[ "$(uname -m)" == arm64 ]] || fail 'Use a native Terminal on an Apple Silicon Mac (not Rosetta).'
[[ "$EUID" -ne 0 ]] || fail 'Run as your normal user, without sudo. Administrator access is requested when needed.'
project_dir=$(cd -- "$(dirname -- "$0")" && pwd)
for required in rawflow profiles pyproject.toml requirements-tested.txt RawFlow.app/Contents/Info.plist; do
    [[ -e "$project_dir/$required" ]] || fail "Missing source file: $required. Run from a complete checkout."
done

# Homebrew also installs Apple's Command Line Tools when needed; its installer
# may ask for a password or require completion of Apple's installation dialog.
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
if ! command -v brew >/dev/null 2>&1; then
    bootstrap=$(mktemp -t rawflow-homebrew)
    trap 'rm -f "$bootstrap"' EXIT
    /usr/bin/curl --fail --show-error --location https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh -o "$bootstrap"
    /bin/bash "$bootstrap"
    command -v brew >/dev/null 2>&1 || fail 'Homebrew installation did not finish. Complete its instructions and rerun this script.'
fi
brew_bin=$(command -v brew)
python="$("$brew_bin" --prefix)/bin/python3.12"
if [[ ! -x "$python" ]]; then
    "$brew_bin" install python@3.12
fi
if ! "$python" -c 'import tkinter; import _tkinter' >/dev/null 2>&1; then
    "$brew_bin" install python-tk@3.12
fi
"$python" -c 'import tkinter; import _tkinter' || fail 'Python 3.12 Tk support is unavailable.'

exiftool=$(command -v exiftool || true)
if [[ -z "$exiftool" ]]; then
    "$brew_bin" install exiftool
    exiftool=$(command -v exiftool)
fi
"$exiftool" -ver
find_processor() {
    local candidate
    for candidate in /Applications/RawTherapee.app/Contents/MacOS/rawtherapee-cli-bin \
        /Applications/RawTherapee.app/Contents/MacOS/rawtherapee-cli; do
        if [[ -x "$candidate" ]]; then printf '%s\n' "$candidate"; return; fi
    done
    command -v rawtherapee-cli
}
processor=$(find_processor || true)
if [[ -z "$processor" ]]; then
    "$brew_bin" install --cask rawtherapee
    processor=$(find_processor || true)
fi
[[ -n "$processor" ]] || fail 'RawTherapee CLI was not found after installation.'

# Each installation has a stable path: virtual environments cannot be relocated.
# Keep previous versions and user work intact when installing an update.
support="$HOME/Library/Application Support/RawFlow"
mkdir -p "$support/versions"
install_dir=$(mktemp -d "$support/versions/install-XXXXXXXX")
cp -R "$project_dir/rawflow" "$project_dir/profiles" "$install_dir/"
cp "$project_dir/pyproject.toml" "$project_dir/requirements-tested.txt" "$project_dir/LICENSE" "$install_dir/"
mkdir -p "$install_dir/work" "$install_dir/validation" "$install_dir/RawFlow.app/Contents/Resources"
cp "$project_dir/RawFlow.app/Contents/Resources/RawFlow.icns" "$install_dir/RawFlow.app/Contents/Resources/"
"$python" -m venv "$install_dir/.venv"
"$install_dir/.venv/bin/python" -m pip install --upgrade pip
"$install_dir/.venv/bin/python" -m pip install -r "$install_dir/requirements-tested.txt"
"$install_dir/.venv/bin/python" -m pip install --no-deps --editable "$install_dir"
"$install_dir/.venv/bin/python" - "$install_dir" "$processor" "$exiftool" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
(root / 'work/local-tools.json').write_text(json.dumps({
    'RAWFLOW_RAWTHERAPEE_CLI': sys.argv[2], 'RAWFLOW_EXIFTOOL': sys.argv[3]
}, indent=2) + '\n')
PY
RAWFLOW_RAWTHERAPEE_CLI="$processor" RAWFLOW_EXIFTOOL="$exiftool" \
    "$install_dir/.venv/bin/rawflow" doctor
"$install_dir/.venv/bin/python" -c 'import tkinter, numpy; from PIL import Image, ImageTk, ImageCms'

app="$install_dir/launcher/RawFlow.app"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
cp "$project_dir/RawFlow.app/Contents/Info.plist" "$app/Contents/"
cp "$project_dir/RawFlow.app/Contents/Resources/RawFlow.icns" "$app/Contents/Resources/"
printf '%s\n' "$install_dir" > "$app/Contents/Resources/project-path.txt"
cat > "$app/Contents/MacOS/RawFlow" <<'LAUNCHER'
#!/bin/bash
set -euo pipefail
contents=$(cd -- "$(dirname -- "$0")/.." && pwd)
IFS= read -r project < "$contents/Resources/project-path.txt"
unset PYTHONHOME PYTHONPATH
cd -- "$project"
mkdir -p work
exec "$project/.venv/bin/python" -m rawflow.gui >> work/launcher.log 2>&1
LAUNCHER
chmod +x "$app/Contents/MacOS/RawFlow"
/usr/bin/plutil -lint "$app/Contents/Info.plist"
# Do not overwrite an existing app until all dependency checks have passed.
if [[ -w /Applications ]]; then
    if [[ -e /Applications/RawFlow.app ]]; then
        mv /Applications/RawFlow.app "/Applications/RawFlow.backup-$(date +%Y%m%d-%H%M%S)-$$.app"
    fi
    cp -R "$app" /Applications/RawFlow.app
else
    sudo -v
    if [[ -e /Applications/RawFlow.app ]]; then
        sudo mv /Applications/RawFlow.app "/Applications/RawFlow.backup-$(date +%Y%m%d-%H%M%S)-$$.app"
    fi
    sudo cp -R "$app" /Applications/RawFlow.app
fi
printf '\nInstalled /Applications/RawFlow.app\nRuntime and logs: %s\n' "$install_dir"
printf 'Open RawFlow, then use Setup > Validate selected sample with one of your RAW files before editing.\n'
printf 'On updates, select your previous settings/evidence paths in Setup if still compatible.\n'
