from typing import Optional
from Repositories.DatabaseManager import DatabaseManager
from Core.Logging.LoggingService import LoggingService
from Features.TranscodeJob.Emit.UngainablePeakError import UngainablePeakError


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C7
class AudioFilterBuilder:
    """Builds the linear-loudnorm filter per linear-loudnorm.feature.md; never falls back to dynamic mode."""

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C7
    def __init__(self, DatabaseManagerInstance: Optional[DatabaseManager] = None):
        """Inject DatabaseManager (DIP); default-constructs one if not provided."""
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C7
    def Build(self, MediaFile) -> Optional[str]:
        """Return the linear loudnorm filter string, None if normalization off, raise UngainablePeakError when fixed gain would clip."""
        Db = self.DatabaseManager

        AudioNormalizationEnabled = Db.GetSystemSetting('AudioNormalizationEnabled')
        if not (AudioNormalizationEnabled
                and AudioNormalizationEnabled.lower() in ('1', 'true', 'yes')):
            return None

        I_Lufs = getattr(MediaFile, 'SourceIntegratedLufs', None)
        L_Lu = getattr(MediaFile, 'SourceLoudnessRangeLU', None)
        P_Dbtp = getattr(MediaFile, 'SourceTruePeakDbtp', None)
        T_Lufs = getattr(MediaFile, 'SourceIntegratedThresholdLufs', None)

        Missing = [
            Name for Name, Val in (
                ('SourceIntegratedLufs', I_Lufs),
                ('SourceLoudnessRangeLU', L_Lu),
                ('SourceTruePeakDbtp', P_Dbtp),
                ('SourceIntegratedThresholdLufs', T_Lufs),
            ) if Val is None
        ]
        if Missing:
            MfId = getattr(MediaFile, 'Id', None)
            raise RuntimeError(
                f"BuildAudioFilters: loudnorm requested for MediaFileId={MfId} "
                f"but measurements missing: {', '.join(Missing)}. The admission "
                f"gate in QueueManagementBusinessService should have deferred "
                f"this file with AdmissionDeferReason="
                f"'awaiting_loudness_measurement' or 'loudness_measurement_failed'."
            )

        TargetI = int(Db.GetSystemSetting('TargetLoudness') or -23)
        TargetTp = int(Db.GetSystemSetting('TruePeak') or -2)
        Floor = int(Db.GetSystemSetting('MinimumLoudnessRangeLU') or 11)
        TargetLra = max(float(L_Lu), float(Floor))

        Gain = float(TargetI) - float(I_Lufs)
        PredictedPeak = float(P_Dbtp) + Gain
        LinearOk = PredictedPeak <= float(TargetTp)

        MeasuredArgs = (
            f"measured_I={float(I_Lufs):.2f}"
            f":measured_LRA={float(L_Lu):.2f}"
            f":measured_TP={float(P_Dbtp):.2f}"
            f":measured_thresh={float(T_Lufs):.2f}"
        )
        Common = (
            f"loudnorm=I={TargetI}:LRA={TargetLra:.2f}:TP={TargetTp}"
            f":{MeasuredArgs}"
        )

        if not LinearOk:
            MfId = getattr(MediaFile, 'Id', None)
            raise UngainablePeakError(MfId, float(I_Lufs), Gain, PredictedPeak, TargetTp)

        Filter = f"{Common}:linear=true"
        LoggingService.LogInfo(
            f"linear loudnorm: gain={Gain:+.2f} dB, "
            f"target_LRA={TargetLra:.2f} (source {float(L_Lu):.2f}), "
            f"MediaFileId={getattr(MediaFile, 'Id', None)}",
            "AudioFilterBuilder", "Build",
        )
        return Filter
