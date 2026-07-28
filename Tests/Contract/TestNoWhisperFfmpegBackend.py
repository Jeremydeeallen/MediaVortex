import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# directive: audio-language-detection C2
class TestNoWhisperFfmpegBackend(unittest.TestCase):

    def test_whisperffmpegbackend_file_deleted(self):
        P = REPO_ROOT / 'Features' / 'AudioNormalization' / 'Services' / 'WhisperFfmpegBackend.py'
        self.assertFalse(P.exists(), 'WhisperFfmpegBackend.py must be deleted (fleet backend consolidation)')

    def test_no_references_in_production_code(self):
        Result = subprocess.run(
            ['git', 'grep', '-l', 'WhisperFfmpegBackend', '--',
             'Features/**/*.py', 'WorkerService/**/*.py', 'Core/**/*.py', 'Services/**/*.py'],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
        Hits = [L for L in Result.stdout.splitlines() if L.strip()]
        self.assertEqual(Hits, [], msg=f'WhisperFfmpegBackend still referenced in production python: {Hits}')

    def test_import_raises(self):
        with self.assertRaises(ImportError):
            from Features.AudioNormalization.Services.WhisperFfmpegBackend import WhisperFfmpegBackend  # noqa


if __name__ == '__main__':
    unittest.main()
