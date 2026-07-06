import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.Services.PostEncodeMeasurementService import (
    PostEncodeMeasurementService,
)
from Features.AudioNormalization.Measurement.EbuR128MeasurementService import LoudnessResult


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C15
class TestPostEncodeMeasurementService(unittest.TestCase):
    """C15: per-track ebur128 -> TranscodeAttempts.AudioTracksEmittedJson."""

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C15
    def test_probe_writes_per_stream_results(self):
        Svc = PostEncodeMeasurementService(FFmpegPath='/usr/bin/ffmpeg', FFprobePath='/usr/bin/ffprobe')
        Streams = [
            {'index': 1, 'tags': {'title': 'Original', 'language': 'eng'}},
            {'index': 2, 'tags': {'title': 'Dialog Boost', 'language': 'eng'}},
        ]
        Measure = LoudnessResult(IntegratedLufs=-23.0, LoudnessRangeLU=9.0, TruePeakDbtp=-2.0, IntegratedThresholdLufs=-33.0)
        with patch.object(Svc, 'ListAudioStreams', return_value=Streams) as MockList, \
             patch.object(Svc, 'MeasureStream', return_value=Measure) as MockMeasure, \
             patch('Features.AudioNormalization.Services.PostEncodeMeasurementService.DatabaseService') as MockDb:
            Instance = MagicMock()
            MockDb.return_value = Instance
            Ok = Svc.Probe(TranscodeAttemptId=42, OutputFilePath='/tmp/out.mp4')
            self.assertTrue(Ok)
            self.assertEqual(MockMeasure.call_count, 2)
            Args = Instance.ExecuteNonQuery.call_args.args
            Json = args_json = Args[1][0]
            Parsed = json.loads(Json)
            self.assertEqual(len(Parsed), 2)
            self.assertEqual(Parsed[0]['Label'], 'Original')
            self.assertEqual(Parsed[1]['Label'], 'Dialog Boost')
            self.assertEqual(Parsed[0]['AchievedIntegratedLufs'], -23.0)

    # directive: transcode-flow-canonical | # see transcode.ST5 -- BUG-0086 attestation lands regardless
    def test_probe_attests_unresolved_when_no_streams(self):
        Svc = PostEncodeMeasurementService(FFmpegPath='/usr/bin/ffmpeg', FFprobePath='/usr/bin/ffprobe')
        with patch.object(Svc, 'ListAudioStreams', return_value=[]), \
             patch('Features.AudioNormalization.Services.PostEncodeMeasurementService.DatabaseService') as MockDb:
            Instance = MagicMock()
            MockDb.return_value = Instance
            Svc.Probe(TranscodeAttemptId=42, OutputFilePath='/tmp/out.mp4', QueueId=99)
            Args = Instance.ExecuteNonQuery.call_args.args
            self.assertEqual(json.loads(Args[1][0]), [])
            self.assertEqual(Args[1][1], 'unresolved')

    # directive: transcode-flow-canonical -- C20 strict-mode: raise when binaries unresolvable
    def test_probe_raises_when_binaries_unresolvable(self):
        from Core.WorkerContext import WorkerContext, WorkerContextNotBoundError
        WorkerContext.Reset()
        try:
            Svc = PostEncodeMeasurementService()
            with self.assertRaises(WorkerContextNotBoundError):
                Svc.Probe(TranscodeAttemptId=42, OutputFilePath='/tmp/out.mp4', QueueId=99)
            WorkerContext.Initialize(WorkerName='test', Platform='linux', FFmpegPath=None, FFprobePath=None)
            with self.assertRaises(RuntimeError):
                Svc.Probe(TranscodeAttemptId=42, OutputFilePath='/tmp/out.mp4', QueueId=99)
        finally:
            WorkerContext.Reset()

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C15
    def test_probe_records_measurement_failure_per_stream(self):
        Svc = PostEncodeMeasurementService(FFmpegPath='/usr/bin/ffmpeg', FFprobePath='/usr/bin/ffprobe')
        Streams = [{'index': 1, 'tags': {'title': 'Track1', 'language': 'eng'}}]
        with patch.object(Svc, 'ListAudioStreams', return_value=Streams), \
             patch.object(Svc, 'MeasureStream', return_value=None), \
             patch('Features.AudioNormalization.Services.PostEncodeMeasurementService.DatabaseService') as MockDb:
            Instance = MagicMock()
            MockDb.return_value = Instance
            Svc.Probe(TranscodeAttemptId=42, OutputFilePath='/tmp/out.mp4')
            Json = Instance.ExecuteNonQuery.call_args.args[1][0]
            Parsed = json.loads(Json)
            self.assertEqual(Parsed[0]['Strategy'], 'measurement_failed')


if __name__ == '__main__':
    unittest.main()
