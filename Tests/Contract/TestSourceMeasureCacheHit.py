# directive: preencode-loudness-cache-hit | # see audio-normalization.C7
import threading
import unittest
from unittest.mock import MagicMock, patch

from Features.AudioNormalization.Services.PreEncodeAudioPipeline import PreEncodeAudioPipeline


class _FakeIsolation:
    VocalsRmsDbfs = -18.0


class _FakeDemucs:
    ModelName = 'htdemucs'

    def __init__(self):
        self.MeasureSourceLoudnormCallCount = 0

    def MeasureSourceLoudnorm(self, *args, **kwargs):
        self.MeasureSourceLoudnormCallCount += 1
        return (-24.9, 7.1, -1.9, -35.5)

    def IsolateVocals(self, *args, **kwargs):
        return _FakeIsolation()

    def MixBoostedPremix(self, *args, **kwargs):
        pass

    def MeasurePremixLoudnorm(self, *args, **kwargs):
        return (-20.0, 5.0, -5.0, -30.0)


class _FakeRules:
    @staticmethod
    def GetRules():
        return {
            'TargetTruePeakDbtp': -1.0, 'SampleLimitHeadroomDb': 0.5,
            'TargetIntegratedLufs': -23.0, 'SourceMeasureTargetLra': 7.0,
            'VocalsBoostDb': 6.0, 'InstrumentalAttenDb': -6.0,
            'PremixCompressorThreshold': -20.0, 'PremixCompressorRatio': 4.0,
            'PremixCompressorMakeupDb': 3.0, 'PremixDynaudnormFrameLen': 500,
            'PremixDynaudnormGaussSize': 31, 'DialogBoostTargetLufs': -20.0,
            'DialogBoostTargetLra': 5.0,
        }


def _BuildPipeline(Demucs):
    P = PreEncodeAudioPipeline(
        FfmpegPath='ffmpeg', PythonExe='python',
        DemucsService=Demucs, ScratchRoot='/tmp',
    )
    P._RulesRepo = _FakeRules()
    P._ExtractStereoDownmix = MagicMock(return_value='downmix.wav')
    return P


class TestSourceMeasureCacheHit(unittest.TestCase):

    # directive: preencode-loudness-cache-hit -- fully-populated MediaFiles row skips ffmpeg pass entirely
    def test_cache_hit_skips_ffmpeg(self):
        Demucs = _FakeDemucs()
        P = _BuildPipeline(Demucs)
        Cached = (-22.5, 6.4, -2.1, -34.0)
        with patch('Features.MediaFiles.MediaFilesRepository.MediaFilesRepository') as MockRepoCls:
            MockRepoCls.return_value.GetSourceLoudness.return_value = Cached
            Result = P.Run('/src/movie.mkv', JobId=1, MediaFileId=42)
        self.assertEqual(Demucs.MeasureSourceLoudnormCallCount, 0)
        self.assertEqual(Result['SourceMeasuredI'], -22.5)
        self.assertEqual(Result['SourceMeasuredLra'], 6.4)
        self.assertEqual(Result['SourceMeasuredTp'], -2.1)
        self.assertEqual(Result['SourceMeasuredThresh'], -34.0)

    # directive: preencode-loudness-cache-hit -- any NULL in the 4 columns falls back to ffmpeg pass
    def test_cache_miss_null_columns_runs_ffmpeg(self):
        Demucs = _FakeDemucs()
        P = _BuildPipeline(Demucs)
        with patch('Features.MediaFiles.MediaFilesRepository.MediaFilesRepository') as MockRepoCls:
            MockRepoCls.return_value.GetSourceLoudness.return_value = None
            Result = P.Run('/src/movie.mkv', JobId=2, MediaFileId=42)
        self.assertEqual(Demucs.MeasureSourceLoudnormCallCount, 1)
        self.assertEqual(Result['SourceMeasuredI'], -24.9)
        self.assertEqual(Result['SourceMeasuredLra'], 7.1)
        self.assertEqual(Result['SourceMeasuredTp'], -1.9)
        self.assertEqual(Result['SourceMeasuredThresh'], -35.5)

    # directive: preencode-loudness-cache-hit -- no MediaFileId provided (defensive default): treat as cache-miss
    def test_no_media_file_id_runs_ffmpeg(self):
        Demucs = _FakeDemucs()
        P = _BuildPipeline(Demucs)
        Result = P.Run('/src/movie.mkv', JobId=3, MediaFileId=None)
        self.assertEqual(Demucs.MeasureSourceLoudnormCallCount, 1)
        self.assertEqual(Result['SourceMeasuredI'], -24.9)

    # directive: preencode-loudness-cache-hit -- MediaFileId not passed (kwarg omitted): backward-compat, treated as cache-miss
    def test_signature_backward_compat(self):
        Demucs = _FakeDemucs()
        P = _BuildPipeline(Demucs)
        Result = P.Run('/src/movie.mkv', JobId=4)
        self.assertEqual(Demucs.MeasureSourceLoudnormCallCount, 1)
        self.assertIsNotNone(Result['SourceMeasuredI'])


if __name__ == '__main__':
    unittest.main()
