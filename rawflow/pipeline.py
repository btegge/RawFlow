from pathlib import Path
import json
import platform
import sys
import time
from .presets import PRESETS, STRENGTHS, preset_settings
import numpy as np
from .core import *


def spike(raw, base, out, dt_profiles=None):
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {'schema': 1, 'status': 'incomplete', 'environment': doctor(),
              'rawtherapee': {'status': 'not-tested'},
              'darktable': {'status': 'not-tested', 'parameter_generation': 'not-demonstrated'}}
    save_json(out / 'evidence.json', report)
    generated_dt = False
    if dt_profiles is None and locate('darktable-cli'):
        try:
            from .darktable_spike import generate_profiles
            dt_profiles = generate_profiles(out / 'generated-xmp')
            generated_dt = True
        except Exception as e:
            report['darktable']['generation_error'] = str(e)
    with protected_input(raw, out / 'input') as (copy, raw_hash):
        report.update(source_sha256=raw_hash, metadata=metadata(copy), base_sha256=digest(base))
        for engine in ('rawtherapee', 'darktable'):
            try:
                arrays = {}
                profile_hashes = {}
                for name in ('baseline', 'repeat', 'exposure', 'white_balance', 'color', 'contrast'):
                    profile_name = 'baseline' if name == 'repeat' else name
                    if engine == 'rawtherapee':
                        overrides = {'exposure': {'exposure': 1.},
                                     'white_balance': {'wb': 'Custom', 'temperature': 3000},
                                     'color': {'saturation': 25}, 'contrast': {'contrast': 25}}
                        profile = out / f'rt-{name}.pp3'
                        profile.write_text(profile_text(base, preview=True, **overrides.get(profile_name, {})))
                        image = render_rt(copy, profile, out / f'rt-{name}.jpg')
                    else:
                        if not dt_profiles:
                            raise RuntimeError('Need baseline/exposure/white_balance/color/contrast XMP profiles; no binary parameter writer validated.')
                        profile = Path(dt_profiles) / f'{profile_name}.xmp'
                        image = out / f'dt-{name}.jpg'
                        render_dt(copy, profile, image, out / f'dt-config-{name}')
                    profile_hashes[name] = digest(profile)
                    arrays[name] = pixels(image)
                checks = {k: compare(arrays['baseline'], arrays[k], k)
                          for k in ('exposure', 'white_balance', 'color', 'contrast')}
                repeat = pixel_hash(arrays['baseline']) == pixel_hash(arrays['repeat'])
                report[engine] = {'status': 'passed' if repeat and all(c['passed'] for c in checks.values()) else 'failed',
                                  'checks': checks, 'repeat_pixels_equal': repeat,
                                  'profile_hashes': profile_hashes,
                                  'parameter_generation': 'python-pp3' if engine == 'rawtherapee' else ('python-legacy-xmp-probe' if generated_dt else 'supplied-xmp-only')}
            except Exception as e:
                report[engine] = {'status': 'failed', 'error': str(e)}
            save_json(out / 'evidence.json', report)
    report['original_preserved'] = digest(raw) == report['source_sha256']
    report['status'] = 'complete'
    report['rt_identity'] = rt_identity() if report['rawtherapee']['status'] == 'passed' else None
    report['scope'] = 'This sample only; visually inspect renders. A pass does not certify other cameras or RAW modes.'
    save_json(out / 'evidence.json', report)
    return report


def require_evidence(evidence, base):
    d = json.loads(Path(evidence).read_text())
    if not (d.get('status') == 'complete' and d.get('original_preserved') and
            d.get('rawtherapee', {}).get('status') == 'passed' and d.get('rt_identity') == rt_identity() and
            d.get('base_sha256') == digest(base)):
        raise RuntimeError('Matching successful RAW/PP3 engine-control evidence required before auto editing.')
    return d


def score(stats, baseline, amount):
    # Conservative objective, not an aesthetic beauty predictor.
    clipping_penalty = max(0., stats['clipped_channels'] - baseline['clipped_channels']) * 100
    return abs(np.log2(max(stats['p50'], 1e-6) / .18)) + clipping_penalty + .3 * abs(amount)


def punchy_center(baseline, scene):
    night = baseline['p50'] < .035 and baseline['saturation'] > .35
    limit = .5 if night and scene == 'preserve' else 1.25
    return float(np.clip(np.log2(.18 / max(baseline['p50'], 1e-6)), -.75, limit))


