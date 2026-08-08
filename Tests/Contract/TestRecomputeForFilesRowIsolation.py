# directive: compliance-reason-full-library-recompute
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.VideoEncoding.VideoVertical import VideoVertical
from Features.AudioNormalization.AudioVertical import AudioVertical
from Features.ContainerFormat.ContainerVertical import ContainerVertical


class TestRecomputeForFilesRowIsolation(unittest.TestCase):
    """DD1: One bad row must not abort the batch. Per-vertical RecomputeFor logs + continues on ANY per-row exception."""

    def _MakeRepoMgr(self):
        """RepoMgr that raises KeyError for every GetMediaFileById -- every row triggers exception path."""
        Rm = MagicMock()
        Rm.GetMediaFileById = MagicMock(side_effect=KeyError("simulated repo lookup failure"))
        return Rm

    def test_video_vertical_recomputefor_does_not_raise_when_every_row_fails(self):
        Vv = VideoVertical(Db=MagicMock(), RepoMgr=self._MakeRepoMgr())
        try:
            Vv.RecomputeFor([1, 2, 3, 4, 5])
        except Exception as Ex:
            self.fail(f'VideoVertical.RecomputeFor raised on all-bad batch: {Ex!r}')

    def test_audio_vertical_recomputefor_does_not_raise_when_every_row_fails(self):
        Av = AudioVertical(Db=MagicMock(), RepoMgr=self._MakeRepoMgr())
        try:
            Av.RecomputeFor([1, 2, 3, 4, 5])
        except Exception as Ex:
            self.fail(f'AudioVertical.RecomputeFor raised on all-bad batch: {Ex!r}')

    def test_container_vertical_recomputefor_does_not_raise_when_every_row_fails(self):
        Cv = ContainerVertical(Db=MagicMock(), RepoMgr=self._MakeRepoMgr())
        try:
            Cv.RecomputeFor([1, 2, 3, 4, 5])
        except Exception as Ex:
            self.fail(f'ContainerVertical.RecomputeFor raised on all-bad batch: {Ex!r}')


if __name__ == '__main__':
    unittest.main()
