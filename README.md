# RawFlow

A local, non-destructive Canon EOS R7 CR3 editor for Apple Silicon macOS. RawTherapee develops the RAW files, Python analyzes color-managed previews, and a desktop interface provides batch editing and before/after comparisons. Original RAW files and adjacent sidecars stay untouched.

## Features

- Dark desktop interface with the RawFlow icon, subtle control borders, background processing, and safe stopping between photos.
- Six looks: **Natural**, **Punchy**, **Saturated**, **Black and white**, **Filmic**, and **Arty**.
- Three strengths: **Low** preserves the original preset amounts; **Medium** allows 25% stronger adjustments; **High** allows 50% more than Low. Integer sliders round to supported steps. Natural keeps neutral contrast/color and increases its exposure allowance.
- Quick cached draft previews, followed by actual RAW previews during processing and the final export at completion. Drafts approximate the camera JPEG; final RAW results can differ.
- Final JPEGs only in the selected output batch. Editable PP3 profiles, recipes and logs stay in a separate working directory.
- A scriptable CLI, compatibility checks, and strict pixel replay for recorded edits.

On the tested daylight sample, export time decreased from 41 seconds to roughly 13 seconds. Four tested scenes exported in about 12–13 seconds with camera white balance. Optional neutral-color WB search takes longer. See [performance measurements](docs/performance.md).

## Installation

### On the already configured Mac

For an installation with configured local dependencies, open the source checkout. The Python runtime and processors are already configured. Double-click **RawFlow.app** or **launch-gui.command** in that folder.

From Terminal:

```sh
cd /path/to/RawFlow
./run-local.sh doctor
./launch-gui.command
```

`run-local.sh` reads optional machine-specific paths from ignored `work/local-env.sh`; the GUI reads optional `work/local-tools.json`. Keep those dependencies available. The included app is configured for this Mac; it is not a standalone installer.

### On a fresh Apple Silicon Mac

1. Clone or download this repository into a permanent, writable folder. Keep `rawflow/`, `profiles/`, and the other project files together:

   ```sh
   git clone https://github.com/btegge/RawFlow.git
   cd RawFlow
   ```