def look_acceptable(stats, reference):
    return (stats['clipped_channels'] <= reference['clipped_channels'] + .005
            and stats['p50'] >= reference['p50'] * .85)


def process(raw, base, evidence, out, scene='preserve', wb='camera', look='punchy', on_progress=None, strength='low'):
    def progress(label):
        if on_progress is not None:
            on_progress(label)

    factor = STRENGTHS[strength]
    started = time.monotonic()
    progress('Checking compatibility')
    if look not in PRESETS:
        raise ValueError('Unknown look')
    proof = require_evidence(evidence, base)
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    manifest = {'schema': 1, 'status': 'incomplete', 'algorithm': ALGORITHM,
                'engine': rt_identity(), 'python': platform.python_version(),
                'numpy': np.__version__, 'render_threads': os.environ.get('RAWFLOW_THREADS', str(min(4, os.cpu_count() or 1))), 'base_sha256': digest(base), 'evidence_sha256': digest(evidence),
                'scene': scene, 'look': look, 'strength': strength, 'strength_factor': factor, 'white_balance_policy': wb, 'input': str(Path(raw).resolve())}
    save_json(out / 'recipe.json', manifest)
    with protected_input(raw, out / 'input', remove_copy=True) as (copy, raw_hash):
        progress('Reading camera information')
        manifest.update(source_sha256=raw_hash, metadata=metadata(copy))
        base_preview = out / 'baseline.pp3'
        base_preview.write_text(profile_text(base, preview=True))
        progress('Developing the original preview')
        try:
            baseline_rgb = pixels(render_rt(copy, base_preview, out / 'baseline.jpg'))
        except Exception as e:
            manifest['decoding'] = {'status': 'failed', 'error': str(e)}
            save_json(out / 'recipe.json', manifest)
            raise RuntimeError(f'Unable to decode this RAW file with the installed processor: {e}') from e
        if not np.isfinite(baseline_rgb).all() or min(baseline_rgb.shape[:2]) < 2:
            raise ValueError('RAW decoding returned an invalid preview')
        manifest['decoding'] = {'status': 'passed', 'method': 'RAW engine render with embedded ICC',
                                'preview_dimensions': list(baseline_rgb.shape[:2]),
                                'scope': 'This file decoded; visual color correctness is not certified'}
        save_json(out / 'recipe.json', manifest)
        baseline = statistics(baseline_rgb)
        # Score exposure estimates on the already decoded linear preview. This
        # avoids a fresh full RAW demosaic for every quarter-stop candidate.
        center = float(np.clip(np.log2(.18 / max(baseline['p50'], 1e-6)), -.75, .75)) if scene == 'normal' else 0.
        if look != 'natural':
            center = punchy_center(baseline, scene)
        center *= factor
        exposures = sorted(set(round(float(np.clip(x, -1.5*factor, 1.5*factor)), 2) for x in (0., center-.25*factor, center, center+.25*factor)))
        linear = np.where(baseline_rgb <= .04045, baseline_rgb / 12.92, ((baseline_rgb + .055) / 1.055) ** 2.4)
        candidates = []
        for ev in exposures:
            adjusted = np.clip(linear * 2**ev, 0, 1)
            estimated = np.where(adjusted <= .0031308, adjusted*12.92, 1.055*adjusted**(1/2.4)-.055)
            stat = statistics(estimated)
            candidates.append({'exposure': ev, 'stats': stat, 'score': float(score(stat, baseline, ev)), 'estimated': True})
        chosen = min(candidates, key=lambda c: c['score'])
        settings = dict(preset_settings(look, strength), exposure=chosen['exposure'])
        look_candidates = []
        wb_candidates = []
        if wb == 'neutral-search' and not settings.get('monochrome'):
            # Search in the RAW engine, never convert RGB gains directly to Kelvin.
            temps = [None, 3500, 5000, 6500, 8000]
            mask = (baseline_rgb.max(axis=2) - baseline_rgb.min(axis=2) < .06) & (baseline_rgb.mean(axis=2) > .2) & (baseline_rgb.mean(axis=2) < .8)
            if mask.mean() >= .01:
                for i, temp in enumerate(temps):
                    progress(f'Comparing white balance {i + 1} of {len(temps)}')
                    s = dict(settings)
                    if temp:
                        s.update(wb='Custom', temperature=temp)
                    p = out / f'wb-{i}.pp3'
                    p.write_text(profile_text(base, preview=True, **s))
                    rgb = pixels(render_rt(copy, p, out / f'wb-{i}.jpg'))
                    if rgb.shape != baseline_rgb.shape:
                        raise ValueError('WB preview geometry changed')
                    means = rgb[mask].mean(axis=0)
                    neutral_error = float(means.std() / max(means.mean(), 1e-6))
                    cost = neutral_error + (.02 if temp else 0)
                    wb_candidates.append({'temperature': temp, 'score': cost})
                winner = min(wb_candidates, key=lambda x: x['score'])
                if winner['temperature']:
                    settings.update(wb='Custom', temperature=winner['temperature'])
        progress('Developing the edited preview')
        preview_profile = out / 'preview.pp3'
        preview_profile.write_text(profile_text(base, preview=True, **settings))
        preview = render_rt(copy, preview_profile, out / 'edited-preview.jpg')
        preview_stats = statistics(pixels(preview))
        # One RAW-rendered verification, with a bounded exposure correction when
        # the estimate clips highlights. Keep the requested creative preset.
        if preview_stats['clipped_channels'] > baseline['clipped_channels'] + .008 and settings['exposure'] > 0:
            settings['exposure'] = max(0., round(settings['exposure']-.5, 2))
            preview_profile.write_text(profile_text(base, preview=True, **settings))
            preview.unlink()
            render_rt(copy, preview_profile, preview)
            preview_stats = statistics(pixels(preview))
        progress('Edited preview ready')
        progress('Exporting the full-resolution photo')
        final_profile = out / 'edit.pp3'
        final_profile.write_text(profile_text(base, **settings))
        final = render_rt(copy, final_profile, out / 'export.jpg')
        final_stats = statistics(pixels(final, max_size=1200))
        manifest.update(settings=settings, candidates=candidates, look_candidates=look_candidates, wb_candidates=wb_candidates,
                        sidecar_sha256=digest(final_profile), export_sha256=digest(final),
                        export_pixels_sha256=image_pixel_hash(final), final_statistics=final_stats,
                        baseline_statistics=baseline,
                        validation_scope=proof['source_sha256'])
    manifest.update(status='complete', original_preserved=True, elapsed_seconds=time.monotonic()-started)
    save_json(out / 'recipe.json', manifest)
    progress('Finished')
    return manifest


