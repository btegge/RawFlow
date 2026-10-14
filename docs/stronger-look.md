# Stronger automatic edits

The prior default capped exposure candidates at ±0.25 EV and usually left contrast and saturation unchanged. The new default is `--look punchy`; `--look natural` reproduces the previous selection policy.

Punchy expands exposure candidates up to +1.5 EV, then applies contrast +12, saturation +10, shadows +35 and highlights +25 in RawTherapee's slider units. These are applied in the RAW processor using PP3, before final export. Camera WB stays the default, keeping night-stage lighting intact.

The processor renders the selected exposure-only preview and then the strongest styled candidate. Styling must keep added rendered channel clipping below 0.5 percentage points and must retain at least 85% of exposure-only median luminance. Otherwise it tests half strength and then neutral styling. Each decision is retained in `recipe.json`. The final full-resolution render is checked against the selected styled preview. Exposure search still penalizes highlight clipping, so a bright sun or white surfaces can limit global brightening.

Shadow and highlight controls use the named keys from the previously downloaded RawTherapee 5.13 `procparams.cc` source. Existing backend evidence still identifies the same processor binary, bundled assets, and base PP3. New actual-file renders exercise these additional controls. Tests cover low-key colored scenes, bright scenes, clipping rejection, unwanted darkening and parameter bounds.

Results and preservation checks are recorded in `validation/stronger-look.json`. `outputs/comparison.jpg` shows previous edits on the left and stronger edits on the right. Full-resolution images and editable sidecars are under `outputs/punchy/`. Original files and previous exports remain unchanged.

All four samples accepted full-strength styling. Selected exposures were +0.75 EV (daylight), +1.25 EV (backlit portrait), +1.5 EV (indoor), and +0.75 EV (night stage). Original checksums were unchanged. The new daylight recipe replayed with identical normalized pixels; JPEG bytes differed as in the initial implementation. All 23 tests passed.
