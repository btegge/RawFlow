import unittest
from rawflow.pipeline import punchy_center, look_acceptable
from rawflow.core import profile_text
from pathlib import Path


class LookTests(unittest.TestCase):
    def test_dark_daylight_can_receive_more_exposure(self):
        self.assertEqual(punchy_center({'p50':.03,'saturation':.2},'preserve'),1.25)
    def test_colored_night_is_kept_low_key(self):
        self.assertEqual(punchy_center({'p50':.02,'saturation':.5},'preserve'),.5)
    def test_bright_scene_is_not_forced_brighter(self):
        self.assertLess(punchy_center({'p50':.35,'saturation':.3},'preserve'),0)
    def test_clipping_increase_rejects_styled_preview(self):
        self.assertFalse(look_acceptable({'p50':.12,'clipped_channels':.02},{'p50':.1,'clipped_channels':.001}))
    def test_contrast_must_not_hide_the_exposure_gain(self):
        self.assertFalse(look_acceptable({'p50':.05,'clipped_channels':0},{'p50':.1,'clipped_channels':0}))
    def test_old_unstyled_profile_retains_base_shadow_settings(self):
        base=Path(__file__).resolve().parents[1]/'profiles/neutral-rt5.13.pp3'
        import configparser
        cfg=configparser.ConfigParser();cfg.read_string(profile_text(base))
        self.assertFalse(cfg.getboolean('Shadows & Highlights','Enabled'))
    def test_new_shadow_values_are_bounded(self):
        base=Path(__file__).resolve().parents[1]/'profiles/neutral-rt5.13.pp3'
        with self.assertRaises(ValueError): profile_text(base,shadows=100)
