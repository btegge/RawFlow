"""Embedded JPEG previews with an evidence-gated, persistent RAW fallback."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from functools import lru_cache
from PIL import Image, ImageCms, ImageOps
from .core import locate, metadata, digest, rt_identity, protected_input, profile_text, render_rt, pixels
from .pipeline import require_evidence


def load_image(path):
    with Image.open(path) as source:
        source.draft('RGB', (1800,1400))
        image = ImageOps.exif_transpose(source).convert('RGB')
        if source.info.get('icc_profile'):
            image = ImageCms.profileToProfile(image, ImageCms.ImageCmsProfile(io.BytesIO(source.info['icc_profile'])),
                ImageCms.createProfile('sRGB'), outputMode='RGB', renderingIntent=1)
        image.thumbnail((1800,1400), Image.Resampling.LANCZOS)
        return image.copy()


@lru_cache(maxsize=12)
def embedded_preview(path, size, modified, exe):
    for tag in ('JpgFromRaw','PreviewImage','OtherImage','JpgFromRaw2','ThumbnailImage'):
        try:
            result = subprocess.run([exe,'-b','-'+tag,path],capture_output=True,timeout=30)
            if result.returncode == 0 and result.stdout:
                return load_image(io.BytesIO(result.stdout))
        except (OSError, ValueError, subprocess.TimeoutExpired):
            continue
    return None


def photo_preview(path, base=None, evidence=None):
    path = Path(path).resolve(strict=True)
    metadata(path)  # Reject renamed non-RAW content before extracting/rendering.
    st = path.stat()
    image = embedded_preview(str(path),st.st_size,st.st_mtime_ns,locate('exiftool'))
    if image is not None:
        return image, 'Before · camera preview'
    if base is None or evidence is None:
        raise ValueError('No embedded preview. Configure a base profile and matching compatibility record for RAW preview rendering.')
    require_evidence(evidence,base)
    key = hashlib.sha256(json.dumps({'source':digest(path),'base':digest(base),'engine':rt_identity(),
                                    'preview_version':1},sort_keys=True).encode()).hexdigest()
    cache = Path(os.environ.get('RAWFLOW_PREVIEW_CACHE',str(Path(__file__).resolve().parents[1]/'work/preview-cache')))
    cache.mkdir(parents=True,exist_ok=True)
    target = cache/(key+'.jpg')
    if target.is_file():
        try:
            pixels(target,max_size=1200)  # A cache hit must still be a valid ICC-tagged render.
            return load_image(target), 'Before · RAW preview'
        except (OSError,ValueError):
            target.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix='rawflow-preview-') as temporary:
        work=Path(temporary)
        with protected_input(path,work/'input',remove_copy=True) as (copy,_):
            profile=work/'preview.pp3';profile.write_text(profile_text(base,preview=True))
            try:
                result=render_rt(copy,profile,work/'preview.jpg')
                pixels(result,max_size=1200)
            except Exception as e:
                raise RuntimeError(f'RAW preview decoding failed for {path.name}: {e}') from e
            # Cache a complete file atomically; concurrent identical requests are equivalent.
            fd, staging=tempfile.mkstemp(prefix='.preview-',dir=cache)
            os.close(fd)
            try:
                shutil.copyfile(result,staging)
                os.replace(staging,target)
            finally:
                Path(staging).unlink(missing_ok=True)
    return load_image(target), 'Before · RAW preview'
