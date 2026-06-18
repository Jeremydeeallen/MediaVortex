import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.Services.AudioStreamProbe import AudioStreamProbe


FFMPEG = r'C:\Code\MediaVortex\FFmpegMaster\bin\ffmpeg.exe'
FFPROBE = r'C:\Code\MediaVortex\FFmpegMaster\bin\ffprobe.exe'


# directive: audio-vertical-live-evidence | # see audio-normalization.L1
class TestAudioStreamProbe(unittest.TestCase):
    """L1: probe enumerates audio streams with sequential audio-only indices + language + default disposition."""

    # directive: audio-vertical-live-evidence | # see audio-normalization.L1
    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(FFMPEG) or not os.path.isfile(FFPROBE):
            raise unittest.SkipTest('ffmpeg/ffprobe missing')

    # directive: audio-vertical-live-evidence | # see audio-normalization.L1
    def test_returns_empty_when_no_ffprobe_path(self):
        Probe = AudioStreamProbe()
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as F:
            P = F.name
        try:
            self.assertEqual(Probe.Probe(P), [])
        finally:
            os.remove(P)

    # directive: audio-vertical-live-evidence | # see audio-normalization.L1
    def test_returns_empty_when_path_missing(self):
        Probe = AudioStreamProbe(FFprobePath=FFPROBE)
        self.assertEqual(Probe.Probe(r'C:\definitely_missing_xyz.mp4'), [])

    # directive: audio-vertical-live-evidence | # see audio-normalization.L1
    def test_returns_empty_when_path_is_none(self):
        Probe = AudioStreamProbe(FFprobePath=FFPROBE)
        self.assertEqual(Probe.Probe(None), [])

    # directive: audio-vertical-live-evidence | # see audio-normalization.L1
    def test_enumerates_two_distinct_audio_streams_with_audio_only_indices(self):
        with tempfile.TemporaryDirectory() as Tmp:
            Source = str(Path(Tmp) / 'source.mp4')
            subprocess.run([
                FFMPEG, '-y',
                '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1',
                '-f', 'lavfi', '-i', 'sine=frequency=880:duration=1',
                '-map', '0:a', '-map', '1:a',
                '-c:a:0', 'aac', '-c:a:1', 'aac',
                '-metadata:s:a:0', 'language=jpn',
                '-metadata:s:a:1', 'language=eng',
                '-disposition:a:1', 'default',
                Source,
            ], capture_output=True, check=True)
            Streams = AudioStreamProbe(FFprobePath=FFPROBE).Probe(Source)
        self.assertEqual(len(Streams), 2)
        self.assertEqual(Streams[0]['index'], 0)
        self.assertEqual(Streams[1]['index'], 1)
        self.assertEqual(Streams[0]['tags'].get('language'), 'jpn')
        self.assertEqual(Streams[1]['tags'].get('language'), 'eng')
        self.assertEqual(Streams[1]['disposition'].get('default'), 1)


if __name__ == '__main__':
    unittest.main()
