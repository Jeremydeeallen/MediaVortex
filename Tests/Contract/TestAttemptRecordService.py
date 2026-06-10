from unittest.mock import MagicMock, patch
from Features.TranscodeJob.Worker.AttemptRecordService import AttemptRecordService


# directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C9
class TestAttemptRecordService:
    """AttemptRecordService contract tests: ctor wiring + Create + GetTotalFrames fallback."""

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C9
    def test_ctor_stashes_deps(self):
        """AttemptRecordService stores the injected DatabaseManager + WorkerName."""
        Db = MagicMock()
        Service = AttemptRecordService(Db, 'worker-larry-1')
        assert Service.DatabaseManager is Db
        assert Service.WorkerName == 'worker-larry-1'

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C9
    def test_create_returns_attempt_id_on_success(self):
        """Create returns the attempt id that DatabaseManager.SaveTranscodeAttempt produced."""
        Db = MagicMock()
        Db.SaveTranscodeAttempt.return_value = 4242
        Db.DatabaseService.ExecuteQuery.return_value = []
        Service = AttemptRecordService(Db, 'worker-larry-1')
        Job = MagicMock(StorageRootId=1, RelativePath='movie.mkv', SizeBytes=1000)
        MediaFile = MagicMock(AssignedProfile=None)
        Result = Service.Create(Job, MediaFile=MediaFile, TranscodingSettings={'ProfileSettings': {'Quality': 23}}, TranscodeCommand='ffmpeg ...')
        assert Result == 4242
        Db.SaveTranscodeAttempt.assert_called_once()

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C9
    def test_get_total_frames_falls_back(self):
        """When ffprobe analysis fails, GetTotalFrames returns 0 (the documented fallback)."""
        Db = MagicMock()
        Service = AttemptRecordService(Db, 'worker-larry-1')
        Job = MagicMock(FilePath='/media/movie.mkv')
        MediaFile = MagicMock(TotalFrames=0)
        with patch('Services.FFmpegAnalysisService.FFmpegAnalysisService') as MockAnalysis:
            Instance = MockAnalysis.return_value
            Instance.AnalyzeMediaFile.return_value = MagicMock(Success=False, TotalFrames=0)
            Result = Service.GetTotalFrames(Job, MediaFile=MediaFile)
        assert Result == 0
