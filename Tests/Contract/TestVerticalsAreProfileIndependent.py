import re
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from Features.VideoEncoding.VideoVertical import VideoVertical
from Features.ContainerFormat.ContainerVertical import ContainerVertical


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# directive: transcode-flow-canonical -- C33i grep-fence + behavioral fence
@dataclass
class _FakeMf:
    Id: int = 1
    Codec: Optional[str] = 'av1'
    Resolution: Optional[str] = '1280x720'
    ResolutionCategory: Optional[str] = '720p'
    VideoBitrateKbps: Optional[int] = 500
    FrameRate: Optional[float] = 24.0
    ContainerFormat: Optional[str] = 'mp4'
    AssignedProfile: Optional[str] = None
    TranscodedByMediaVortex: bool = False


class _StubVideoDb:
    def ExecuteQuery(self, _Sql, _Params=None):
        return [{'acceptablevideocodecscsv': 'av1'}]


class _StubContainerDb:
    def ExecuteQuery(self, _Sql, _Params=None):
        return [{'acceptablecontainerscsv': 'mp4'}]


# directive: transcode-flow-canonical -- C33
class TestVerticalsAreProfileIndependent(unittest.TestCase):

    def test_video_vertical_source_does_not_import_effective_profile_resolver(self):
        Src = (_REPO_ROOT / 'Features' / 'VideoEncoding' / 'VideoVertical.py').read_text(encoding='utf-8')
        self.assertNotIn('EffectiveProfileResolver', Src,
            "VideoVertical must not reference EffectiveProfileResolver per C33")

    def test_container_vertical_source_does_not_import_effective_profile_resolver(self):
        Src = (_REPO_ROOT / 'Features' / 'ContainerFormat' / 'ContainerVertical.py').read_text(encoding='utf-8')
        self.assertNotIn('EffectiveProfileResolver', Src,
            "ContainerVertical must not reference EffectiveProfileResolver per C33")

    def test_audio_vertical_source_does_not_import_effective_profile_resolver(self):
        Src = (_REPO_ROOT / 'Features' / 'AudioNormalization' / 'AudioVertical.py').read_text(encoding='utf-8')
        self.assertNotIn('EffectiveProfileResolver', Src,
            "AudioVertical must not reference EffectiveProfileResolver per C33")

    def test_video_vertical_accepts_null_assigned_profile(self):
        Mf = _FakeMf(AssignedProfile=None)
        Compliant, Reason = VideoVertical(Db=_StubVideoDb()).Evaluate(Mf)
        self.assertTrue(Compliant)
        self.assertIsNone(Reason)

    def test_container_vertical_accepts_null_assigned_profile(self):
        Mf = _FakeMf(AssignedProfile=None)
        Compliant, Reason = ContainerVertical(Db=_StubContainerDb()).Evaluate(Mf)
        self.assertTrue(Compliant)
        self.assertIsNone(Reason)

    def test_no_effective_profile_reason_purged_from_verticals(self):
        for Vertical in ('VideoVertical', 'ContainerVertical', 'AudioVertical'):
            Path_ = (
                _REPO_ROOT / 'Features' / ('VideoEncoding' if Vertical == 'VideoVertical'
                    else 'ContainerFormat' if Vertical == 'ContainerVertical'
                    else 'AudioNormalization') / f'{Vertical}.py'
            )
            Src = Path_.read_text(encoding='utf-8')
            self.assertNotIn('no_effective_profile', Src,
                f"{Vertical} must not emit 'no_effective_profile' per C33")


if __name__ == '__main__':
    unittest.main()
