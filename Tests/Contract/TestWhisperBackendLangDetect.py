import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.Services.LanguageEnrichmentService import WhisperFfmpegBackend, REPO_ROOT


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.L3
class TestWhisperBackendLangDetect(unittest.TestCase):
    """L3: backend assembles whisper JSON-line transcript and produces a real ISO 639-1 code via langdetect."""

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.L3
    def test_model_path_for_filter_strips_drive_colon(self):
        Backend = WhisperFfmpegBackend()
        ModelPath = os.path.join(REPO_ROOT, 'AIModels', 'ggml-tiny.bin')
        FilterArg = Backend._ModelPathForFilter(ModelPath)
        self.assertEqual(FilterArg, 'AIModels/ggml-tiny.bin')
        self.assertNotIn(':', FilterArg)

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.L3
    def test_model_path_outside_repo_root_refused(self):
        Backend = WhisperFfmpegBackend()
        FilterArg = Backend._ModelPathForFilter(os.path.join(REPO_ROOT, '..', 'evil', 'model.bin'))
        self.assertIsNone(FilterArg)

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.L3
    def test_lang_detect_english_transcript(self):
        Backend = WhisperFfmpegBackend()
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.jsonl', delete=False, dir=REPO_ROOT, encoding='utf-8'
        ) as F:
            for Seg in [
                {'start': 0, 'end': 2000, 'text': 'Happy Valentines Day Bob.'},
                {'start': 2000, 'end': 5000, 'text': 'It was so nice of them to give us free champagne.'},
                {'start': 5000, 'end': 8000, 'text': 'Well there is nothing free about it; it is part of the package.'},
            ]:
                F.write(json.dumps(Seg) + '\n')
            Path = F.name
        try:
            Result = Backend._LangDetectFromTranscript(Path)
        finally:
            os.remove(Path)
        self.assertEqual(Result['Language'], 'en')
        self.assertGreater(Result['Confidence'], 0.9)

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.L3
    def test_lang_detect_skips_music_bracketed_segments(self):
        Backend = WhisperFfmpegBackend()
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.jsonl', delete=False, dir=REPO_ROOT, encoding='utf-8'
        ) as F:
            F.write(json.dumps({'text': '[MUSIC PLAYING]'}) + '\n')
            F.write(json.dumps({'text': 'Bonjour tout le monde. Comment allez-vous aujourd hui mes amis.'}) + '\n')
            F.write(json.dumps({'text': "C'est une belle journee n'est-ce pas. Le soleil brille fort."}) + '\n')
            Path = F.name
        try:
            Result = Backend._LangDetectFromTranscript(Path)
        finally:
            os.remove(Path)
        self.assertEqual(Result['Language'], 'fr')

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.L3
    def test_lang_detect_missing_transcript_returns_und(self):
        Backend = WhisperFfmpegBackend()
        Result = Backend._LangDetectFromTranscript(os.path.join(REPO_ROOT, 'definitely_missing_transcript.jsonl'))
        self.assertEqual(Result['Language'], 'und')
        self.assertEqual(Result['Confidence'], 0.0)
        self.assertEqual(Result['Error'], 'transcript_not_produced')

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.L3
    def test_lang_detect_too_short_returns_und(self):
        Backend = WhisperFfmpegBackend()
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.jsonl', delete=False, dir=REPO_ROOT, encoding='utf-8'
        ) as F:
            F.write(json.dumps({'text': 'Hi.'}) + '\n')
            Path = F.name
        try:
            Result = Backend._LangDetectFromTranscript(Path)
        finally:
            os.remove(Path)
        self.assertEqual(Result['Language'], 'und')
        self.assertEqual(Result['Error'], 'transcript_too_short')


if __name__ == '__main__':
    unittest.main()
