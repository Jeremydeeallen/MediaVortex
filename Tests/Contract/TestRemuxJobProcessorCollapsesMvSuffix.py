import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from Features.TranscodeJob.Emit.OutputFilenameBuilder import OutputFilenameBuilder


# directive: worker-runtime-state
class TestCollapseMvSuffixAgainstRealRemuxJobInputs(unittest.TestCase):
    def setUp(self):
        self.Builder = OutputFilenameBuilder()

    # directive: worker-runtime-state
    def _Compose(self, EffectiveInputBase: str) -> str:
        BaseName = self.Builder.CollapseMvSuffix(EffectiveInputBase)
        return BaseName + '-mv.mp4.inprogress'

    def test_single_mv_source_stays_single(self):
        Out = self._Compose('Black Butler - S01E22 - His Butler, Dissolution Bluray-1080p-mv')
        self.assertTrue(Out.endswith('-mv.mp4.inprogress'))
        self.assertNotIn('-mv-mv', Out)

    def test_double_mv_source_collapses_to_single(self):
        Out = self._Compose('Black Butler - S01E22 - His Butler, Dissolution Bluray-1080p-mv-mv')
        self.assertTrue(Out.endswith('-mv.mp4.inprogress'))
        self.assertNotIn('-mv-mv', Out)

    def test_triple_mv_source_collapses_to_single(self):
        Out = self._Compose('Obi-Wan Kenobi - S01E06 - Part VI WEBRip-720p-mv-mv-mv')
        self.assertTrue(Out.endswith('-mv.mp4.inprogress'))
        self.assertNotIn('-mv-mv', Out)

    def test_no_mv_source_gets_single_mv(self):
        Out = self._Compose('Foo - S01E01 - Pilot WEBDL-720p')
        self.assertTrue(Out.endswith('-mv.mp4.inprogress'))
        self.assertNotIn('-mv-mv', Out)


if __name__ == '__main__':
    unittest.main()
