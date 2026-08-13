from typing import List, Optional, Tuple

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Features.MediaFile.Domain.MediaFileScope import IsAudioOnlyContainer
from Repositories.DatabaseManager import DatabaseManager
from Features.AudioNormalization.AudioPolicyAdmissionGate import AudioPolicyAdmissionGate


# directive: transcode-flow-canonical -- C33
class AudioVertical:

    # directive: transcode-flow-canonical -- C33 profile-independent baseline
    def __init__(self, Gate: Optional[AudioPolicyAdmissionGate] = None, Db: Optional[DatabaseService] = None, RepoMgr: Optional[DatabaseManager] = None):
        self._Gate = Gate or AudioPolicyAdmissionGate()
        self._Db = Db or DatabaseService()
        self._RepoMgr = RepoMgr or DatabaseManager()

    # directive: worker-runtime-state
    def _LoadRules(self) -> dict:
        # directive: audio-dialog-boost-real | # see audio-normalization.C8
        Rows = self._Db.ExecuteQuery(
            "SELECT TargetIntegratedLufs, TargetTruePeakDbtp, AcceptableAudioCodecsCsv "
            "FROM AudioComplianceRules ORDER BY Id LIMIT 1"
        )
        if not Rows:
            raise RuntimeError('AudioComplianceRules has no rows -- migration not applied')
        R = Rows[0]
        Csv = (R.get('AcceptableAudioCodecsCsv') or R.get('acceptableaudiocodecscsv') or '').strip()
        AllowedCodecs = [C.strip().lower() for C in Csv.split(',') if C.strip()]
        return {
            'TargetIntegratedLufs': float(R.get('TargetIntegratedLufs') if 'TargetIntegratedLufs' in R else R.get('targetintegratedlufs')),
            'TargetTruePeakDbtp': float(R.get('TargetTruePeakDbtp') if 'TargetTruePeakDbtp' in R else R.get('targettruepeakdbtp')),
            'AllowedCodecs': AllowedCodecs,
        }

    # directive: audio-vertical-dialog-boost-enforcement
    def Evaluate(self, Mf) -> Tuple[Optional[bool], Optional[str]]:
        if IsAudioOnlyContainer(Mf):
            return (None, 'non_video_scope')
        if getattr(Mf, 'AudioCorruptSuspect', None) is True:
            return (None, 'audio_corrupt_suspect')
        if not getattr(Mf, 'AudioCodec', None) and getattr(Mf, 'Resolution', None):
            return (None, 'no_audio_stream')
        Rules = self._LoadRules()
        SrcCodec = (getattr(Mf, 'AudioCodec', None) or '').lower()
        if SrcCodec and Rules['AllowedCodecs'] and SrcCodec not in Rules['AllowedCodecs']:
            return (False, f'codec:{SrcCodec}')
        Decision = self._Gate.AdmitOrDefer(Mf)
        if Decision.Outcome != 'admitted':
            return (None, Decision.DeferReason)
        if getattr(Mf, 'HasDialogBoostTrack', None) is True:
            return (True, None)
        return (False, 'no_dialog_boost')

    # directive: compliance-reason-full-library-recompute -- batch orchestrator isolates per-row so one bad row does not abort a batch; Evaluate stays fail-loud
    def RecomputeFor(self, MediaFileIds: List[int]) -> None:
        for Id in MediaFileIds:
            try:
                Mf = self._RepoMgr.GetMediaFileById(Id)
                if Mf is None:
                    LoggingService.LogWarning(f"AudioVertical.RecomputeFor: MediaFileId {Id} not found; skipping", "AudioVertical", "RecomputeFor")
                    continue
                Compliant, Reason = self.Evaluate(Mf)
                self._WriteResult(Id, Compliant, Reason)
            # fail-loud-ok: batch-orchestrator per-row isolation; Evaluate stays fail-loud per audio-normalization contract; each row surfaces via LogException
            except Exception as Ex:
                LoggingService.LogException(f"AudioVertical.RecomputeFor: MediaFileId {Id} raised; skipping", Ex, "AudioVertical", "RecomputeFor")
                continue

    # directive: transcode-flow-canonical -- C33
    def _WriteResult(self, MediaFileId: int, Compliant, Reason):
        self._Db.ExecuteNonQuery(
            "UPDATE MediaFiles SET AudioCompliant = %s, AudioCompliantReason = %s WHERE Id = %s",
            (Compliant, Reason, MediaFileId),
        )
        LoggingService.LogInfo(f"AudioVertical.RecomputeFor Id={MediaFileId} -> Compliant={Compliant}, Reason={Reason!r}", "AudioVertical", "_WriteResult")
