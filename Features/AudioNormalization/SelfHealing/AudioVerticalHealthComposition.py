from Features.AudioNormalization.SelfHealing.AudioVerticalHealthService import AudioVerticalHealthService
from Features.AudioNormalization.SelfHealing.Invariants.PendingQueueWithoutPolicyJson import PendingQueueWithoutPolicyJson
from Features.AudioNormalization.SelfHealing.Invariants.SuccessfulAttemptWithoutTracksEmitted import SuccessfulAttemptWithoutTracksEmitted
from Features.AudioNormalization.SelfHealing.Invariants.StaleOperatorReview import StaleOperatorReview
from Features.AudioNormalization.SelfHealing.Invariants.InvalidMeasurementWithoutRemeasure import InvalidMeasurementWithoutRemeasure
from Features.AudioNormalization.SelfHealing.Invariants.PreVerticalTranscodedFile import PreVerticalTranscodedFile
from Features.AudioNormalization.SelfHealing.Invariants.ConsistencyBandDeviantWithComplete import ConsistencyBandDeviantWithComplete
from Features.AudioNormalization.SelfHealing.Remediations.BackfillPolicyJson import BackfillPolicyJson
from Features.AudioNormalization.SelfHealing.Remediations.EnqueueReProbe import EnqueueReProbe
from Features.AudioNormalization.SelfHealing.Remediations.AlertOperatorReview import AlertOperatorReview
from Features.AudioNormalization.SelfHealing.Remediations.EnqueueRemeasurement import EnqueueRemeasurement
from Features.AudioNormalization.SelfHealing.Remediations.EnqueueRetranscode import EnqueueRetranscode


# directive: audio-vertical-live-evidence | # see audio-normalization.H1
def BuildAudioVerticalHealthService(RemediationBatch=None):
    """Composition root: wires 6 invariants + 5 remediations into a ready-to-run AudioVerticalHealthService."""
    Invariants = [
        PendingQueueWithoutPolicyJson(),
        SuccessfulAttemptWithoutTracksEmitted(),
        StaleOperatorReview(),
        InvalidMeasurementWithoutRemeasure(),
        PreVerticalTranscodedFile(),
        ConsistencyBandDeviantWithComplete(),
    ]
    Remediations = {
        PendingQueueWithoutPolicyJson.Name: BackfillPolicyJson(),
        SuccessfulAttemptWithoutTracksEmitted.Name: EnqueueReProbe(),
        StaleOperatorReview.Name: AlertOperatorReview(),
        InvalidMeasurementWithoutRemeasure.Name: EnqueueRemeasurement(),
        PreVerticalTranscodedFile.Name: EnqueueRetranscode(),
        ConsistencyBandDeviantWithComplete.Name: EnqueueRetranscode(),
    }
    return AudioVerticalHealthService(Invariants, Remediations, RemediationBatch=RemediationBatch)
