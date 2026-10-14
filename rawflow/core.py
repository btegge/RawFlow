from __future__ import annotations
import configparser
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from PIL import Image, ImageCms, ImageOps
import numpy as np

from .formats import is_raw_candidate, RAW_TYPES

ALGORITHM = "fast-presets-v3"


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def save_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + '\n')


def execute(args, log=None):
    env = dict(os.environ, LC_ALL='C', OMP_NUM_THREADS=os.environ.get('RAWFLOW_THREADS', str(min(4, os.cpu_count() or 1))))
    with tempfile.TemporaryDirectory(prefix='rawflow-settings-') as settings:
        env.update(RT_SETTINGS=settings, RT_CACHE=settings + '/cache')
        p = subprocess.run([str(x) for x in args], capture_output=True, text=True,
                           timeout=600, env=env)
    if log:
        save_json(log, {'argv': [str(x) for x in args], 'returncode': p.returncode,
                        'stdout': p.stdout, 'stderr': p.stderr})
    if p.returncode and not (p.returncode == 2 and '--version' in args and 'RawTherapee, version' in p.stdout):
        raise RuntimeError(f'Command failed ({p.returncode}): {args[0]}: {p.stderr[-1500:]}')
    return p.stdout + p.stderr


def locate(name):
    override = os.environ.get('RAWFLOW_' + name.upper().replace('-', '_'))
    if override:
        return str(Path(override).resolve(strict=True))
    candidates = {
        'rawtherapee-cli': ['/Applications/RawTherapee.app/Contents/MacOS/rawtherapee-cli'],
        'darktable-cli': ['/Applications/darktable.app/Contents/MacOS/darktable-cli'],
    }.get(name, [])
    found = shutil.which(name)
    if found:
        sibling = Path(found).resolve().with_name('rawtherapee-cli-bin')
        return str(sibling) if name == 'rawtherapee-cli' and sibling.is_file() else found
    return next((p for p in candidates if Path(p).is_file()), None)


def doctor():
    result = {'architecture': platform.machine(), 'python': platform.python_version(), 'tools': {}}
    for name in ('rawtherapee-cli', 'darktable-cli', 'exiftool'):
        path = locate(name)
        entry = {'path': path, 'status': 'missing'}
        if path:
            try:
                entry.update(status='available', version=execute([path, '-ver' if name == 'exiftool' else '--version']).strip(), sha256=digest(path))
            except (RuntimeError, subprocess.TimeoutExpired) as e:
                entry.update(status='error', error=str(e))
        result['tools'][name] = entry
    return result


def metadata(raw):
    exe = locate('exiftool')
    if not exe:
        raise RuntimeError('ExifTool is required; install it before processing RAW files.')
    items = json.loads(execute([exe, '-j', '-n', '-Make', '-Model', '-ISO', '-ExposureTime',
                               '-FNumber', '-LensModel', '-WhiteBalance', '-ColorTemperature',
                               '-ImageWidth', '-ImageHeight', '-RawImageSize', '-Compression', '-Orientation', '-FileType', '-DNGVersion', '-CFARepeatPatternDim', '-PhotometricInterpretation', '-Canon:Quality', '-Canon:DualPixelRaw', raw]))
    if len(items) != 1 or not isinstance(items[0], dict):
        raise ValueError('Expected metadata for one RAW file')
    data = items[0]
    kind = str(data.get('FileType', '')).upper()
    tiff_raw = kind == 'TIFF' and (data.get('DNGVersion') or data.get('CFARepeatPatternDim') or data.get('PhotometricInterpretation') in (32803, 34892))
    if kind not in RAW_TYPES and not tiff_raw:
        raise ValueError(f'Unrecognized RAW content ({kind or "missing file type"}); the extension alone is insufficient')
    if data.get('Error'):
        raise ValueError(str(data['Error']))
    data['camera'] = {'make': data.get('Make'), 'model': data.get('Model'),
                      'iso': data.get('ISO'), 'width': data.get('ImageWidth'),
                      'height': data.get('ImageHeight'), 'orientation': data.get('Orientation'),
                      'compression': data.get('Compression'), 'file_type': kind}
    return data


@contextmanager
def protected_input(raw, directory, remove_copy=False):
    raw = Path(raw).resolve(strict=True)
    if not is_raw_candidate(raw):
        raise ValueError('Expected a candidate camera RAW file')
    before = digest(raw)
    folder = Path(directory)
    folder.mkdir(parents=True, exist_ok=False)
    copy = folder / raw.name
    shutil.copyfile(raw, copy)
    copy.chmod(0o444)
    try:
        if digest(copy) != before:
            raise RuntimeError('Input copy checksum mismatch')
        yield copy, before
    finally:
        try:
            if digest(raw) != before or digest(copy) != before:
                raise RuntimeError('RAW checksum changed; preservation check failed')
        finally:
            if remove_copy:
                shutil.rmtree(folder)


