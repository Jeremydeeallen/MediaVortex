from typing import Dict, Any, Optional
from Repositories.DatabaseManager import DatabaseManager
from Services.FileManagerService import FileManagerService
from Core.Logging.LoggingService import LoggingService
from Core.Path.Path import Path, PathError
from Core.Path.PathStorageRoots import GetPrefixMap
from Core.Path.LocalPath import LocalExists


# directive: path-schema-migration | # see path.S9
class ComplianceGate:
    """Pre-rename cascade check; see compliance-gated-rename.feature.md."""

    # directive: filereplacement-decompose
    def __init__(self, DatabaseManagerInstance: DatabaseManager = None,
                 FileManagerInstance: FileManagerService = None,
                 FFprobePath: str = None):
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
        self.FileManager = FileManagerInstance or FileManagerService(FFprobePath=FFprobePath)

    # directive: path-schema-migration | # see path.S8 | filereplacement-decompose | compliance-gated-rename.C1, C4
    def Evaluate(self, LocalStagedPath: str, SourceMediaFileId: int,
                 FFmpegCommand: Optional[str] = None) -> Dict[str, Any]:
        """Evaluate staged file against the cascade; see compliance-gated-rename.C1, C4."""
        try:
            from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService

            def _SynthFP(Row) -> str:
                Sid = Row.get('StorageRootId')
                if Sid is None:
                    return ""
                try:
                    return Path(Sid, Row.get('RelativePath') or '').CanonicalDisplay(GetPrefixMap())
                except PathError:
                    return ""

            if not LocalExists(LocalStagedPath):
                return {'Compliant': False, 'RefusalReason': 'staged_file_missing'}

            ProbeResult = self.FileManager.ExtractMediaMetadata(LocalStagedPath)
            if not ProbeResult.get('Success', False):
                return {'Compliant': False, 'RefusalReason': 'probe_failed'}

            # allow: R12 SQL preexisting; relocate to MediaFileRepository in mediafile-persistence-no-drift
            SourceRows = self.DatabaseManager.DatabaseService.ExecuteQuery(
                """
                SELECT Id, StorageRootId, RelativePath, AssignedProfile,
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
                'FilePath': _SynthFP(Src),
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
                from Features.AudioNormalization.Services.AudioCompletionService import AudioCompletionService
                if FFmpegCommand and AudioCompletionService.DetectNormalizationInCommand(FFmpegCommand):
                    CandidateRow['AudioComplete'] = True
            except Exception:
                pass

            # directive: audio-vertical-live-encode-gaps | # see audio-normalization.C11
            try:
                import re as _ReAVC
                EmittedLangs = _ReAVC.findall(r'-metadata:s:a:\d+\s+"?language=([a-z]{2,3})"?', FFmpegCommand or '')
                if EmittedLangs:
                    CandidateRow['AudioLanguages'] = ','.join(EmittedLangs)
                    CandidateRow['HasExplicitEnglishAudio'] = any(L.lower() in ('eng', 'en') for L in EmittedLangs)
            except Exception:
                pass

            Eval = QueueManagementBusinessService().EvaluateCandidateCompliance(CandidateRow)

            if Eval.get('IsCompliant') is True and Eval.get('WorkBucket') is None:
                return {'Compliant': True, 'RefusalReason': None}

            RefusalReason = Eval.get('RefusalReason') or (
                f"undecidable_{Eval.get('WorkBucket') or 'unknown'}"
                if Eval.get('IsCompliant') is None
                else f"non_compliant_{Eval.get('WorkBucket') or 'unknown'}"
            )
            return {'Compliant': False, 'RefusalReason': RefusalReason}

        except Exception as e:
            LoggingService.LogException(
                f"Compliance gate raised for staged={LocalStagedPath}, SourceMediaFileId={SourceMediaFileId}",
                e, "ComplianceGate", "Evaluate"
            )
            return {'Compliant': False, 'RefusalReason': 'gate_evaluation_error'}
