import unittest
import configparser
from pathlib import Path
from rawflow.presets import PRESETS, preset_settings
from rawflow.core import profile_text

class StrengthTests(unittest.TestCase):
    def test_low_preserves_existing_adjustments(self):
        for look, original in PRESETS.items():
            settings=preset_settings(look)
            self.assertEqual({k:settings[k] for k in original},original)
    def test_medium_and_high_scale_every_numeric_adjustment(self):
        for look, original in PRESETS.items():
            for strength,factor in [('medium',1.25),('high',1.5)]:
                settings=preset_settings(look,strength)
                for key in ['contrast','saturation','shadows','highlights']:
                    self.assertEqual(settings[key],round(original[key]*factor))
                text=profile_text(Path(__file__).resolve().parents[1]/'profiles/neutral-rt5.13.pp3',exposure=2.25,**settings)
                cfg=configparser.ConfigParser();cfg.read_string(text)
                self.assertEqual(cfg.getfloat('Exposure','Saturation'),round(original['saturation']*factor))
    def test_tonal_curve_deviation_scales(self):
        base=Path(__file__).resolve().parents[1]/'profiles/neutral-rt5.13.pp3'
        cfg=configparser.ConfigParser();cfg.read_string(profile_text(base,**preset_settings('filmic','high')))
        self.assertAlmostEqual(float(cfg['Exposure']['Curve'].split(';')[2]),.0525)
