import time
from typing import Dict, List

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService


INSERT_AUDIT_SQL = (
    "INSERT INTO AudioVerticalHealthRuns "
    "(InvariantName, DetectedCount, RemediatedCount, DurationMs, Notes) "
    "VALUES (%s, %s, %s, %s, %s)"
)


DEFAULT_REMEDIATION_BATCH = 100


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
class AudioVerticalHealthService:
    """Recurring scan + remediation orchestrator; constructor injects List[invariant] + Dict[name -> remediation]."""

    # directive: audio-vertical-phase-1-completion | # see directive.md P2
    def __init__(self, Invariants, Remediations, RemediationBatch=None, DryRun=False):
        """Inject the list of invariants and the matched remediations dict (keyed by invariant Name). DryRun runs Detect but never Remediation.Apply; audit row carries DRY_RUN prefix."""
        self.Invariants = list(Invariants or [])
        self.Remediations = dict(Remediations or {})
        self.RemediationBatch = int(RemediationBatch or DEFAULT_REMEDIATION_BATCH)
        self.DryRun = bool(DryRun)

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
    def RunCycle(self):
        """Run every invariant + matched remediation once; return list of per-invariant outcome dicts."""
        Outcomes = []
        for Invariant in self.Invariants:
            Start = time.perf_counter()
            try:
                Detected = Invariant.Detect() or []
            except Exception as Ex:
                LoggingService.LogException(
                    f"Invariant.Detect raised for {Invariant.Name}",
                    Ex, "AudioVerticalHealthService", "RunCycle",
                )
                Detected = []
            Remediated = 0
            Notes = None
            Remediation = self.Remediations.get(Invariant.Name)
            if Remediation is not None and Detected:
                Batch = Detected[:self.RemediationBatch]
                if len(Detected) > self.RemediationBatch:
                    Notes = f"capped {len(Detected)}->{self.RemediationBatch}"
                if self.DryRun:
                    Notes = f"DRY_RUN: would have remediated {len(Batch)}" + (f" ({Notes})" if Notes else "")
                else:
                    try:
                        Remediated = Remediation.Apply(Batch) or 0
                    except Exception as Ex:
                        LoggingService.LogException(
                            f"Remediation.Apply raised for {Invariant.Name}",
                            Ex, "AudioVerticalHealthService", "RunCycle",
                        )
            DurationMs = int((time.perf_counter() - Start) * 1000)
            Outcomes.append({
                'Invariant': Invariant.Name,
                'Detected': len(Detected),
                'Remediated': Remediated,
                'DurationMs': DurationMs,
                'Notes': Notes,
            })
            self._WriteAudit(Invariant.Name, len(Detected), Remediated, DurationMs, Notes=Notes)
        return Outcomes

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
    def _WriteAudit(self, InvariantName, Detected, Remediated, DurationMs, Notes=None):
        """Persist one AudioVerticalHealthRuns row per invariant per cycle."""
        try:
            DatabaseService().ExecuteNonQuery(
                INSERT_AUDIT_SQL,
                (InvariantName, int(Detected), int(Remediated), int(DurationMs), Notes),
            )
        except Exception as Ex:
            LoggingService.LogException(
                f"AudioVerticalHealthService audit write failed for {InvariantName}",
                Ex, "AudioVerticalHealthService", "_WriteAudit",
            )
