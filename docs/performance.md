# Faster editing and six presets — 0.4

Validated on this Mac on October 14, 2026, with the supplied Canon EOS R7 C-RAW samples and the same RawTherapee 5.13 build/base profile.

## Measured performance

| Operation | Measured time |
|---|---:|
| Previous pipeline, daylight Punchy export | 41.3 s |
| Updated pipeline, daylight Punchy export, fresh process | 12.9 s |
| Updated backlit portrait / indoor / stage Punchy exports | 11.7 / 12.4 / 11.9 s |
| First embedded camera preview extraction and display-image preparation | 0.62 s |
| Cached draft generation for each of six presets | 0.033–0.036 s |
| RAW-rendered preview, camera WB (initial six-preset run) | 5.1–6.2 s |

The same-sample export comparison is about 3.2× faster (69% less time). These are individual local runs, not a broad hardware benchmark. Draft timings exclude Tk event delivery/redraw; the UI drains events every 100 ms. Optional neutral-color WB search adds RAW renders and therefore takes longer. Black-and-white bypasses that search because neutral-color scoring is meaningless after desaturation.

## Changes

- Estimate candidate exposure on a single linearized, ICC-normalized preview, then verify the chosen preset with an actual RAW render. Normally three developments: baseline preview, edited preview, final JPEG. Excess preview clipping can add one corrected preview; optional color WB search adds up to five.
- Run the renderer with up to four threads rather than forcing one. Set `RAWFLOW_THREADS` to override.
- Cache engine content identity while all executable and bundled asset stat fingerprints remain unchanged. Changing an asset invalidates the cache and still requires matching compatibility evidence.
- Calculate full-resolution pixel checksums in small strips instead of building giant float64 arrays. The hash remains compatible with existing replay records. Final statistics use a color-managed 1200-pixel image; export pixels remain full-resolution.
- Decode display JPEGs at reduced resolution and cache camera previews for twelve photos. Use a single background preview worker, cancel queued obsolete requests, and reject stale results.
- Publish only the finished JPEG to the selected output batch. Keep PP3 profiles, JSON recipes, previews and logs in `work/edits/` (or `RAWFLOW_WORK_DIR`). Delete temporary isolated RAW copies after success or failure; originals and adjacent sidecars stay untouched. Existing historical batches are not changed.

The new exposure estimate can choose a different result from the exhaustive v2 search. A draft applies a lightweight approximation to the camera JPEG; it is explicitly labeled **Draft** and is not pixel-identical to the RAW result. It is replaced by a RAW preview during processing and the final image at completion.

## Presets

| Preset | Treatment |
|---|---|
| Natural | Restrained exposure, neutral contrast/color |
| Punchy | Brighter shadows, richer contrast and color |
| Saturated | More intense color with moderate contrast |
| Black and white | Neutral monochrome, stronger contrast |
| Filmic | Lifted blacks, softer contrast, subdued color and compressed whites |
| Arty | Strong contrast and saturation with creative RGB color curves |

Filmic is a tonal style, not a named film-stock simulation. All six were rendered end-to-end from a real R7 CR3. Monochrome has equal RGB channels after color normalization; Saturated has greater mean saturation than Punchy; all six outputs differ. The comparison is in `work/performance/presets.jpg`, with full JPEGs in `outputs/presets-v3/`.

## Verification

38 automated tests pass, including unchanged originals/adjacent sidecars, cleanup on failure, no overwriting, JPEG-only publication, separate-record reopening, bounded-hash compatibility, engine-cache invalidation, distinct drafts, and skipping monochrome WB search.

Four real scenes exported successfully with preserved original checksums. A saved recipe replay produced identical normalized pixels (JPEG file bytes differ). GUI testing verified visible preset controls, immediate monochrome draft selection, and a completed real monochrome export with only one JPEG in the batch folder. Initial UI testing was blocked by the lock screen; it was completed after the user unlocked the Mac.

Benchmark records: `work/performance/before.json`, `after.json`, `final.json`; replay evidence: `work/performance/replay-final/replay.json`; consolidated evidence: `validation/performance-v3.json`.

The existing full-RAW/high-ISO and camera-profile validation limitations in `feasibility.md` still apply.
