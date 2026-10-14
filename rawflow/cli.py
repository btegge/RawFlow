import argparse
import glob
import json
from pathlib import Path
import sys
from .core import doctor, save_json
from .presets import PRESETS
from .storage import export_photo
from .pipeline import spike, process, replay, export_profile


def main():
    p = argparse.ArgumentParser(description='RawFlow: experimental, evidence-gated R7 RAW pipeline')
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('doctor')
    s = sub.add_parser('spike')
    s.add_argument('raw', type=Path)
    s.add_argument('--base', required=True, type=Path, help='Full neutral PP3 from the installed engine')
    s.add_argument('--out', required=True, type=Path)
    s.add_argument('--darktable-profiles', type=Path)
    r = sub.add_parser('edit')
    r.add_argument('inputs', nargs='+', help='Paths or quoted glob patterns')
    r.add_argument('--base', required=True, type=Path)
    r.add_argument('--evidence', required=True, type=Path)
    r.add_argument('--out', required=True, type=Path)
    r.add_argument('--look', choices=list(PRESETS), default='punchy', help='Creative editing preset')
    r.add_argument('--strength', choices=['low','medium','high'], default='low')
    r.add_argument('--scene', choices=['preserve', 'normal'], default='preserve')
    r.add_argument('--wb', choices=['camera', 'neutral-search'], default='camera')
    e = sub.add_parser('export')
    e.add_argument('raw', type=Path)
    e.add_argument('--profile', required=True, type=Path)
    e.add_argument('--out', required=True, type=Path)
    r = sub.add_parser('replay')
    r.add_argument('raw', type=Path)
    r.add_argument('--recipe', required=True, type=Path)
    r.add_argument('--out', required=True, type=Path)
    args = p.parse_args()
    try:
        if args.command == 'doctor':
            result = doctor()
        elif args.command == 'spike':
            result = spike(args.raw, args.base, args.out, args.darktable_profiles)
        elif args.command == 'export':
            result = export_profile(args.raw, args.profile, args.out)
        elif args.command == 'replay':
            result = replay(args.raw, args.recipe, args.out)
        else:
            paths = sorted(set(Path(f).resolve() for pattern in args.inputs for f in glob.glob(pattern)))
            if not paths:
                raise ValueError('No inputs matched')
            from .core import digest
            result = []
            for index, raw in enumerate(paths):
                target = args.out / f'{index+1:03d}-{raw.stem}-{args.look}-{args.strength}.jpg'
                record = export_photo(raw, args.base, args.evidence, target, args.scene, args.wb, args.look, strength=args.strength)
                result.append({'jpeg': str(target.resolve()), 'recipe': str(record/'recipe.json')})
        print(json.dumps(result, indent=2))
        if args.command == 'spike' and result['rawtherapee']['status'] != 'passed':
            return 1
        return 0
    except Exception as e:
        print(f'rawflow: {e}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
