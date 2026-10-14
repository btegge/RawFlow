# Staged acceptance criteria

1. **Feasibility:** R7 metadata, true RAW decoding, independently generated sidecars for exposure/WB/color/contrast; changed pixels and expected directions; repeat renders; original checksums. Record exact engine and profile schema. RawTherapee chosen only after this gate. darktable production support needs a separate gate; the legacy basicadj probe is insufficient for a scene-referred production workflow.
2. **Reproducible CLI:** isolated engine settings; immutable working copies; no original-adjacent writes; full PP3; explicit ICC output; recipe and subprocess logs; replay original recipe and compare pixels. Tests must reject silent failures, stale versions, missing ICC, and overwrite attempts.
3. **Conservative editing:** deterministic candidate exposures; rendered clipping checks; optional neutral-region WB search in the RAW engine; modest color/contrast candidates; defaults preserve camera WB and scene intent. Compare daylight, backlit people, indoor mixed light, and colored night lighting. Human review is required to assess photographic quality, even after objective checks pass.
4. **Broader validation:** representative full RAW and C-RAW; multiple ISO settings, lenses and WB conditions; darktable version-pinned modern modules if worthwhile; 16-bit TIFF workflow; lens corrections after engine/profile validation; batch lighting consistency and user preference calibration. Not completed by this initial spike.

A tested file is evidence for that file and engine build, not certification of every CR3 variant. No machine learning in this version. Unit fixtures are never counted as real CR3 validation.

## 0.4 — faster editing, clean outputs, six presets

Completed: three-render default path, bounded pixel hashing, engine identity caching, four-thread rendering, immediate cached draft previews, early RAW previews, six presets, and JPEG-only batch destinations with separate editable records. Validated on four CR3 scenes, all six presets, strict pixel replay, and the desktop UI. See `performance.md` for measured timings and remaining limits.

## 0.6 — multi-camera stages 1 and 2

Completed: shared candidate format list, generic optional metadata, non-RAW content rejection, per-file decode reporting, mixed-file batch failures, expanded preview extraction and persistent RAW-render fallback. Stage 3 is pending other-camera samples; no broader camera compatibility is claimed.
