import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image, ImageCms
from rawflow.core import image_pixel_hash, pixel_hash, pixels, protected_input
from rawflow.presets import PRESETS, draft_preview
from rawflow.storage import export_photo
from rawflow.gui_jobs import completed_results


class FastPipelineTests(unittest.TestCase):
    def test_banded_hash_matches_legacy_replay_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'color.png'
            rng=np.random.default_rng(12)
            Image.fromarray(rng.integers(0,256,(137,115,3),dtype=np.uint8)).save(path,
                icc_profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes())
            self.assertEqual(image_pixel_hash(path),pixel_hash(pixels(path)))

    def test_all_drafts_distinct_and_monochrome_is_neutral(self):
        rng=np.random.default_rng(8)
        image=Image.fromarray(rng.integers(0,256,(80,100,3),dtype=np.uint8))
        results={k:draft_preview(image,k) for k in PRESETS}
        self.assertEqual(len({v.tobytes() for v in results.values()}),6)
        mono=np.asarray(results['black-and-white'])
        np.testing.assert_array_equal(mono[:,:,0],mono[:,:,2])

    def test_temporary_raw_copy_removed_on_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            raw=Path(temp)/'photo.CR3';raw.write_bytes(b'original')
            with self.assertRaisesRegex(ValueError,'renderer'):
                with protected_input(raw,Path(temp)/'input',remove_copy=True):
                    raise ValueError('renderer failure')
            self.assertFalse((Path(temp)/'input').exists())
            self.assertEqual(raw.read_bytes(),b'original')

    def test_only_jpeg_published_with_separate_reopenable_record(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);raw=root/'source.CR3';raw.write_bytes(b'raw')
            destination=root/'exports'/'photo.jpg'
            def process(raw,base,evidence,work,*args,**kw):
                work.mkdir();(work/'export.jpg').write_bytes(b'jpeg')
                (work/'edit.pp3').write_text('profile')
                return {'status':'complete','input':str(raw)}
            with patch('rawflow.storage.records_root',return_value=root/'records'), patch('rawflow.storage.process',side_effect=process):
                record=export_photo(raw,None,None,destination)
                with self.assertRaises(FileExistsError):export_photo(raw,None,None,destination)
            self.assertEqual(list(destination.parent.iterdir()),[destination])
            self.assertEqual(destination.read_bytes(),b'jpeg')
            self.assertTrue((record/'edit.pp3').is_file())
            self.assertFalse((record/'export.jpg').exists())
            with patch('rawflow.gui_jobs.records_root',return_value=root/'records'):
                self.assertEqual(completed_results(destination.parent)[0][1],record)
                self.assertEqual(completed_results(root/'unrelated'),[])
            self.assertEqual(raw.read_bytes(),b'raw')

    def test_failed_render_publishes_nothing(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            with patch('rawflow.storage.records_root',return_value=root/'records'), patch('rawflow.storage.process',side_effect=RuntimeError('failed')):
                with self.assertRaises(RuntimeError):export_photo(root/'raw.CR3',None,None,root/'exports/photo.jpg')
            self.assertFalse((root/'exports').exists())

    def test_monochrome_skips_meaningless_neutral_color_search(self):
        from rawflow.pipeline import process
        from rawflow.core import digest
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);raw=root/'sample.CR3';raw.write_bytes(b'raw')
            base=Path(__file__).resolve().parents[1]/'profiles/neutral-rt5.13.pp3'
            evidence=root/'evidence.json';evidence.write_text('{}')
            calls=[]
            def render(raw, profile, output):
                calls.append(output.name)
                Image.new('RGB',(80,60),(120,120,120)).save(output,
                    icc_profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes())
                return output
            with patch('rawflow.pipeline.require_evidence',return_value={'source_sha256':digest(raw)}), patch('rawflow.pipeline.rt_identity',return_value={}), patch('rawflow.pipeline.metadata',return_value={}), patch('rawflow.pipeline.render_rt',side_effect=render):
                record=process(raw,base,evidence,root/'record',wb='neutral-search',look='black-and-white')
            self.assertEqual(calls,['baseline.jpg','edited-preview.jpg','export.jpg'])
            self.assertEqual(record['wb_candidates'],[])
            self.assertTrue(record['settings']['monochrome'])
            self.assertFalse((root/'record/input').exists())

    def test_engine_asset_change_invalidates_cached_identity(self):
        from rawflow.core import rt_identity
        with tempfile.TemporaryDirectory() as temp:
            contents=Path(temp)/'Contents'
            (contents/'MacOS').mkdir(parents=True);(contents/'Resources').mkdir()
            exe=contents/'MacOS/rt';exe.write_bytes(b'processor')
            asset=contents/'Resources/profile';asset.write_bytes(b'first')
            with patch('rawflow.core.locate',return_value=str(exe)), patch('rawflow.core.execute',return_value='version') as execute:
                first=rt_identity();self.assertEqual(rt_identity(),first)
                self.assertEqual(execute.call_count,1)
                asset.write_bytes(b'changed')
                self.assertNotEqual(rt_identity(),first)
                self.assertEqual(execute.call_count,2)
