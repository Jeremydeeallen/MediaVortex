from Features.ServiceControl.JobPhase import JobPhase
from Features.ServiceControl.PhaseDetectors.SetupPhaseDetector import SetupPhaseDetector
from Features.ServiceControl.PhaseDetectors.EncodingPhaseDetector import EncodingPhaseDetector
from Features.ServiceControl.PhaseDetectors.PostEncodePhaseDetector import PostEncodePhaseDetector
from Features.ServiceControl.PhaseDetectors.VerifyingPhaseDetector import VerifyingPhaseDetector
from Features.ServiceControl.ProcessInspector import ProcessInspector


# directive: transcode-flow-canonical
class PhaseDetectorRegistry:
    """Strategy dispatch by JobPhase; Open/Closed against new phases (add row + detector class)."""

    # directive: transcode-flow-canonical
    def __init__(self, DatabaseManager, SystemSettingsRepositoryFactory=None):
        Inspector = ProcessInspector()
        self._Detectors = {
            JobPhase.Setup: SetupPhaseDetector(SystemSettingsRepositoryFactory=SystemSettingsRepositoryFactory),
            JobPhase.Encoding: EncodingPhaseDetector(
                DatabaseManager=DatabaseManager,
                ProcessInspector=Inspector,
                SystemSettingsRepositoryFactory=SystemSettingsRepositoryFactory,
            ),
            JobPhase.PostEncode: PostEncodePhaseDetector(SystemSettingsRepositoryFactory=SystemSettingsRepositoryFactory),
            JobPhase.Verifying: VerifyingPhaseDetector(SystemSettingsRepositoryFactory=SystemSettingsRepositoryFactory),
        }

    # directive: transcode-flow-canonical
    def GetDetector(self, Phase: JobPhase):
        if Phase not in self._Detectors:
            raise ValueError(f"No detector registered for phase {Phase!r}")
        return self._Detectors[Phase]
