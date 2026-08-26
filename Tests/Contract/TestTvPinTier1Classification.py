# directive: tv-tier1-classifier-pin
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.ContentClassifier.ContentClassifierService import ContentClassifierService


class TestTvPinTier1Classification(unittest.TestCase):

    def test_tv_row_matches_tv_pin_before_1080p_rule(self):
        Svc = ContentClassifierService()
        Rules = Svc.Repository.GetActiveRules()
        # T:\ file at 1080p, h264, 5967 kbps -- same shape as Outer Banks S05E09.
        Media = {
            'Id': 700065, 'AssignedProfile': None,
            'Codec': 'h264', 'VideoBitrateKbps': 5967, 'ResolutionCategory': '1080p',
            'FilePath': 'T:\\Outer Banks\\Season 5\\Outer Banks - S05E09 - Arise, Arise WEBDL-1080p.mkv',
        }
        Matched = Svc._Walk(Rules, Media)
        self.assertIsNotNone(Matched, 'no rule matched TV row')
        self.assertEqual(Matched.AssignProfileName, 'AV1 Tier 1 Efficient',
                         f"expected TvPin rule to win, got {Matched.RuleName}={Matched.AssignProfileName}")

    def test_movies_row_does_not_match_tv_pin(self):
        Svc = ContentClassifierService()
        Rules = Svc.Repository.GetActiveRules()
        Media = {
            'Id': 999999, 'AssignedProfile': None,
            'Codec': 'h264', 'VideoBitrateKbps': 5000, 'ResolutionCategory': '1080p',
            'FilePath': 'M:\\Movies\\Some Movie (2024)\\Some Movie (2024) Bluray-1080p.mkv',
        }
        Matched = Svc._Walk(Rules, Media)
        self.assertIsNotNone(Matched)
        self.assertNotEqual(Matched.RuleName, 'TvPinTier1Efficient',
                            'TvPin rule wrongly matched a Movies row')


if __name__ == '__main__':
    unittest.main()
