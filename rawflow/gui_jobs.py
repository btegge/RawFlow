"""Background jobs independent of the desktop toolkit."""
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
import json
from .formats import is_raw_candidate
from .pipeline import require_evidence
from .storage import export_photo, records_root


@dataclass(frozen=True)
class BatchOptions:
    base: Path
    evidence: Path
    output: Path
    look: str = 'punchy'
    scene: str = 'preserve'
    wb: str = 'camera'
    strength: str = 'low'


def run_batch(paths, options, events, stop, processor=export_photo, validate=require_evidence):
    completed = failed = 0
    folder = None
    try:
        validate(options.evidence, options.base)
        folder = options.output / datetime.now().strftime('RawFlow-%Y%m%d-%H%M%S-%f')
        folder.mkdir(parents=True, exist_ok=False)
        events.put(('batch_folder', folder))
        for index, path in enumerate(paths):
            if stop.is_set():
                break
            events.put(('started', path, index, len(paths)))
            try:
                output = folder / f'{index + 1:03d}-{path.stem}-{options.look}-{options.strength}.jpg'
                def progress(label):
                    events.put(('edit_preview', path, label[1])) if isinstance(label, tuple) else events.put(('progress', path, label))
                record = processor(path, options.base, options.evidence, output,
                          options.scene, options.wb, options.look, on_progress=progress, **({'strength': options.strength} if options.strength != 'low' else {}))
                completed += 1
                events.put(('completed', path, record or output))
            except Exception as e:
                failed += 1
                events.put(('failed', path, str(e)))
    except Exception as e:
        events.put(('fatal', str(e)))
    finally:
        events.put(('finished', completed, failed, stop.is_set(), folder))


def completed_results(folder):
    """Find usable outputs; incomplete and malformed recipes are excluded."""
    results = []
    folder = Path(folder).resolve()
    recipes = set(folder.rglob('recipe.json'))
    recipes.update(records_root().glob('*/recipe.json'))
    for recipe in sorted(recipes):
        try:
            data = json.loads(recipe.read_text())
            output = recipe.parent
            export = Path(data.get('export_path', output/'export.jpg'))
            if 'export_path' in data and not export.is_relative_to(folder):
                continue
            if data.get('status') == 'complete' and export.is_file():
                source = Path(data['input'])
                if not source.is_file():
                    copies = sorted(p for p in (output/'input').glob('*') if p.is_file() and is_raw_candidate(p))
                    if not copies:
                        continue
                    source = copies[0]
                results.append((source.resolve(), output, data))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return results
