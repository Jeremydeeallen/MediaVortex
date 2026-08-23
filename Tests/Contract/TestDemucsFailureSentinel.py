# directive: dialog-boost-marker-unify | # see dialog-boost-marker-unify.C5
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.Services.PreEncodeAudioPipeline import PreEncodeAudioPipeline


class TestDemucsFailureSentinel(unittest.TestCase):

    def test_pipeline_returns_failure_sentinel_when_downmix_raises(self):
        MockDemucs = MagicMock()
        MockDemucs.ModelName = 'htdemucs'
        MockDemucs.Device = 'cpu'
        MockDemucs.MeasureSourceLoudnorm.return_value = (None, None, None, None)
        Pipeline = PreEncodeAudioPipeline(FfmpegPath='/does/not/exist/ffmpeg', PythonExe='python', DemucsService=MockDemucs)
        with patch.object(Pipeline, '_ExtractStereoDownmix', side_effect=RuntimeError('stereo downmix failed (exit 1): boom')):
            Result = Pipeline.Run(SourceFilePath='/tmp/fake.mkv', JobId=99999)
        self.assertIsInstance(Result, dict)
        self.assertIs(Result['DemucsFailed'], True)
        self.assertIn('RuntimeError', Result['DemucsFailureReason'])
        self.assertIn('boom', Result['DemucsFailureReason'])
        self.assertIsNone(Result['DemucsPremixPath'])
        self.assertIsNone(Result['VocalsRmsDbfs'])

    def test_pipeline_returns_failure_sentinel_when_demucs_isolate_raises(self):
        MockDemucs = MagicMock()
        MockDemucs.ModelName = 'htdemucs'
        MockDemucs.Device = 'cuda'
        MockDemucs.MeasureSourceLoudnorm.return_value = (None, None, None, None)
        MockDemucs.IsolateVocals.side_effect = FileNotFoundError('demucs binary not on PATH')
        Pipeline = PreEncodeAudioPipeline(FfmpegPath='/does/not/exist/ffmpeg', PythonExe='python', DemucsService=MockDemucs)
        with patch.object(Pipeline, '_ExtractStereoDownmix', return_value='/tmp/downmix.wav'):
            Result = Pipeline.Run(SourceFilePath='/tmp/fake.mkv', JobId=99998)
        self.assertIs(Result['DemucsFailed'], True)
        self.assertIn('FileNotFoundError', Result['DemucsFailureReason'])

    def test_failure_reason_capped_at_200_chars(self):
        MockDemucs = MagicMock()
        MockDemucs.ModelName = 'htdemucs'
        MockDemucs.Device = 'cpu'
        MockDemucs.MeasureSourceLoudnorm.return_value = (None, None, None, None)
        LongMsg = 'X' * 5000
        Pipeline = PreEncodeAudioPipeline(FfmpegPath='/does/not/exist/ffmpeg', PythonExe='python', DemucsService=MockDemucs)
        with patch.object(Pipeline, '_ExtractStereoDownmix', side_effect=RuntimeError(LongMsg)):
            Result = Pipeline.Run(SourceFilePath='/tmp/fake.mkv', JobId=99997)
        Prefix = 'RuntimeError: '
        self.assertTrue(Result['DemucsFailureReason'].startswith(Prefix))
        Body = Result['DemucsFailureReason'][len(Prefix):]
        self.assertLessEqual(len(Body), 200)


if __name__ == '__main__':
    unittest.main()
