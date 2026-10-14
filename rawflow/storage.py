"""Separate user-facing JPEGs from editable processing records."""
from pathlib import Path
import os
import shutil
import tempfile
import uuid
from .core import save_json
from .pipeline import process


def records_root():
    return Path(os.environ.get('RAWFLOW_WORK_DIR', str(Path(__file__).resolve().parents[1]/'work'/'edits')))


def export_photo(raw, base, evidence, destination, scene='preserve', wb='camera', look='punchy', on_progress=None, strength='low'):
    destination = Path(destination).resolve()
    if destination.exists():
        raise FileExistsError(destination)
    work = records_root()/uuid.uuid4().hex
    work.parent.mkdir(parents=True, exist_ok=True)
    def progress(label):
        if on_progress:
            # Internal event payload for the desktop; ordinary stages stay text.
            on_progress(('preview_ready', work) if label == 'Edited preview ready' else label)
    manifest = process(raw, base, evidence, work, scene, wb, look, on_progress=progress, strength=strength)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Publish a complete JPEG atomically without overwriting an existing file.
    fd, staging = tempfile.mkstemp(prefix='.rawflow-', dir=destination.parent)
    try:
        with os.fdopen(fd, 'wb') as output, (work/'export.jpg').open('rb') as source:
            shutil.copyfileobj(source, output)
        os.link(staging, destination)
    finally:
        Path(staging).unlink(missing_ok=True)
    manifest['export_path'] = str(destination)
    save_json(work/'recipe.json', manifest)
    (work/'export.jpg').unlink()
    return work
