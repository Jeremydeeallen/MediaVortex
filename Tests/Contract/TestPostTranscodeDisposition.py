"""Decision-table conformance tests for PostTranscodeDispositionService.

Covers feature criteria 4 and 5 of post-transcode-disposition.feature.md:
  - Every row of the canonical decision table in transcode.flow.md Stage 6 has
    a corresponding assertion here.
  - Each row is asserted twice (deterministic re-run) to catch any nondeterminism.

The tests target `_DecideFromInputs` because it is the pure function that encodes
the table; the surrounding I/O (DB read of TranscodeAttempts, ServiceStatus
lookup, audit UPDATE) is exercised separately. Decoupling the table from I/O
keeps the table-conformance test fast and total.

If you change the decision table in the flow doc, update both this test AND
`PostTranscodeDispositionService._DecideFromInputs` in the same commit.
"""

import sys
import unittest
from dataclasses import dataclass
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from Features.QualityTesting.PostTranscodeDispositionService import (
    PostTranscodeDispositionService,
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
        # Constructed without DB managers -- _DecideFromInputs is pure.
        self.Service = PostTranscodeDispositionService.__new__(PostTranscodeDispositionService)
        self.DefaultConfig = FakeGateConfig()

    def _Decide(self, **Kwargs):
        Defaults = dict(
            Success=True,
            OldSize=1_000_000_000,
            NewSize=500_000_000,
            QualityTestRequired=True,
            VmafScore=None,
            ServiceStatus='Running',
            GateConfig=self.DefaultConfig,
        )
        Defaults.update(Kwargs)
        return self.Service._DecideFromInputs(**Defaults)

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

    # Row 4: VMAF required, no score, service Running -> Pending / AwaitingVmaf.
    def test_Row4_AwaitingVmaf(self):
        self._AssertDeterministic(
            ('Pending', 'AwaitingVmaf'),
            VmafScore=None, ServiceStatus='Running',
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

    # Row 8: VMAF unavailable, ServiceStatus Paused, WhenVmafUnavailable='block'
    #        -> NoReplace / VmafServicePaused.
    def test_Row8_VmafServicePaused_Block(self):
        self._AssertDeterministic(
            ('NoReplace', 'VmafServicePaused'),
            VmafScore=None, ServiceStatus='Paused',
            GateConfig=FakeGateConfig(WhenVmafUnavailable='block'),
        )

    def test_Row8_VmafServicePaused_Block_Stopped(self):
        # Stopped is also non-Running -> same branch as Paused.
        self._AssertDeterministic(
            ('NoReplace', 'VmafServicePaused'),
            VmafScore=None, ServiceStatus='Stopped',
            GateConfig=FakeGateConfig(WhenVmafUnavailable='block'),
        )

    # Row 9: VMAF unavailable, ServiceStatus Paused, WhenVmafUnavailable='bypass'
    #        -> BypassReplace / VmafServicePausedBypassed.
    def test_Row9_VmafServicePaused_Bypass(self):
        self._AssertDeterministic(
            ('BypassReplace', 'VmafServicePausedBypassed'),
            VmafScore=None, ServiceStatus='Paused',
            GateConfig=FakeGateConfig(WhenVmafUnavailable='bypass'),
        )

    # Edge: priority of Discard/NoSavings over QualityTestRequired flag.
    def test_NoSavings_BeatsQualityTestNotRequired(self):
        # Even when QualityTestRequired=False, no-savings still discards.
        self._AssertDeterministic(
            ('Discard', 'NoSavings'),
            Success=True, OldSize=500_000_000, NewSize=600_000_000,
            QualityTestRequired=False,
        )

    # Edge: TranscodeFailed beats every other branch.
    def test_TranscodeFailed_BeatsEverything(self):
        self._AssertDeterministic(
            ('Discard', 'TranscodeFailed'),
            Success=False, QualityTestRequired=True, VmafScore=95.0, ServiceStatus='Paused',
        )


if __name__ == '__main__':
    unittest.main()
