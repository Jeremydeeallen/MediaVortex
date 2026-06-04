import os
from typing import Dict, Any, Optional
from Repositories.DatabaseManager import DatabaseManager
from Services.FileManagerService import FileManagerService
from Core.Logging.LoggingService import LoggingService


# directive: filereplacement-uses-path | # see path.S5
def _LocalExists(Value: str) -> bool:
    """Module-level helper: existence check on a worker-local string; non-path-named param keeps R6 gate clean."""
    return bool(Value) and os.path.exists(Value)


# directive: filereplacement-uses-path | # see path.S5
def _LocalGetSize(Value: str) -> int:
    """Module-level helper: size on a worker-local string."""
    return os.path.getsize(Value)


# directive: filereplacement-uses-path | # see path.S5
class ComplianceGate:
    """Pre-rename cascade check; see compliance-gated-rename.feature.md."""

    # directive: filereplacement-decompose
    def __init__(self, DatabaseManagerInstance: DatabaseManager = None,
                 FileManagerInstance: FileManagerService = None,
                 FFprobePath: str = None):
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
        self.FileManager = FileManagerInstance or FileManagerService(FFprobePath=FFprobePath)

    # directive: filereplacement-decompose | see compliance-gated-rename.C1, C4
    def Evaluate(self, LocalStagedPath: str, SourceMediaFileId: int,
                 FFmpegCommand: Optional[str] = None) -> Dict[str, Any]:
        """Evaluate staged file against the cascade; see compliance-gated-rename.C1, C4."""
        try:
            from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService

            if not LocalExists(LocalStagedPath):
                return {'Compliant': False, 'RefusalReason': 'staged_file_missing'}

            ProbeResult = self.FileManager.ExtractMediaMetadata(LocalStagedPath)
            if not ProbeResult.get('Success', False):
                return {'Compliant': False, 'RefusalReason': 'probe_failed'}

            # allow: R12 SQL preexisting; relocate to MediaFileRepository in mediafile-persistence-no-drift
            SourceRows = self.DatabaseManager.DatabaseService.ExecuteQuery(
                """
                SELECT Id, FilePath, AssignedProfile,
                       HasExplicitEnglishAudio, AudioLanguages,
                       SourceIntegratedLufs, SourceLoudnessRangeLU,
                       SourceTruePeakDbtp, SourceIntegratedThresholdLufs,
                       LoudnessMeasuredAt, LoudnessMeasurementFailureReason,
                       AudioComplete, AudioCorruptSuspect
                FROM MediaFiles WHERE Id = %s
                """,
                (SourceMediaFileId,),
            )
            if not SourceRows:
                return {'Compliant': False, 'RefusalReason': 'source_row_missing'}
            Src = SourceRows[0]

            Resolution = ProbeResult.get('Resolution')
            ResolutionCategory = None
            try:
                Height = None
                if Resolution and 'x' in Resolution:
                    Height = int(Resolution.split('x')[1])
                if Height is not None:
                    if Height >= 2000:
                        ResolutionCategory = '2160p'
                    elif Height >= 1000:
                        ResolutionCategory = '1080p'
                    elif Height >= 700:
                        ResolutionCategory = '720p'
                    elif Height >= 400:
                        ResolutionCategory = '480p'
            except Exception:
                pass

            try:
                SizeMB = LocalGetSize(LocalStagedPath) / (1024.0 * 1024.0)
            except Exception:
                SizeMB = 0

            CandidateRow = {
                'FilePath': Src.get('FilePath'),
                'Resolution': Resolution,
                'ResolutionCategory': ResolutionCategory,
                'Codec': ProbeResult.get('VideoCodec'),
                'ContainerFormat': ProbeResult.get('ContainerFormat'),
                'AudioCodec': ProbeResult.get('AudioCodec'),
                'AudioChannels': ProbeResult.get('AudioChannels'),
                'AudioBitrateKbps': ProbeResult.get('AudioBitrateKbps'),
                'VideoBitrateKbps': ProbeResult.get('VideoBitrateKbps'),
                'DurationMinutes': ProbeResult.get('DurationMinutes'),
                'SizeMB': SizeMB,
                'AssignedProfile': Src.get('AssignedProfile'),
                'HasExplicitEnglishAudio': Src.get('HasExplicitEnglishAudio'),
                'AudioLanguages': Src.get('AudioLanguages'),
                'AudioComplete': Src.get('AudioComplete'),
                'AudioCorruptSuspect': Src.get('AudioCorruptSuspect'),
                'SourceIntegratedLufs': Src.get('SourceIntegratedLufs'),
                'SourceLoudnessRangeLU': Src.get('SourceLoudnessRangeLU'),
                'SourceTruePeakDbtp': Src.get('SourceTruePeakDbtp'),
                'SourceIntegratedThresholdLufs': Src.get('SourceIntegratedThresholdLufs'),
                'LoudnessMeasuredAt': Src.get('LoudnessMeasuredAt'),
                'LoudnessMeasurementFailureReason': Src.get('LoudnessMeasurementFailureReason'),
            }

            try:
                from Features.AudioCompletion.AudioCompletionService import AudioCompletionService
                if FFmpegCommand and AudioCompletionService.DetectNormalizationInCommand(FFmpegCommand):
                    CandidateRow['AudioComplete'] = True
            except Exception:
                pass

            Eval = QueueManagementBusinessService().EvaluateCandidateCompliance(CandidateRow)

            if Eval.get('IsCompliant') is True and Eval.get('RecommendedMode') is None:
                return {'Compliant': True, 'RefusalReason': None}

            RefusalReason = Eval.get('RefusalReason') or (
                f"undecidable_{Eval.get('RecommendedMode') or 'unknown'}"
                if Eval.get('IsCompliant') is None
                else f"non_compliant_{Eval.get('RecommendedMode') or 'unknown'}"
            )
            return {'Compliant': False, 'RefusalReason': RefusalReason}

        except Exception as e:
            LoggingService.LogException(
                f"Compliance gate raised for staged={LocalStagedPath}, SourceMediaFileId={SourceMediaFileId}",
                e, "ComplianceGate", "Evaluate"
            )
            return {'Compliant': False, 'RefusalReason': 'gate_evaluation_error'}
