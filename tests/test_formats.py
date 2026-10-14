import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image, ImageCms
from rawflow.formats import is_raw_candidate
from rawflow.core import metadata, protected_input, digest
from rawflow.previews import photo_preview

class CameraGeneralizationTests(unittest.TestCase):
    def test_multiple_extensions_and_mixed_case(self):
        for name in ['photo.NEF','photo.ArW','photo.RAF','photo.DNG','photo.ORF','photo.RW2','photo.PEF','photo.CR3']:
            self.assertTrue(is_raw_candidate(name))
        self.assertFalse(is_raw_candidate('photo.jpg'))

    def test_metadata_accepts_other_camera_and_missing_optional_fields(self):
        for data in [{'FileType':'NEF','Make':'Nikon','Model':'Z 6'},{'FileType':'DNG'}]:
            with patch('rawflow.core.locate',return_value='/exiftool'),patch('rawflow.core.execute',return_value=json.dumps([data])):
                result=metadata('photo.raw')
                self.assertEqual(result['camera']['model'],data.get('Model'))
                self.assertIsNone(result['camera']['iso'])

    def test_tiff_requires_raw_indicators(self):
        for data,accepted in [({'FileType':'TIFF'},False),({'FileType':'TIFF','CFARepeatPatternDim':'2 2'},True)]:
            with patch('rawflow.core.locate',return_value='/exiftool'),patch('rawflow.core.execute',return_value=json.dumps([data])):
                if accepted:self.assertEqual(metadata('photo.raw')['camera']['file_type'],'TIFF')
                else:
                    with self.assertRaises(ValueError):metadata('photo.raw')

    def test_isolated_copy_supports_other_extensions_and_preserves_sidecars(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);raw=root/'image.NEF';raw.write_bytes(b'fixture')
            sidecar=root/'image.NEF.pp3';sidecar.write_text('existing')
            with protected_input(raw,root/'input',remove_copy=True) as (copy,_):
                self.assertEqual(copy.name,raw.name)
                self.assertFalse(copy.with_suffix('.NEF.pp3').exists())
            self.assertEqual(raw.read_bytes(),b'fixture');self.assertEqual(sidecar.read_text(),'existing')

    def test_raw_preview_cache_invalidates_on_source_and_profile_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);raw=root/'image.RAF';raw.write_bytes(b'fixture');base=root/'base.pp3';base.write_text('profile')
            calls=[]
            def render(raw,profile,target):
                calls.append(target)
                Image.new('RGB',(100,80),(80,90,100)).save(target,icc_profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes())
                return target
            with patch.dict('os.environ',{'RAWFLOW_PREVIEW_CACHE':str(root/'cache')}),patch('rawflow.previews.metadata',return_value={}),patch('rawflow.previews.embedded_preview',return_value=None),patch('rawflow.previews.require_evidence'),patch('rawflow.previews.rt_identity',return_value={'version':'fixture'}),patch('rawflow.previews.profile_text',return_value='profile'),patch('rawflow.previews.render_rt',side_effect=render):
                image,caption=photo_preview(raw,base,root/'evidence')
                self.assertEqual(caption,'Before · RAW preview');self.assertEqual(image.size,(100,80))
                photo_preview(raw,base,root/'evidence');self.assertEqual(len(calls),1)
                raw.write_bytes(b'changed');photo_preview(raw,base,root/'evidence');self.assertEqual(len(calls),2)
                base.write_text('changed');photo_preview(raw,base,root/'evidence');self.assertEqual(len(calls),3)
            self.assertEqual(raw.read_bytes(),b'changed')

    def test_failed_raw_preview_never_creates_cache_entry(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);raw=root/'image.ARW';raw.write_bytes(b'fixture');base=root/'base.pp3';base.write_text('profile')
            with patch.dict('os.environ',{'RAWFLOW_PREVIEW_CACHE':str(root/'cache')}),patch('rawflow.previews.metadata',return_value={}),patch('rawflow.previews.embedded_preview',return_value=None),patch('rawflow.previews.require_evidence'),patch('rawflow.previews.rt_identity',return_value={}),patch('rawflow.previews.profile_text',return_value='profile'),patch('rawflow.previews.render_rt',side_effect=RuntimeError('unsupported mode')):
                with self.assertRaisesRegex(RuntimeError,'unsupported mode'):photo_preview(raw,base,root/'evidence')
            self.assertEqual(list((root/'cache').iterdir()),[])
            self.assertEqual(raw.read_bytes(),b'fixture')

    def test_decode_failure_records_reason_and_preserves_original(self):
        from rawflow.pipeline import process
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);raw=root/'image.NEF';raw.write_bytes(b'fixture')
            evidence=root/'evidence.json';evidence.write_text('{}')
            base=Path(__file__).resolve().parents[1]/'profiles/neutral-rt5.13.pp3'
            with patch('rawflow.pipeline.require_evidence',return_value={'source_sha256':digest(raw)}),patch('rawflow.pipeline.rt_identity',return_value={}),patch('rawflow.pipeline.metadata',return_value={'Model':'fixture'}),patch('rawflow.pipeline.render_rt',side_effect=RuntimeError('unsupported compression')):
                with self.assertRaisesRegex(RuntimeError,'Unable to decode'):process(raw,base,evidence,root/'record')
            record=json.loads((root/'record/recipe.json').read_text())
            self.assertEqual(record['decoding']['status'],'failed')
            self.assertIn('unsupported compression',record['decoding']['error'])
            self.assertFalse((root/'record/input').exists());self.assertFalse((root/'record/export.jpg').exists())
            self.assertEqual(raw.read_bytes(),b'fixture')
