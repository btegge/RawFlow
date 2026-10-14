# RawFlow desktop app

Double-click `RawFlow.app` in this project to open the editor. `launch-gui.command` opens the same app. The app uses the existing local Python runtime and RAW processor; nothing is uploaded.

1. Choose **Add photos** or **Add folder**. A folder adds CR3 files directly inside it, without recursively importing unrelated subfolders.
2. Choose a look. **Natural**, **Punchy**, **Saturated**, **Black and white**, **Filmic**, and **Arty** are available as visible preset buttons. **Preserve the scene** keeps night scenes darker; **Brighten toward daylight** permits stronger brightening. Keep camera WB for colored stage lighting; **Find neutral colors** enables the optional search.
3. Pick a save folder and choose **Edit all photos**. Each run creates a fresh dated batch folder. Completed exports are kept if another photo fails.
4. Select a photo to compare its neutral RAW development with the final edit. Before editing, the viewer shows the camera JPEG on the left and an approximate preset draft on the right. Selecting a preset updates the draft without waiting for a RAW export. A RAW-rendered edited preview replaces it during processing. After editing it uses the pipeline's neutral RAW preview, so it compares the same development engine.
5. **Show exports** reveals the selected edit folder in Finder. It contains only final JPEGs. Profiles, recipes, logs and previews are kept in the project’s `work/edits/` directory, outside your destination. Temporary RAW copies are removed after processing.

**Open batch** loads previous complete RawFlow outputs using the separate records; keep those records and keep exports at their recorded paths. Older batches with inline recipes remain supported. It skips incomplete or malformed recipes, and can use the preserved input copy if the original moved. Failed photos stay marked in the queue; select them to read the error.

**Stop after this photo** completes the active edit, then skips remaining photos. Closing or quitting while busy requests the same safe stop and closes after the worker finishes. This can take as long as the current photo. A compatibility check also finishes before closing. It does not interrupt a processor halfway through an export.

## Keyboard shortcuts

- Command-O: add photos.
- Command-Return: edit the queue.
- Command-Shift-O: open an existing batch.
- Command-comma: processing setup.
- Command-Q: finish the current photo and quit.

Options, save folder, processor location and compatibility record are remembered in the project's `work/desktop-settings.json`. Original source files and existing sidecars are not modified.

## Processing setup

The defaults point to the processor and ExifTool downloaded during the feasibility spike, and the existing validated profile/evidence in this project. Use **Setup** to change these paths. After a processor or base-profile change, **Validate selected sample** runs the actual CR3 compatibility spike and records new evidence. Editing still requires matching successful evidence; the GUI cannot bypass that gate.

Previews are decoded in a background thread, normalized to sRGB when an embedded ICC profile is present, and scaled to fit. RAW export and analysis still use the established color-managed pipeline. Display previews are not a replacement for a calibrated proofing workflow.

## Implementation and portability

The interface uses Python, Tk/Tcl and Pillow, all open source. Job coordination is independent from the desktop widgets; processor work runs off the UI thread and emits queued progress and completion events. The CLI remains available.

The macOS app contains a small native C launcher embedding the existing Python runtime, so Cocoa identifies it as RawFlow. It is configured for this Mac and project; it is not a self-contained distribution. Its project and runtime paths are stored in app resources. If moving the source or Python runtime, update those resource paths or rebuild. The editable source lives in `rawflow/gui.py`, `rawflow/gui_jobs.py` and `desktop/launcher.c`.

For another Python environment, install Tk support and the project dependencies, then run `python -m rawflow.gui` or the installed `rawflow-gui` entry point. Set processor/metadata paths through Setup as needed and validate a sample on that environment.

## Validation on this Mac

The original desktop validation had 31 passing tests. A real R7 CR3 was selected through the native file chooser and edited through the GUI. The window displayed live processing stages, a Done status, and the before/after result. Its original SHA-256 stayed unchanged and the export matched the previously validated Punchy pixel checksum. The packaged app was relaunched successfully and loaded all four prior edits using Open batch. Evidence is saved in `validation/desktop-verification.json`.

## Faster presets (0.4)

See [performance and validation](performance.md). Drafts are cached for up to twelve photos, computed at display resolution off the UI thread, and explicitly approximate camera-JPEG previews. The final RAW result may differ in exposure, white balance, color and recovered detail. **Camera white balance** is fastest; **Find neutral colors** adds up to five RAW renders. The processing engine uses up to four threads by default (`RAWFLOW_THREADS` overrides this).

## Strength and modern interface (0.5)

Each look has Low, Medium and High strength buttons, remembered between sessions. Low preserves the 0.4 preset values. Medium scales adjustment and exposure limits by 1.25; High scales them by 1.50 (an additional 25 percentage points over Low). Integer sliders round to the nearest supported step. This includes contrast, saturation, shadow/highlight amounts and creative curve deviations. Natural retains neutral color/contrast, with a wider exposure allowance at higher strengths. White balance and highlight-clipping protection remain scene-dependent, so a higher allowance does not guarantee a proportionally brighter result.

The CLI accepts `--strength low|medium|high`. Recipes record strength and factor; filenames include strength. The interface uses a dark palette, button-style preset selectors and strength segments, plus dark preview panels.

## App identity and control borders

The packaged launcher exports a small Cocoa icon setter, called after Tk initializes its application. It assigns the full-size bundled icon to the running NSApplication for Dock and app-switcher identity. The same artwork appears in the editor header. Fields, photo-list borders, scrollbars and the progress bar use dark low-contrast outlines; focused input fields retain a subtle blue indication. The launcher is compiled as Objective-C with Cocoa support by `desktop/build-app.sh`.
