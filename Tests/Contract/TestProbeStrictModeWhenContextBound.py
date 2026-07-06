import json
from unittest.mock import MagicMock, patch

import pytest

from Core.WorkerContext import WorkerContext, WorkerContextNotBoundError
from Features.AudioNormalization.Services.PostEncodeMeasurementService import PostEncodeMeasurementService


@pytest.fixture(autouse=True)
def _ResetContext():
    WorkerContext.Reset()
    yield
    WorkerContext.Reset()


def test_Probe_raises_when_context_unbound():
    Svc = PostEncodeMeasurementService()
    with pytest.raises(WorkerContextNotBoundError):
        Svc.Probe(TranscodeAttemptId=999999, OutputFilePath="/tmp/nonexistent.mp4", QueueId=None)


def test_Probe_raises_when_binaries_unresolved_on_bound_context():
    WorkerContext.Initialize(WorkerName="test-worker", Platform="linux", FFmpegPath=None, FFprobePath=None)
    Svc = PostEncodeMeasurementService()
    with pytest.raises(RuntimeError, match="binaries unresolved"):
        Svc.Probe(TranscodeAttemptId=999999, OutputFilePath="/tmp/nonexistent.mp4", QueueId=None)


def test_Probe_writes_resolved_attestation_from_ffprobe_when_bound():
    WorkerContext.Initialize(WorkerName="test-worker", Platform="linux", FFmpegPath="/opt/ffmpeg", FFprobePath="/opt/ffprobe")
    Svc = PostEncodeMeasurementService()

    Streams = [{"index": 1, "tags": {"handler_name": "Original", "language": "eng", "title": "Original"}}]
    ListMock = MagicMock(return_value=Streams)
    Measured = MagicMock(IntegratedLufs=-23.0, TruePeakDbtp=-1.5, LoudnessRangeLU=6.0)
    MeasureMock = MagicMock(return_value=Measured)

    Captured = {}

    def CapturingExecuteNonQuery(Sql, Params):
        Captured["Sql"] = Sql
        Captured["Params"] = Params
        return None

    DbInstance = MagicMock()
    DbInstance.ExecuteNonQuery.side_effect = CapturingExecuteNonQuery

    with patch.object(Svc, "ListAudioStreams", ListMock), \
         patch.object(Svc, "MeasureStream", MeasureMock), \
         patch("Features.AudioNormalization.Services.PostEncodeMeasurementService.DatabaseService", return_value=DbInstance):
        Result = Svc.Probe(TranscodeAttemptId=42, OutputFilePath="/tmp/out.mp4", QueueId=7)

    assert Result is True
    assert Captured["Params"][1] == "resolved"
    assert Captured["Params"][2] == 7
    assert Captured["Params"][3] == 42
    Written = json.loads(Captured["Params"][0])
    assert len(Written) == 1
    assert Written[0]["Strategy"] == "measured"
    assert Written[0]["AchievedIntegratedLufs"] == -23.0
    assert Written[0]["AchievedTruePeakDbtp"] == -1.5


def test_Probe_writes_unresolved_sentinel_when_no_streams():
    WorkerContext.Initialize(WorkerName="test-worker", Platform="linux", FFmpegPath="/opt/ffmpeg", FFprobePath="/opt/ffprobe")
    Svc = PostEncodeMeasurementService()

    Captured = {}

    def CapturingExecuteNonQuery(Sql, Params):
        Captured["Params"] = Params
        return None

    DbInstance = MagicMock()
    DbInstance.ExecuteNonQuery.side_effect = CapturingExecuteNonQuery

    with patch.object(Svc, "ListAudioStreams", MagicMock(return_value=[])), \
         patch("Features.AudioNormalization.Services.PostEncodeMeasurementService.DatabaseService", return_value=DbInstance):
        Svc.Probe(TranscodeAttemptId=42, OutputFilePath="/tmp/out.mp4", QueueId=7)

    assert Captured["Params"][1] == "unresolved"
    Written = json.loads(Captured["Params"][0])
    assert Written == []
