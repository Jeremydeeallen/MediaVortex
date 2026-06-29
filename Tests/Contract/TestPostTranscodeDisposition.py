# directive: transcode-worker-unification -- decision-table conformance for PostTranscodeDispositionDecider; see disposition.feature.md C2.
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from Features.QualityTesting.Disposition.PostTranscodeDispositionDecider import (
    PostTranscodeDispositionDecider,
)


@dataclass
class FakeGateConfig:
    """Lightweight stand-in for PostTranscodeGateConfigModel."""
    VmafAutoReplaceMinThreshold: float = 88.0
    VmafAutoReplaceMaxThreshold: float = 98.0
    WhenVmafUnavailable: str = 'block'


class TestPostTranscodeDispositionTable(unittest.TestCase):
    """One method per row of transcode.flow.md Stage 6 decision table."""

    def setUp(self):
        self.Decider = PostTranscodeDispositionDecider()
        self.DefaultConfig = FakeGateConfig()

    def _Decide(self, **Kwargs):
        GateCfg = Kwargs.pop('GateConfig', self.DefaultConfig)
        Defaults = dict(
            Success=True,
            OldSize=1_000_000_000,
            NewSize=500_000_000,
            QualityTestRequired=True,
            VmafScore=None,
            VmafCapableWorkerOnline=True,
        )
        Defaults.update(Kwargs)
        GateInput = dict(
            VmafAutoReplaceMinThreshold=float(GateCfg.VmafAutoReplaceMinThreshold),
            VmafAutoReplaceMaxThreshold=float(GateCfg.VmafAutoReplaceMaxThreshold),
            WhenVmafUnavailable=GateCfg.WhenVmafUnavailable,
            QualityTestEnabled=True,
        )
        Outcome = self.Decider.Decide(Defaults, GateInput)
        return (Outcome.Action, Outcome.Reason)

    def _AssertDeterministic(self, Expected, **Kwargs):
        """Run twice, assert identical -- covers criterion 5."""
        self.assertEqual(self._Decide(**Kwargs), Expected)
        self.assertEqual(self._Decide(**Kwargs), Expected)

    # Row 1: transcode failed -> Discard / TranscodeFailed.
    def test_Row1_TranscodeFailed(self):
        self._AssertDeterministic(('Discard', 'TranscodeFailed'), Success=False)

    # Row 2: transcode succeeded but produced no savings.
    def test_Row2_NoSavings(self):
        self._AssertDeterministic(
            ('Discard', 'NoSavings'),
            Success=True, OldSize=500_000_000, NewSize=600_000_000,
        )

    # Row 3: QualityTestRequired=False -> BypassReplace / QualityTestNotRequired.
    def test_Row3_QualityTestNotRequired(self):
        self._AssertDeterministic(
            ('BypassReplace', 'QualityTestNotRequired'),
            QualityTestRequired=False,
        )

    # Row 4: VMAF required, no score, capable worker online -> Pending / AwaitingVmaf.
    def test_Row4_AwaitingVmaf(self):
        self._AssertDeterministic(
            ('Pending', 'AwaitingVmaf'),
            VmafScore=None, VmafCapableWorkerOnline=True,
        )

    # Row 5: VMAF score below min -> Requeue / VmafBelowMin.
    def test_Row5_VmafBelowMin(self):
        self._AssertDeterministic(
            ('Requeue', 'VmafBelowMin'),
            VmafScore=80.0,
        )

    # Row 6: VMAF score in [min, max] -> Replace / VmafPassed.
    def test_Row6a_VmafPassed_AtMin(self):
        self._AssertDeterministic(('Replace', 'VmafPassed'), VmafScore=88.0)

    def test_Row6b_VmafPassed_Mid(self):
        self._AssertDeterministic(('Replace', 'VmafPassed'), VmafScore=92.5)

    def test_Row6c_VmafPassed_AtMax(self):
        self._AssertDeterministic(('Replace', 'VmafPassed'), VmafScore=98.0)

    # Row 7: VMAF score above max -> NoReplace / VmafAboveMax.
    def test_Row7_VmafAboveMax(self):
        self._AssertDeterministic(('NoReplace', 'VmafAboveMax'), VmafScore=99.5)

    # Rows 8-9 (legacy `VmafServicePaused` / `VmafServicePausedBypassed`)
    # were retired by qt-queue-visibility-and-override.feature.md (2026-05-29).
    # The decision tree now returns `(Pending, AwaitingVmaf)` unconditionally
    # when VMAF is required and no score is available; the queue row is the
    # operator's visibility surface and the override endpoint is the manual
    # escape. The `VmafCapableWorkerOnline` input is no longer consulted by
    # `_DecideFromInputs`.
    def test_NoCapableWorker_StillReturnsPending_Block(self):
        self._AssertDeterministic(
            ('Pending', 'AwaitingVmaf'),
            VmafScore=None, VmafCapableWorkerOnline=False,
            GateConfig=FakeGateConfig(WhenVmafUnavailable='block'),
        )

    def test_NoCapableWorker_StillReturnsPending_Bypass(self):
        self._AssertDeterministic(
            ('Pending', 'AwaitingVmaf'),
            VmafScore=None, VmafCapableWorkerOnline=False,
            GateConfig=FakeGateConfig(WhenVmafUnavailable='bypass'),
        )

    # Edge: priority of Discard/NoSavings over QualityTestRequired flag.
    @unittest.expectedFailure
    def test_NoSavings_BeatsQualityTestNotRequired(self):
        # FLOW-DOC vs CODE DISCREPANCY (filed in
        # `.claude/programs/db-authority-program.md` deferred items):
        # The transcode.flow.md Stage 6 decision table lists "no savings" Discard
        # BEFORE the `QualityTestRequired=False -> BypassReplace` row. The
        # current `_DecideFromInputs` orders them the opposite way, with an
        # inline comment justifying the order for remux jobs (which set
        # QualityTestRequired=False and are not aimed at disk savings).
        # Resolution requires operator decision: either the flow doc reorders
        # to match code (and the no-savings gate becomes remux-aware) OR the
        # code reorders to match the flow doc (and remux jobs growing slightly
        # get Discarded). xfail until that decision lands.
        self._AssertDeterministic(
            ('Discard', 'NoSavings'),
            Success=True, OldSize=500_000_000, NewSize=600_000_000,
            QualityTestRequired=False,
        )

    # Edge: TranscodeFailed beats every other branch.
    def test_TranscodeFailed_BeatsEverything(self):
        self._AssertDeterministic(
            ('Discard', 'TranscodeFailed'),
            Success=False, QualityTestRequired=True, VmafScore=95.0, VmafCapableWorkerOnline=False,
        )


if __name__ == '__main__':
    unittest.main()
