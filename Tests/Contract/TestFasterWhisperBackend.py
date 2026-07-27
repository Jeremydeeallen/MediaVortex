import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.Services.FasterWhisperBackend import FasterWhisperBackend


# directive: audio-language-detection
class TestFasterWhisperBackend(unittest.TestCase):

    def test_detect_returns_und_when_ffmpeg_path_unresolved(self):
        Backend = FasterWhisperBackend()
        Result = Backend.Detect('/tmp/x.mp4', 0)
        self.assertEqual(Result['Language'], 'und')
        self.assertEqual(Result['Error'], 'ffmpeg_unavailable')

    def test_detect_returns_und_when_ffmpeg_extract_fails(self):
        Backend = FasterWhisperBackend(FFmpegPath='/usr/bin/ffmpeg')
        with patch('Features.AudioNormalization.Services.FasterWhisperBackend.subprocess.run') as MockRun:
            MockRun.return_value = MagicMock(returncode=1, stderr=b'boom')
            Result = Backend.Detect('/tmp/x.mp4', 0)
            self.assertEqual(Result['Language'], 'und')

    def test_detect_normalizes_language_lowercase(self):
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            self.skipTest('faster_whisper not installed in this venv (production hosts pip-install it)')
        Backend = FasterWhisperBackend(FFmpegPath='/usr/bin/ffmpeg')
        FakeModel = MagicMock()
        FakeModel.detect_language.return_value = ('EN', 0.95, None)
        with patch('Features.AudioNormalization.Services.FasterWhisperBackend.subprocess.run') as MockRun, \
             patch.object(Backend, '_GetOrLoadModel', return_value=FakeModel), \
             patch('faster_whisper.audio.decode_audio', return_value=[0.0] * 16000, create=True):
            MockRun.return_value = MagicMock(returncode=0, stderr=b'')
            Result = Backend.Detect('/tmp/x.mp4', 0)
            self.assertEqual(Result['Language'], 'en')
            self.assertAlmostEqual(Result['Confidence'], 0.95, places=3)


if __name__ == '__main__':
    unittest.main()