def profile_text(base, exposure=0., contrast=0, saturation=0, wb='Camera', temperature=6500, green=1., preview=False, shadows=None, highlights=None, monochrome=False, tone=None, tone_strength=1.):
    if not (-2.25 <= exposure <= 2.25 and -45 <= contrast <= 45 and -45 <= saturation <= 45):
        raise ValueError('Adjustment outside supported range')
    if wb not in ('Camera', 'Custom') or not (2000 <= temperature <= 12000 and .5 <= green <= 2):
        raise ValueError('Invalid white balance')
    if any(v is not None and not 0 <= v <= 60 for v in (shadows, highlights)):
        raise ValueError('Shadow/highlight adjustment outside supported range')
    cfg = configparser.ConfigParser(interpolation=None, strict=True)
    cfg.optionxform = str
    cfg.read_string(Path(base).read_text())
    if cfg.getint('Version', 'Version') not in (351, 353):
        raise ValueError('Experimental PP3 adapter supports profile formats 351 and 353 only')
    values = {
        'Exposure': {'Auto': 'false', 'Compensation': str(exposure), 'Contrast': str(contrast),
                     'Saturation': str(saturation), 'HistogramMatching': 'false'},
        'White Balance': {'Enabled': 'true', 'Setting': wb, 'Temperature': str(temperature), 'Green': str(green)},
        'Color Management': {'OutputProfile': 'RTv4_sRGB', 'OutputProfileIntent': 'Relative', 'OutputBPC': 'true'},
        'Resize': {'Enabled': str(preview).lower(), 'Scale': '1', 'AppliesTo': 'Full image', 'Method': 'Lanczos',
                   'DataSpecified': '3', 'Width': '1200', 'Height': '1200', 'AllowUpscaling': 'false'},
    }
    if shadows is not None or highlights is not None:
        values['Shadows & Highlights'] = {
            'Enabled': str(bool(shadows or highlights)).lower(),
            'Shadows': str(shadows or 0), 'Highlights': str(highlights or 0),
            'ShadowTonalWidth': '50', 'HighlightTonalWidth': '50', 'Radius': '40', 'Lab': 'false'}
    if not 1 <= tone_strength <= 1.5:
        raise ValueError('Invalid tone strength')
    if tone not in (None, 'filmic', 'arty'):
        raise ValueError('Unknown tone')
    values['Black & White'] = {'Enabled': str(monochrome).lower(), 'Method': 'Desaturation'}
    if tone == 'filmic':
        values['Exposure']['Curve'] = '1;0;0.035;0.25;0.26;0.5;0.51;0.75;0.74;1;0.965;'
    if tone == 'arty':
        values['RGB Curves'] = {'Enabled': 'true', 'LumaMode': 'false',
            'rCurve': '1;0;0;0.5;0.52;1;1;',
            'gCurve': '1;0;0;1;1;', 'bCurve': '1;0;0.055;0.5;0.52;1;1;'}
    if tone and tone_strength != 1:
        # Scale each curve's deviation from the identity, keeping x coordinates.
        sections = [('Exposure', 'Curve')] if tone == 'filmic' else [('RGB Curves', k) for k in ('rCurve','gCurve','bCurve')]
        for section, key in sections:
            points = values[section][key].strip(';').split(';')
            for i in range(1, len(points), 2):
                x, y = float(points[i]), float(points[i+1])
                points[i+1] = str(max(0., min(1., x+(y-x)*tone_strength)))
            values[section][key] = ';'.join(points)+';'
    for section, pairs in values.items():
        if not cfg.has_section(section):
            cfg.add_section(section)
        for k, v in pairs.items():
            cfg.set(section, k, v)
    output = io.StringIO()
    cfg.write(output, space_around_delimiters=False)
    return output.getvalue()


def render_rt(raw, profile, output):
    exe = locate('rawtherapee-cli')
    if not exe:
        raise RuntimeError('rawtherapee-cli is missing')
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    args = [exe, '-o', output, '-p', profile, '-j100', '-js3', '-c', raw]
    execute(args, output.with_suffix('.command.json'))
    if not output.is_file():
        raise RuntimeError('Renderer returned success without creating output')
    return output


def render_dt(raw, profile, output, config):
    exe = locate('darktable-cli')
    if not exe:
        raise RuntimeError('darktable-cli is missing')
    if Path(output).exists():
        raise FileExistsError(output)
    Path(config).mkdir(parents=True, exist_ok=False)
    execute([exe, Path(raw).resolve(), Path(profile).resolve(), Path(output).resolve(), '--width', '1200', '--height', '1200',
             '--core', '--configdir', Path(config).resolve(), '--library', ':memory:', '--disable-opencl',
             '--conf', 'write_sidecar_files=never'], Path(output).with_suffix('.command.json'))
    if not Path(output).is_file():
        raise RuntimeError('No darktable output')


