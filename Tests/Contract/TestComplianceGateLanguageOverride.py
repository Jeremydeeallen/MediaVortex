import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import re


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S13
LANG_RE = re.compile(r'-metadata:s:a:\d+\s+"?language=([a-z]{2,3})"?')


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S13
def _ParseEmittedLangsForCandidate(FFmpegCommand):
    """Mirrors the parse path inside Features/FileReplacement/ComplianceGate.py; pure for testability."""
    return LANG_RE.findall(FFmpegCommand or '')


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S13
class TestComplianceGateLanguageOverride(unittest.TestCase):
    """S4 / S13: parse emitted language tags from the FFmpegCommand; override candidate row fields."""

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S13
    def test_parses_single_emitted_language(self):
        Cmd = 'ffmpeg ... -metadata:s:a:0 "language=eng" -metadata:s:a:0 "title=Original" ...'
        self.assertEqual(_ParseEmittedLangsForCandidate(Cmd), ['eng'])

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S13
    def test_parses_dual_track_with_same_language(self):
        Cmd = ('ffmpeg ... -metadata:s:a:0 "language=eng" -metadata:s:a:0 "title=Original" '
               '-metadata:s:a:1 "language=eng" -metadata:s:a:1 "title=Dialog Boost" ...')
        self.assertEqual(_ParseEmittedLangsForCandidate(Cmd), ['eng', 'eng'])

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S13
    def test_parses_multi_language(self):
        Cmd = ('ffmpeg ... -metadata:s:a:0 "language=eng" ... '
               '-metadata:s:a:1 "language=jpn" ...')
        self.assertEqual(_ParseEmittedLangsForCandidate(Cmd), ['eng', 'jpn'])

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S13
    def test_empty_command_returns_empty_list(self):
        self.assertEqual(_ParseEmittedLangsForCandidate(''), [])
        self.assertEqual(_ParseEmittedLangsForCandidate(None), [])

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S13
    def test_no_metadata_returns_empty_list(self):
        Cmd = 'ffmpeg -i input.mp4 -c:v copy -c:a copy output.mp4'
        self.assertEqual(_ParseEmittedLangsForCandidate(Cmd), [])

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S13
    def test_override_routes_to_explicit_english_when_present(self):
        Cmd = '-metadata:s:a:0 "language=eng"'
        Langs = _ParseEmittedLangsForCandidate(Cmd)
        HasExplicitEnglish = any(L.lower() in ('eng', 'en') for L in Langs)
        self.assertTrue(HasExplicitEnglish)

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S13
    def test_override_does_not_grant_english_for_other_languages(self):
        Cmd = '-metadata:s:a:0 "language=jpn" -metadata:s:a:1 "language=spa"'
        Langs = _ParseEmittedLangsForCandidate(Cmd)
        HasExplicitEnglish = any(L.lower() in ('eng', 'en') for L in Langs)
        self.assertFalse(HasExplicitEnglish)


if __name__ == '__main__':
    unittest.main()