def replay(raw, recipe, out):
    recipe = Path(recipe).resolve()
    manifest = json.loads(recipe.read_text())
    if manifest.get('status') != 'complete':
        raise ValueError('Recipe is incomplete')
    if digest(raw) != manifest['source_sha256'] or rt_identity() != manifest['engine']:
        raise ValueError('Input or engine differs from recorded recipe')
    profile = recipe.parent / 'edit.pp3'
    if digest(profile) != manifest['sidecar_sha256']:
        raise ValueError('Sidecar changed; create a new recorded edit rather than silently replaying it')
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    with protected_input(raw, out / 'input') as (copy, _):
        target = render_rt(copy, profile, out / 'export.jpg')
        same = image_pixel_hash(target) == manifest['export_pixels_sha256']
    result = {'pixels_identical': same, 'file_identical': digest(target) == manifest['export_sha256'], 'original_preserved': True}
    save_json(out / 'replay.json', result)
    if not same:
        raise RuntimeError('Replay pixels differ; see replay.json')
    return result


def export_profile(raw, profile, out):
    """Render a user's explicit PP3 and record a fresh recipe for strict replay."""
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    manifest = {'schema': 1, 'status': 'incomplete', 'algorithm': 'explicit-profile-v1',
                'engine': rt_identity(), 'input': str(Path(raw).resolve())}
    save_json(out/'recipe.json', manifest)
    target_profile = out/'edit.pp3'
    shutil.copyfile(profile, target_profile)
    with protected_input(raw, out/'input') as (copy, raw_hash):
        manifest.update(source_sha256=raw_hash, metadata=metadata(copy))
        target = render_rt(copy, target_profile, out/'export.jpg')
        manifest.update(sidecar_sha256=digest(target_profile), export_sha256=digest(target),
                        export_pixels_sha256=image_pixel_hash(target))
    manifest.update(status='complete', original_preserved=True)
    save_json(out/'recipe.json', manifest)
    return manifest
