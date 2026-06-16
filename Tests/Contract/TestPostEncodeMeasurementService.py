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

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C15
    def test_probe_returns_false_when_no_streams(self):
        Svc = PostEncodeMeasurementService(FFmpegPath='/usr/bin/ffmpeg', FFprobePath='/usr/bin/ffprobe')
        with patch.object(Svc, 'ListAudioStreams', return_value=[]):
            self.assertFalse(Svc.Probe(TranscodeAttemptId=42, OutputFilePath='/tmp/out.mp4'))

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C15
    def test_probe_returns_false_when_binaries_unresolvable(self):
        Svc = PostEncodeMeasurementService()
        self.assertFalse(Svc.Probe(TranscodeAttemptId=42, OutputFilePath='/tmp/out.mp4'))

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
