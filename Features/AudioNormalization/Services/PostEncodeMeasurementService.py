import json
import subprocess
from typing import List, Optional

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Features.AudioNormalization.Measurement.EbuR128MeasurementService import ParseSummary


WRITE_TRACKS_EMITTED_SQL = (
    "UPDATE TranscodeAttempts "
    "SET AudioTracksEmittedJson = %s::jsonb "
    "WHERE Id = %s"
)


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C15
class PostEncodeMeasurementService:
    """Runs ffprobe -af ebur128 per output audio stream + writes TranscodeAttempts.AudioTracksEmittedJson."""

    DEFAULT_TIMEOUT_SECONDS = 300

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C15
    def __init__(self, FFmpegPath=None, FFprobePath=None):
        """Bind to specific binaries; resolve from WorkerContext when None."""
        self._FFmpegOverride = FFmpegPath
        self._FFprobeOverride = FFprobePath

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C15
    def _ResolveBinaries(self):
        """Return (FFmpegPath, FFprobePath) using overrides or WorkerContext."""
        Ffmpeg = self._FFmpegOverride
        Ffprobe = self._FFprobeOverride
        if Ffmpeg and Ffprobe:
            return Ffmpeg, Ffprobe
        try:
            from Core.WorkerContext import WorkerContext
            Ctx = WorkerContext.Current()
            if Ctx:
                Ffmpeg = Ffmpeg or Ctx.FFmpegPath
                Ffprobe = Ffprobe or getattr(Ctx, 'FFprobePath', None)
        except Exception:
            pass
        return Ffmpeg, Ffprobe

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C15
    def ListAudioStreams(self, FFprobePath, OutputPath):
        """Return ffprobe audio stream metadata as a list of dicts; empty on failure."""
        try:
            Result = subprocess.run(
                [
                    FFprobePath, '-v', 'error', '-select_streams', 'a',
                    '-show_streams', '-of', 'json', OutputPath,
                ],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=60, check=False,
            )
            if Result.returncode != 0:
                return []
            Data = json.loads(Result.stdout.decode('utf-8', errors='replace') or '{}')
            return Data.get('streams') or []
        except Exception as Ex:
            LoggingService.LogException(
                f"PostEncodeMeasurement.ListAudioStreams failed for {OutputPath}",
                Ex, "PostEncodeMeasurementService", "ListAudioStreams",
            )
            return []

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C15
    def MeasureStream(self, FFmpegPath, OutputPath, StreamIndex):
        """Run ebur128 on one output audio stream; return LoudnessResult or None."""
        Cmd = [
            FFmpegPath, '-hide_banner', '-nostats', '-nostdin',
            '-i', OutputPath,
            '-map', f'0:a:{StreamIndex}',
            '-af', 'ebur128=peak=true',
            '-f', 'null',
            'NUL' if subprocess.os.name == 'nt' else '/dev/null',
        ]
        try:
            Result = subprocess.run(
                Cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                timeout=self.DEFAULT_TIMEOUT_SECONDS, check=False,
            )
            if Result.returncode != 0:
                return None
            Stderr = Result.stderr.decode('utf-8', errors='replace')
            return ParseSummary(Stderr)
        except Exception as Ex:
            LoggingService.LogException(
                f"PostEncodeMeasurement.MeasureStream failed for {OutputPath}:a:{StreamIndex}",
                Ex, "PostEncodeMeasurementService", "MeasureStream",
            )
            return None

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C15
    def Probe(self, TranscodeAttemptId, OutputFilePath):
        """Measure every output audio stream, build AudioTracksEmittedJson, write to TranscodeAttempts."""
        Ffmpeg, Ffprobe = self._ResolveBinaries()
        if not Ffmpeg or not Ffprobe:
            return False
        Streams = self.ListAudioStreams(Ffprobe, OutputFilePath)
        if not Streams:
            try:
                DatabaseService().ExecuteNonQuery(WRITE_TRACKS_EMITTED_SQL, ('[]', TranscodeAttemptId))
                return True
            except Exception as Ex:
                LoggingService.LogException(
                    f"PostEncodeMeasurement.Probe no-streams sentinel persist failed for AttemptId={TranscodeAttemptId}",
                    Ex, "PostEncodeMeasurementService", "Probe",
                )
                return False

        Results = []
        for Stream in Streams:
            Idx = Stream.get('index')
            Tags = Stream.get('tags') or {}
            Label = Tags.get('title') or 'Track'
            Language = Tags.get('language') or 'und'
            Measure = self.MeasureStream(Ffmpeg, OutputFilePath, len(Results))
            if Measure is not None:
                Results.append({
                    'TrackIndex': Idx,
                    'Label': Label,
                    'Language': Language,
                    'Strategy': 'measured',
                    'AchievedIntegratedLufs': Measure.IntegratedLufs,
                    'AchievedTruePeakDbtp': Measure.TruePeakDbtp,
                    'AchievedLra': Measure.LoudnessRangeLU,
                })
            else:
                Results.append({
                    'TrackIndex': Idx,
                    'Label': Label,
                    'Language': Language,
                    'Strategy': 'measurement_failed',
                    'AchievedIntegratedLufs': None,
                    'AchievedTruePeakDbtp': None,
                    'AchievedLra': None,
                })

        try:
            DatabaseService().ExecuteNonQuery(
                WRITE_TRACKS_EMITTED_SQL,
                (json.dumps(Results), TranscodeAttemptId),
            )
            return True
        except Exception as Ex:
            LoggingService.LogException(
                f"PostEncodeMeasurement.Probe persist failed for AttemptId={TranscodeAttemptId}",
                Ex, "PostEncodeMeasurementService", "Probe",
            )
            return False
