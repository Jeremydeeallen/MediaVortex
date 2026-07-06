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

READ_TRACKS_EMITTED_SQL = (
    "SELECT AudioTracksEmittedJson FROM TranscodeAttempts WHERE Id = %s"
)

# directive: transcode-flow-canonical | # see transcode.ST5
WRITE_ATTEMPT_ATTESTATION_SQL = (
    "UPDATE TranscodeAttempts "
    "SET AudioTracksEmittedJson = %s::jsonb, "
    "    AudioPolicyResolved = %s, "
    "    AudioPolicyJson = COALESCE("
    "        (SELECT AudioPolicyJson FROM TranscodeQueue WHERE Id = %s), "
    "        AudioPolicyJson"
    "    ) "
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

    # directive: transcode-flow-canonical
    def _ResolveBinaries(self):
        """Return (FFmpegPath, FFprobePath) from overrides or WorkerContext; raises when unresolved."""
        Ffmpeg = self._FFmpegOverride
        Ffprobe = self._FFprobeOverride
        if Ffmpeg and Ffprobe:
            return Ffmpeg, Ffprobe
        from Core.WorkerContext import WorkerContext
        Ctx = WorkerContext.Current()
        Ffmpeg = Ffmpeg or Ctx.FFmpegPath
        Ffprobe = Ffprobe or getattr(Ctx, 'FFprobePath', None)
        if not Ffmpeg or not Ffprobe:
            raise RuntimeError(
                f"PostEncodeMeasurement: binaries unresolved (ffmpeg={Ffmpeg}, ffprobe={Ffprobe}) "
                f"from WorkerContext {Ctx.WorkerName}"
            )
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

    # directive: transcode-flow-canonical
    def Probe(self, TranscodeAttemptId, OutputFilePath, QueueId=None):
        """Measure every output audio stream; write AudioTracksEmittedJson + AudioPolicyResolved verdict + AudioPolicyJson in one UPDATE. Strict-mode: raises when binaries unresolved (fail-loud per C20)."""
        Ffmpeg, Ffprobe = self._ResolveBinaries()
        Streams = self.ListAudioStreams(Ffprobe, OutputFilePath)
        if not Streams:
            return self._PersistAttestation(TranscodeAttemptId, QueueId, [], 'unresolved')

        Results = []
        AnyMeasureFailed = False
        for Stream in Streams:
            Idx = Stream.get('index')
            Tags = Stream.get('tags') or {}
            Handler = (Tags.get('handler_name') or '').strip()
            Label = Tags.get('title') or (Handler.split(' (')[0] if Handler and Handler != 'SoundHandler' else 'Track')
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
                AnyMeasureFailed = True
                Results.append({
                    'TrackIndex': Idx,
                    'Label': Label,
                    'Language': Language,
                    'Strategy': 'measurement_failed',
                    'AchievedIntegratedLufs': None,
                    'AchievedTruePeakDbtp': None,
                    'AchievedLra': None,
                })

        Verdict = 'mixed' if AnyMeasureFailed else 'resolved'
        return self._PersistAttestation(TranscodeAttemptId, QueueId, Results, Verdict)

    # directive: transcode-flow-canonical | # see transcode.ST5 | # see audio-normalization.C5
    def _PersistAttestation(self, TranscodeAttemptId, QueueId, Results, Verdict):
        """Single UPDATE that lands AudioTracksEmittedJson + AudioPolicyResolved + AudioPolicyJson (snapshot from queue)."""
        try:
            DatabaseService().ExecuteNonQuery(
                WRITE_ATTEMPT_ATTESTATION_SQL,
                (json.dumps(Results), Verdict, QueueId, TranscodeAttemptId),
            )
            return True
        except Exception as Ex:
            LoggingService.LogException(
                f"PostEncodeMeasurement._PersistAttestation failed for AttemptId={TranscodeAttemptId} Verdict={Verdict}",
                Ex, "PostEncodeMeasurementService", "_PersistAttestation",
            )
            return False

    # directive: audio-dialog-boost-real | # see audio-normalization.C39
    def PersistPreEncodeMeta(self, TranscodeAttemptId, VocalsRmsDbfs, DialogBoostEmitted, VocalsFallbackDbfs, DemucsFailed=False, DemucsFailureReason=None):
        """Merge Demucs vocals-stem RMS + Dialog Boost decision + Demucs failure signal onto AudioTracksEmittedJson so G5 verifier SQL can run and operators can distinguish deliberate skip from silent Demucs crash."""
        try:
            Rows = DatabaseService().ExecuteQuery(READ_TRACKS_EMITTED_SQL, (TranscodeAttemptId,))
            Current = Rows[0].get('audiotracksemittedjson') if Rows else None
            if isinstance(Current, str):
                Current = json.loads(Current) if Current else []
            if not isinstance(Current, list):
                Current = []
            Meta = {
                'vocals_rms_dbfs': None if VocalsRmsDbfs is None else float(VocalsRmsDbfs),
                'vocals_fallback_dbfs': None if VocalsFallbackDbfs is None else float(VocalsFallbackDbfs),
                'dialog_boost_emitted': bool(DialogBoostEmitted),
                'demucs_failed': bool(DemucsFailed),
                'demucs_failure_reason': DemucsFailureReason if DemucsFailed else None,
            }
            if not Current:
                Current = [dict(Meta, TrackIndex=None, Label='pre_encode_meta', Language='und', Strategy='pre_encode_meta_only')]
            else:
                for Entry in Current:
                    if isinstance(Entry, dict):
                        Entry.update(Meta)
            DatabaseService().ExecuteNonQuery(
                WRITE_TRACKS_EMITTED_SQL,
                (json.dumps(Current), TranscodeAttemptId),
            )
            return True
        except Exception as Ex:
            LoggingService.LogException(
                f"PostEncodeMeasurement.PersistPreEncodeMeta failed for AttemptId={TranscodeAttemptId}",
                Ex, "PostEncodeMeasurementService", "PersistPreEncodeMeta",
            )
            return False
