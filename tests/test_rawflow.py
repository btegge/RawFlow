import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image, ImageCms
from rawflow.core import protected_input, digest, profile_text, pixels, statistics, compare
from rawflow.pipeline import require_evidence


class SafetyAndAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
    def tearDown(self):
        self.temp.cleanup()
    def base(self):
        p = self.root/'base.pp3'
        p.write_text('[Version]\nVersion=353\n[Exposure]\nBlack=7\n[Color Management]\nWorkingProfile=ProPhoto\n')
        return p
    def test_original_and_adjacent_sidecars_preserved(self):
        raw = self.root/'photo.CR3'; raw.write_bytes(b'raw fixture')
        sidecar = self.root/'photo.CR3.pp3'; sidecar.write_text('manual edit')
        original = digest(raw)
        with protected_input(raw, self.root/'copy') as (copy, checksum):
            self.assertNotEqual(copy, raw)
            self.assertEqual(checksum, original)
            self.assertEqual(copy.stat().st_mode & 0o222, 0)
        self.assertEqual(digest(raw), original)
        self.assertEqual(sidecar.read_text(), 'manual edit')
    def test_mutation_detected_on_failure(self):
        raw = self.root/'photo.CR3'; raw.write_bytes(b'raw')
        with self.assertRaisesRegex(RuntimeError, 'checksum changed'):
            with protected_input(raw, self.root/'copy'):
                raw.write_bytes(b'changed')
    def test_existing_workspace_rejected(self):
        raw = self.root/'photo.CR3'; raw.write_bytes(b'raw')
        with self.assertRaises(FileExistsError):
            with protected_input(raw, self.root): pass
    def test_pp3_preserves_other_settings(self):
        result = profile_text(self.base(), exposure=.5, wb='Custom', temperature=5000)
        self.assertIn('Black=7', result)
        self.assertIn('WorkingProfile=ProPhoto', result)
        self.assertIn('Compensation=0.5', result)
        self.assertIn('Setting=Custom', result)
    def test_bad_profile_version_rejected(self):
        base = self.base(); base.write_text('[Version]\nVersion=1\n')
        with self.assertRaises(ValueError): profile_text(base)
    def test_invalid_parameters_rejected(self):
        with self.assertRaises(ValueError): profile_text(self.base(), exposure=float('nan'))
    def test_untagged_image_rejected(self):
        p=self.root/'image.jpg'; Image.new('RGB',(10,10)).save(p)
        with self.assertRaisesRegex(ValueError, 'ICC'): pixels(p)
    def test_tagged_srgb_linearization(self):
        p=self.root/'image.png'
        icc=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
        Image.new('RGB',(10,10),(128,128,128)).save(p,icc_profile=icc)
        stats=statistics(pixels(p))
        self.assertAlmostEqual(stats['p50'], .21586, places=4)
    def test_ignored_adjustment_fails_spike(self):
        rgb=np.full((20,20,3),.5)
        for kind in ['exposure','color','contrast','white_balance']:
            self.assertFalse(compare(rgb,rgb,kind)['passed'])
    def test_exposure_direction_checked(self):
        a=np.full((20,20,3),.5)
        self.assertTrue(compare(a,a+.1,'exposure')['passed'])
        self.assertFalse(compare(a,a-.1,'exposure')['passed'])
    def test_geometry_mismatch_rejected(self):
        with self.assertRaises(ValueError): compare(np.zeros((2,2,3)),np.zeros((3,3,3)),'color')
    def test_missing_or_stale_evidence_rejected(self):
        base=self.base(); p=self.root/'evidence.json'
        p.write_text(json.dumps({'status':'incomplete'}))
        with self.assertRaises(RuntimeError): require_evidence(p,base)
        d={'status':'complete','original_preserved':True,'rawtherapee':{'status':'passed'},
           'base_sha256':digest(base),'rt_identity':{'version':'old'}}
        p.write_text(json.dumps(d))
        with patch('rawflow.pipeline.rt_identity',return_value={'version':'new'}):
            with self.assertRaises(RuntimeError): require_evidence(p,base)


class EngineBoundaryTests(unittest.TestCase):
    def test_rawtherapee_version_exit_two_is_handled(self):
        import subprocess
        from rawflow.core import execute
        p=subprocess.CompletedProcess(['rt','--version'],2,'RawTherapee, version 5.13, command line.\n','')
        with patch('rawflow.core.subprocess.run',return_value=p):
            self.assertIn('5.13',execute(['rt','--version']))
    def test_render_exit_two_is_not_ignored(self):
        import subprocess
        from rawflow.core import execute
        p=subprocess.CompletedProcess(['rt','-c'],2,'RawTherapee, version 5.13','failed')
        with patch('rawflow.core.subprocess.run',return_value=p):
            with self.assertRaises(RuntimeError): execute(['rt','-c'])
    def test_non_r7_metadata_rejected(self):
        from rawflow.core import metadata
        with patch('rawflow.core.locate',return_value='/exiftool'), patch('rawflow.core.execute',return_value='[{"Model":"Other camera"}]'):
            with self.assertRaises(ValueError): metadata('other.CR3')
    def test_existing_export_is_rejected(self):
        from rawflow.core import render_rt
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'export.jpg';output.write_bytes(b'manual')
            with patch('rawflow.core.locate',return_value='/rt'):
                with self.assertRaises(FileExistsError): render_rt('input.CR3','edit.pp3',output)
            self.assertEqual(output.read_bytes(),b'manual')

if __name__ == '__main__': unittest.main()
