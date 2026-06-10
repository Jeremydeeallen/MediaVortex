from unittest.mock import MagicMock
from Features.TranscodeJob.Worker.EncodeExecutor import EncodeExecutor


# directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C8
class TestEncodeExecutor:
    """EncodeExecutor contract tests: ctor wiring + UpdateProgress write + UpdateProgress resilience."""

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C8
    def test_ctor_stashes_deps(self):
        """EncodeExecutor stores the injected DatabaseManager + VideoTranscoding references."""
        Db = MagicMock()
        Vt = MagicMock()
        Executor = EncodeExecutor(Db, Vt)
        assert Executor.DatabaseManager is Db
        assert Executor.VideoTranscoding is Vt

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C8
    def test_update_progress_writes_row(self):
        """UpdateProgress invokes DatabaseManager.SaveTranscodeProgress once with the expected args."""
        Db = MagicMock()
        Vt = MagicMock()
        Executor = EncodeExecutor(Db, Vt)
        Executor.UpdateProgress(42, 'Probing', 12.5, 'extra')
        Db.SaveTranscodeProgress.assert_called_once_with(
            TranscodeAttemptId=42,
            CurrentPhase='Probing',
            ProgressPercent=12.5,
            CurrentFrame=0,
            CurrentFPS=0.0,
            CurrentBitrate='0kbits/s',
            CurrentTime='00:00:00',
            CurrentSpeed='0x',
            ETA='Unknown',
            TotalFrames=0,
            AverageFPS=0.0,
        )

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C8
    def test_update_progress_swallows_exceptions(self):
        """UpdateProgress returns None without propagating when the DB write raises."""
        Db = MagicMock()
        Db.SaveTranscodeProgress.side_effect = RuntimeError('DB exploded')
        Vt = MagicMock()
        Executor = EncodeExecutor(Db, Vt)
        Result = Executor.UpdateProgress(7, 'Transcoding', 0.0, '')
        assert Result is None