def pixels(path, max_size=None):
    with Image.open(path) as source:
        icc = source.info.get('icc_profile')
        if not icc:
            raise ValueError(f'Missing embedded ICC profile: {path}')
        # Normalize through LittleCMS before applying the sRGB transfer function.
        image = ImageOps.exif_transpose(source).convert('RGB')
        if max_size:
            image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        image = ImageCms.profileToProfile(image, ImageCms.ImageCmsProfile(io.BytesIO(icc)),
                                         ImageCms.createProfile('sRGB'), outputMode='RGB', renderingIntent=1)
        return np.asarray(image, dtype=np.float64) / 255


def statistics(rgb):
    linear = np.where(rgb <= .04045, rgb / 12.92, ((rgb + .055) / 1.055) ** 2.4)
    lum = linear @ np.array([.2126, .7152, .0722])
    p10, p50, p90, p99 = np.percentile(lum, [10, 50, 90, 99])
    maximum, minimum = rgb.max(axis=2), rgb.min(axis=2)
    sat = (maximum - minimum) / np.maximum(maximum, 1e-6)
    return {'p10': float(p10), 'p50': float(p50), 'p90': float(p90), 'p99': float(p99),
            'clipped_channels': float(np.mean(rgb >= 254 / 255)), 'saturation': float(np.mean(sat)),
            'contrast': float(p90 - p10), 'channel_means': linear.mean(axis=(0, 1)).tolist()}


def pixel_hash(rgb):
    return hashlib.sha256(rgb.tobytes()).hexdigest()


def image_pixel_hash(path):
    """Same canonical float64 hash as pixel_hash(pixels()), with bounded arrays."""
    with Image.open(path) as source:
        icc = source.info.get('icc_profile')
        if not icc:
            raise ValueError(f'Missing embedded ICC profile: {path}')
        image = ImageCms.profileToProfile(ImageOps.exif_transpose(source).convert('RGB'),
            ImageCms.ImageCmsProfile(io.BytesIO(icc)), ImageCms.createProfile('sRGB'),
            outputMode='RGB', renderingIntent=1)
    h = hashlib.sha256()
    for y in range(0, image.height, 64):
        band = np.asarray(image.crop((0, y, image.width, min(y+64, image.height))), dtype=np.float64) / 255
        h.update(band.tobytes())
    return h.hexdigest()


def compare(base, changed, kind):
    if base.shape != changed.shape:
        raise ValueError('Rendered image dimensions differ')
    a, b = statistics(base), statistics(changed)
    delta = float(np.mean(np.abs(base - changed)))
    if kind == 'exposure':
        direction = b['p50'] > a['p50'] + .001
    elif kind == 'color':
        direction = b['saturation'] > a['saturation'] + .001
    elif kind == 'contrast':
        direction = b['contrast'] > a['contrast'] + .001
    else:
        aa, bb = np.array(a['channel_means']), np.array(b['channel_means'])
        direction = abs(bb[0] / max(bb[2], 1e-8) - aa[0] / max(aa[2], 1e-8)) > .01
    return {'mean_absolute_difference': delta, 'direction_or_chroma_check': bool(direction),
            'passed': bool(delta > .0001 and direction), 'baseline': a, 'changed': b}


_IDENTITY_CACHE = {}


def rt_identity():
    # Reuse content hashes only while every engine file's stat fingerprint matches.
    exe = Path(locate('rawtherapee-cli') or '').resolve()
    if not exe.is_file():
        raise RuntimeError('RawTherapee CLI is unavailable')
    assets = []
    contents = exe.parent.parent
    if exe.parent.name == 'MacOS' and contents.name == 'Contents':
        for directory in ('Resources', 'Frameworks'):
            assets.extend(p for p in sorted((contents/directory).rglob('*')) if p.is_file())
    files = [exe] + assets
    fingerprint = tuple((str(p), p.stat().st_size, p.stat().st_mtime_ns,
                         p.stat().st_ctime_ns, p.stat().st_ino) for p in files)
    cached = _IDENTITY_CACHE.get(str(exe))
    if cached and cached[0] == fingerprint:
        return dict(cached[1])
    identity = {'version': execute([str(exe), '--version']).strip(), 'sha256': digest(exe)}
    if assets:
        h = hashlib.sha256()
        for asset in assets:
            h.update(str(asset.relative_to(contents)).encode())
            h.update(digest(asset).encode())
        identity['assets_sha256'] = h.hexdigest()
    _IDENTITY_CACHE[str(exe)] = (fingerprint, identity)
    return dict(identity)