2. Install Python with Tk support from the [official macOS downloads](https://www.python.org/downloads/macos/). The tested runtime is Python 3.12; the project requires Python 3.11 or newer. Confirm Tk works before launching the desktop interface.
3. Install **RawTherapee 5.13** from its [official downloads](https://www.rawtherapee.com/downloads/), placing the application in `/Applications`. This is the processor version demonstrated with the supplied CR3 files and PP3 profile. Other versions require new compatibility evidence and may need adapter changes.
4. Install **ExifTool** using its [official distribution](https://exiftool.org/). It supplies camera metadata and embedded preview extraction.
5. Open Terminal in the source folder and install the Python package:

```sh
python3 --version
python3 -m tkinter
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-tested.txt
.venv/bin/python -m pip install --no-deps -e .
```

The Tk command should open a small test window; close it before continuing. If `python3` selects a different installation, use the full path to your intended Python executable. `requirements-tested.txt` pins NumPy and Pillow to the tested versions.

Configure the executable paths in the same Terminal session:

```sh
export RAWFLOW_RAWTHERAPEE_CLI='/Applications/RawTherapee.app/Contents/MacOS/rawtherapee-cli-bin'
export RAWFLOW_EXIFTOOL='/usr/local/bin/exiftool'
.venv/bin/rawflow doctor
```

Replace the ExifTool path with your actual installation location. Prefer RawTherapee's `rawtherapee-cli-bin` when present: the macOS wrapper can detach from the calling process. If your bundle has a different layout, locate its CLI and confirm it runs synchronously. `doctor` must report the processor and ExifTool as available.

Darktable is optional for the backend comparison, not required for normal edits. To include it, install the tested darktable 5.6.2 build and set `RAWFLOW_DARKTABLE_CLI` to its CLI executable.

### Validate a real CR3 before editing

Compatibility records are tied to the processor binary, bundled assets and base profile. The record from another Mac does not automatically validate your installation. Supply one of your actual Canon EOS R7 CR3 files:

```sh
.venv/bin/rawflow spike /absolute/path/to/sample.CR3 \
  --base profiles/neutral-rt5.13.pp3 \
  --out validation/my-installation
```

Use a new output directory for every spike. Inspect the rendered sample images and `validation/my-installation/evidence.json`. The RawTherapee result must pass and report the original preserved before automatic editing is enabled. The spike creates diagnostic images and logs; it does not use the JPEG-only export layout.

Start the desktop interface from the same Terminal session:

```sh
.venv/bin/rawflow-gui
```

In **Setup**, select your processor, ExifTool, base PP3 and new compatibility record. Save the setup. You can also add a CR3 to the queue and use **Validate selected sample** to run the compatibility check through the interface. Settings are remembered in `work/desktop-settings.json`.

The repository includes app metadata and icon artwork, but excludes the compiled launcher and machine-specific runtime paths. The local `RawFlow.app` and `launch-gui.command` depend on a configured embedded Python 3.12 runtime. On a fresh installation, use `rawflow-gui` as above. `desktop/build-app.sh` rebuilds the native launcher for the configured embedded runtime; it does not bundle dependencies or create a portable installer. Rebuilding requires Apple's command-line developer tools.

## Using the desktop app

1. Add photos or a folder of CR3 files.
2. Select a look and strength. The draft preview updates in the background.
3. Choose brightness and white balance. **Camera white balance** is fastest and preserves colored lighting; **Find neutral colors** performs an optional temperature search.
4. Choose a save folder and select **Edit all photos**.
5. Use **Show exports** to reveal the JPEG batch, or **Open batch** to reopen completed edits.

Each run creates a dated folder containing only final JPEGs. **Stop after this photo** finishes the current export and skips the remaining queue. Quitting during processing requests the same safe stop.

Keyboard shortcuts: Command-O adds photos, Command-Return edits the queue, Command-Shift-O opens a batch, Command-comma opens Setup, and Command-Q quits safely. See [desktop usage](docs/desktop.md).

## CLI examples

On this configured Mac, replace `.venv/bin/rawflow` below with `./run-local.sh` and use `validation/backend-evidence.json` for the existing matching processor installation.

```sh
.venv/bin/rawflow edit '/absolute/path/to/photos/*.CR3' \
  --base profiles/neutral-rt5.13.pp3 \
  --evidence validation/my-installation/evidence.json \
  --out exports --look punchy --strength medium
```

Look names are `natural`, `punchy`, `saturated`, `black-and-white`, `filmic`, and `arty`. Strength names are `low`, `medium`, and `high`; defaults are Punchy and Low. Optional policies are `--scene preserve|normal` and `--wb camera|neutral-search`.

The CLI expands quoted globs, publishes numbered JPEGs including look and strength, refuses to overwrite existing files, and prints separate recipe paths. It stops on the first error; the desktop continues with remaining photos.

Replay a recorded edit:

```sh
.venv/bin/rawflow replay /absolute/path/to/sample.CR3 \
  --recipe work/edits/RECORD-ID/recipe.json \
  --out validation/replay-check
```

Replay requires the same original bytes, engine identity and unchanged PP3. It compares normalized pixels and reports JPEG byte equality separately. Use a new diagnostic destination for each replay.

To render a manually revised PP3 and record a fresh recipe:

```sh
.venv/bin/rawflow export /absolute/path/to/sample.CR3 \
  --profile /absolute/path/to/revised.pp3 --out revised-export
```

This advanced command creates a complete processing workspace, including its profile, recipe and input copy. The normal desktop/CLI `edit` path publishes only final JPEGs to the destination.

## Records, color management and configuration

Normal edit records live in `work/edits/RECORD-ID/`: `edit.pp3`, `recipe.json`, previews and command logs. Set `RAWFLOW_WORK_DIR` to relocate them. Keep records and exports at their recorded paths to reopen batches. Older batches with inline recipes remain supported. Open the original RAW in RawTherapee and load its saved PP3 to continue editing manually.

The renderer receives a checksum-verified, read-only RAW copy, removed after normal processing completes or fails. RawFlow never writes sidecars beside source photographs. Previews request RTv4_sRGB and are normalized through Pillow/LittleCMS before linear-luminance analysis. Final exports are full-resolution, color-tagged 8-bit JPEGs. Metrics describe rendered clipping, not irrecoverable sensor clipping.

Recipes record source/profile/export checksums, processor identity, settings, strength, metadata and normalized pixel hashes. Changing processor builds, assets or the base PP3 requires another spike. Filmic is a built-in tonal look rather than an emulation of a named film stock. Higher strength increases allowances; scene-dependent exposure selection and clipping protection can limit the final change.

`RAWFLOW_THREADS` overrides the default renderer thread count of up to four. Tool overrides are `RAWFLOW_RAWTHERAPEE_CLI`, `RAWFLOW_EXIFTOOL`, and optional `RAWFLOW_DARKTABLE_CLI`. Use absolute executable paths.

## Troubleshooting

- **Tk unavailable:** install a Python distribution with working Tk support; verify `python3 -m tkinter` before creating the environment.
- **Processor or ExifTool missing:** check executable paths with `doctor` or correct them in Setup.
- **Matching evidence required:** run a fresh spike with the installed processor and selected base profile, then choose its evidence file.
- **No preview:** a photo may lack an extractable embedded camera JPEG; RAW rendering may still work.
- **No completed edits found:** keep the separate processing records and the JPEGs at their recorded paths.
- **App stops launching after moving dependencies:** use the Python entry point or update the configured native launcher paths and rebuild.

## Validation and limits

The automated suite has 41 passing tests, covering source preservation, evidence checks, JPEG publication, replay hashing, preset strengths and job coordination:

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Actual-file validation includes six presets, Medium/High exports, four lighting scenes, identical-pixel replay and desktop editing. The provided samples are Canon C-RAW at ISO 100. Full RAW and higher ISO still need validation. Camera-profile fidelity, lens corrections, skin tones and broader lighting conditions need further review. There is no calibrated aesthetic score, ML optimization or TIFF export.

See [feasibility](docs/feasibility.md), [performance](docs/performance.md), [desktop documentation](docs/desktop.md), and [milestones](docs/milestones.md). RawFlow uses the MIT license; Python, Tk, Pillow, NumPy and the external processors retain their own licenses.
