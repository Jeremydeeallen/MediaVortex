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


# directive: bug-0087-audio-per-stream-channels | # see audio-normalization.L1
class TestAudioStreamProbeChannels(unittest.TestCase):
    """C1: AudioStreamProbe emits per-stream channels (+ channel_layout) so downstream can gate per-stream, not per-file."""

    # directive: bug-0087-audio-per-stream-channels | # see audio-normalization.L1
    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(FFMPEG) or not os.path.isfile(FFPROBE):
            raise unittest.SkipTest('ffmpeg/ffprobe missing')

    # directive: bug-0087-audio-per-stream-channels | # see audio-normalization.L1
    def test_probe_emits_channels_per_stream_mixed_layout(self):
        with tempfile.TemporaryDirectory() as Tmp:
            Source = str(Path(Tmp) / 'mixed.mp4')
            subprocess.run([
                FFMPEG, '-y',
                '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1',
                '-f', 'lavfi', '-i', 'sine=frequency=880:duration=1:sample_rate=48000',
                '-map', '0:a', '-map', '1:a',
                '-c:a:0', 'aac', '-ac:0', '2',
                '-c:a:1', 'aac', '-ac:1', '6', '-channel_layout:a:1', '5.1',
                '-metadata:s:a:0', 'language=fre',
                '-metadata:s:a:1', 'language=eng',
                '-disposition:a:1', 'default',
                Source,
            ], capture_output=True, check=True)
            Streams = AudioStreamProbe(FFprobePath=FFPROBE).Probe(Source)
        self.assertEqual(len(Streams), 2)
        Channels = [S['channels'] for S in Streams]
        self.assertEqual(Channels, [2, 6])
        self.assertIn('channel_layout', Streams[0])
        self.assertIn('channel_layout', Streams[1])
        self.assertEqual(Streams[1]['tags'].get('language'), 'eng')


if __name__ == '__main__':
    unittest.main()
