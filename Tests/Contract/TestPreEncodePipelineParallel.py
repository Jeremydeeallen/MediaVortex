# directive: pre-encode-pipeline-parallel | # see audio-normalization.C14
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from Features.AudioNormalization.Services.PreEncodeAudioPipeline import PreEncodeAudioPipeline


class _FakeIsolation:
    VocalsRmsDbfs = -18.5


class _FakeDemucs:
    ModelName = 'htdemucs'

    def __init__(self, SourceMeasureDelay=0.0, ChainDelay=0.0,
                 SourceMeasureExc=None, ChainExc=None):
        self._SourceMeasureDelay = SourceMeasureDelay
        self._ChainDelay = ChainDelay
        self._SourceMeasureExc = SourceMeasureExc
        self._ChainExc = ChainExc
        self.SourceMeasureCalledFrom = None
        self.PremixMeasureCalledFrom = None
        self.ChainOrder = []
        self._Lock = threading.Lock()

    def MeasureSourceLoudnorm(self, SourceFilePath, TargetLufs, TargetLra, TargetTruePeakDbtp, ProgressCallback=None):
        self.SourceMeasureCalledFrom = threading.current_thread().name
        if self._SourceMeasureDelay:
            time.sleep(self._SourceMeasureDelay)
        if self._SourceMeasureExc:
            raise self._SourceMeasureExc
        return (-24.1, 6.2, -1.5, -35.0)

    def IsolateVocals(self, DownmixWavPath, ScratchDir, ProgressCallback=None):
        with self._Lock:
            self.ChainOrder.append('demucs')
        if self._ChainDelay:
            time.sleep(self._ChainDelay)
        if self._ChainExc:
            raise self._ChainExc
        return _FakeIsolation()

    def MixBoostedPremix(self, Isolation, PremixWavPath, **kwargs):
        with self._Lock:
            self.ChainOrder.append('premix')

    def MeasurePremixLoudnorm(self, PremixWavPath, TargetLufs, TargetLra, TargetTruePeakDbtp, ProgressCallback=None):
        with self._Lock:
            self.ChainOrder.append('loudnorm')
        self.PremixMeasureCalledFrom = threading.current_thread().name
        return (-20.0, 5.0, -5.0, -30.0)


class _FakeRules:
    @staticmethod
    def GetRules():
        return {
            'TargetTruePeakDbtp': -1.0,
            'SampleLimitHeadroomDb': 0.5,
            'TargetIntegratedLufs': -23.0,
            'SourceMeasureTargetLra': 7.0,
            'VocalsBoostDb': 6.0,
            'InstrumentalAttenDb': -6.0,
            'PremixCompressorThreshold': -20.0,
            'PremixCompressorRatio': 4.0,
            'PremixCompressorMakeupDb': 3.0,
            'PremixDynaudnormFrameLen': 500,
            'PremixDynaudnormGaussSize': 31,
            'DialogBoostTargetLufs': -20.0,
            'DialogBoostTargetLra': 5.0,
        }


def _BuildPipeline(Demucs, ScratchRoot):
    P = PreEncodeAudioPipeline(
        FfmpegPath='ffmpeg',
        PythonExe='python',
        DemucsService=Demucs,
        ScratchRoot=ScratchRoot,
    )
    P._RulesRepo = _FakeRules()
    P._ExtractStereoDownmix = MagicMock(return_value='downmix.wav')
    return P


class TestPreEncodePipelineParallel(unittest.TestCase):

    # directive: pre-encode-pipeline-parallel
    def test_success_returns_all_loudnorm_fields(self):
        Demucs = _FakeDemucs()
        P = _BuildPipeline(Demucs, ScratchRoot='/tmp')
        Result = P.Run('/src/movie.mkv', JobId=999)
        self.assertEqual(Result['SourceMeasuredI'], -24.1)
        self.assertEqual(Result['SourceMeasuredLra'], 6.2)
        self.assertEqual(Result['SourceMeasuredTp'], -1.5)
        self.assertEqual(Result['SourceMeasuredThresh'], -35.0)
        self.assertEqual(Result['PremixMeasuredI'], -20.0)
        self.assertEqual(Result['PremixMeasuredLra'], 5.0)
        self.assertEqual(Result['PremixMeasuredTp'], -5.0)
        self.assertEqual(Result['PremixMeasuredThresh'], -30.0)
        self.assertEqual(Result['VocalsRmsDbfs'], -18.5)

    # directive: pre-encode-pipeline-parallel -- SourceMeasure runs on a separate named thread; chain runs on the caller thread
    def test_source_measure_runs_on_separate_thread(self):
        Demucs = _FakeDemucs()
        P = _BuildPipeline(Demucs, ScratchRoot='/tmp')
        P.Run('/src/movie.mkv', JobId=1234)
        self.assertEqual(Demucs.SourceMeasureCalledFrom, 'PreEncodeSourceMeasureTask-1234'.replace('Task', ''))
        self.assertIsNotNone(Demucs.PremixMeasureCalledFrom)
        self.assertNotEqual(Demucs.SourceMeasureCalledFrom, Demucs.PremixMeasureCalledFrom)

    # directive: pre-encode-pipeline-parallel -- C2 wall reduction proof: parallel wall <= max(source, chain) + eps
    def test_parallel_execution_saves_wall_time(self):
        Demucs = _FakeDemucs(SourceMeasureDelay=0.30, ChainDelay=0.30)
        P = _BuildPipeline(Demucs, ScratchRoot='/tmp')
        Start = time.perf_counter()
        P.Run('/src/movie.mkv', JobId=1)
        Elapsed = time.perf_counter() - Start
        # Sequential predecessor would be ~0.60s (0.30 + 0.30). Parallel should be near 0.30s + orchestration overhead. Allow 0.55s cap.
        self.assertLess(Elapsed, 0.55, f"parallel wall {Elapsed:.3f}s should beat sequential 0.60s")

    # directive: pre-encode-pipeline-parallel -- C4 failure propagation: SourceMeasure raise surfaces after chain completes
    def test_source_measure_exception_propagates_after_chain_join(self):
        Demucs = _FakeDemucs(
            SourceMeasureDelay=0.05,
            SourceMeasureExc=RuntimeError("loudnorm subprocess exit 1"),
        )
        P = _BuildPipeline(Demucs, ScratchRoot='/tmp')
        Result = P.Run('/src/movie.mkv', JobId=1)
        # Per C39, exception is caught by Run's outer try/except and returned as DemucsFailed dict
        self.assertTrue(Result.get('DemucsFailed'))
        self.assertIn('RuntimeError', Result.get('DemucsFailureReason', ''))

    # directive: pre-encode-pipeline-parallel -- C4 failure propagation: chain exception waits for peer join then propagates
    def test_chain_exception_waits_for_source_measure_before_raising(self):
        Demucs = _FakeDemucs(
            SourceMeasureDelay=0.20,
            ChainExc=RuntimeError("demucs daemon closed stdout unexpectedly"),
        )
        P = _BuildPipeline(Demucs, ScratchRoot='/tmp')
        Start = time.perf_counter()
        Result = P.Run('/src/movie.mkv', JobId=1)
        Elapsed = time.perf_counter() - Start
        self.assertTrue(Result.get('DemucsFailed'))
        self.assertIn('demucs daemon', Result.get('DemucsFailureReason', ''))
        # Chain fails immediately; SourceMeasure needs its 0.20s. Peer join means total >= 0.20s.
        self.assertGreaterEqual(Elapsed, 0.19)


if __name__ == '__main__':
    unittest.main()
