# Feasibility report — October 12, 2026

**Selected backend: RawTherapee 5.13 PP3/CLI.** Real Canon EOS R7 C-RAW files were decoded and developed locally on arm64 macOS 27.0.1. Neither GUI was used for the parameter-generation/export tests. All originals tested retained their SHA-256 checksums. Existing source-directory edits were not passed to the processors.

## Measurements

| Backend and sample | Exposure | White balance | Color | Contrast | Repeated pixels |
|---|---|---|---|---|---|
| RawTherapee, daylight 0Z1A0621 | pass | pass | pass | pass | identical |
| RawTherapee, night 0Z1A0662 | pass | pass | pass | pass | identical |
| RawTherapee, indoor 0Z1A0650 | pass | pass | pass | pass | identical |
| darktable 5.6.2, daylight 0Z1A0621 | pass | pass | pass | pass | identical |
| darktable 5.6.2, indoor 0Z1A0650 | pass | pass | pass | direction check failed | identical |

Each property was tested separately against the same baseline: +1 EV, custom WB (RT Kelvin / DT sensor multipliers), increased saturation, and increased contrast. A successful command alone was insufficient: the output had to contain an ICC profile, normalized pixels had to change, and the relevant metric had to change in the expected direction. Contrast uses the rendered linear-luminance 90th–10th percentile spread; this is a narrow heuristic. darktable's indoor contrast edit changed pixels but reduced that spread, so the failed check does **not** establish that the slider was ignored.

Daylight mean absolute normalized RGB changes for RawTherapee: exposure 0.0868, WB 0.0686, color 0.0143, contrast 0.0306. darktable: exposure 0.0970, WB 0.0179, color 0.0111, contrast 0.0327. These magnitudes demonstrate effects, not equivalent scales or comparative image quality.

## Why PP3

RawTherapee profiles use readable named fields; the baseline is a complete profile saved by its CLI. Python changes exposure, WB, saturation, contrast, output ICC and resize fields while preserving other settings. No user defaults or adjacent source sidecars are applied. The implementation uses profile schema 353 for the tested 5.13 build; schema 351 has source-based support but was not exercised against an installed 5.11 engine.

The darktable proof packs module parameters into little-endian bytes and serializes a legacy XMP history. Its layouts were checked against the exact release source. It demonstrated GUI-free editing, but only for `basicadj` version 2 and `temperature` version 4. This is **not** a production adapter for exposure, color calibration, color balance RGB and sigmoid/filmic. Modern module ordering, camera WB, blend parameters and version migration remain work. A standards-valid XMP using an arbitrary namespace prefix initially failed import; the canonical `x` prefix succeeded. The failed probes and their logs remain in `validation`.

## End-to-end artifacts

Four CR3 inputs were analyzed, exported at full resolution and paired with editable `edit.pp3` and JSON recipes: daylight 0621, backlit 0626, indoor 0650, and night 0662. Conservative mode selected +0.25 EV for each and retained camera WB, saturation and contrast. Optional neutral-WB search was exercised on three files and retained camera WB. This is a conservative first result, not evidence that +0.25 EV is universally optimal.

The daylight replay produced **identical normalized pixels but different JPEG file bytes**. Reproducibility is assessed separately at both levels; byte-for-byte JPEG reproduction is not claimed. Command logs retain engine output; timestamps/metadata may differ. New recipes additionally fingerprint bundled processor resources and libraries, because matching a version string alone is inadequate.

The normal-exposure indoor example selected +1 EV and retained camera WB after evaluating five WB candidates. Its final replay also produced identical normalized pixels; explicit PP3 export completed with preservation checks. The complete test suite has 16 passing tests.

## Coverage and limits

ExifTool's Canon Quality tag identifies the supplied set as CRAW. Generic EXIF Compression describes the embedded JPEG and does not establish RAW compression. All 36 images are ISO 100. Full RAW, higher ISO, other cameras, HDR modes, bursts, and unusual CR3 variants remain untested. Subjective quality, camera color accuracy, lens corrections and skin-tone preservation have not been certified. Sidecars can be loaded and edited in RawTherapee; a GUI load/save round trip was not tested.

Final repeatable spike evidence is in `validation/final-spike-0650/evidence.json`; daylight and night evidence are also retained. `validation/darktable-0621/evidence.json` records the successful legacy-XMP daylight test. Tests use real files for integration and synthetic fixtures only for unit checks.

## Primary references

- [RawTherapee CLI documentation](https://github.com/RawTherapee/RawTherapee/blob/5.13/doc/manpage/rawtherapee.1)
- [RawTherapee 5.13 profile serialization](https://github.com/RawTherapee/RawTherapee/blob/5.13/rtengine/procparams.cc)
- [RawTherapee 5.13 profile version](https://github.com/RawTherapee/RawTherapee/blob/5.13/rtgui/ppversion.h)
- [darktable CLI manual](https://docs.darktable.org/usermanual/development/en/special-topics/program-invocation/darktable-cli/)
- [darktable 5.6.2 basic adjustments layout](https://github.com/darktable-org/darktable/blob/release-5.6.2/src/iop/basicadj.c)
- [darktable 5.6.2 WB layout](https://github.com/darktable-org/darktable/blob/release-5.6.2/src/iop/temperature.c)
- [darktable 5.6.2 XMP reader](https://github.com/darktable-org/darktable/blob/release-5.6.2/src/common/exif.cc)

Download URLs and local archive SHA-256 values are recorded in `tool-downloads.json`; these identify the fetched artifacts rather than independently authenticating their provenance.
