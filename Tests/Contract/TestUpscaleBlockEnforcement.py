# directive: profile-row-lookup | # see marginal-savings-gate.C2b -- Cartesian upscale coverage against the file's own row target.
import unittest
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
from Core.Models.MediaFileModel import MediaFileModel


RESOLUTIONS = ['480p', '720p', '1080p', '2160p']
RANK = {label: idx for idx, label in enumerate(RESOLUTIONS)}


# directive: profile-row-lookup | # see marginal-savings-gate.C2b
class _AdmissionConfigStub:
    MinTranscodeSavingsMB = 150
    MissingEstimatePolicy = 'admit'


# directive: profile-row-lookup | # see marginal-savings-gate.C2b
class TestUpscaleBlockEnforcement(unittest.TestCase):

    # directive: profile-row-lookup | # see marginal-savings-gate.C2b
    def setUp(self):
        self.Service = QueueManagementBusinessService()

    # directive: profile-row-lookup | # see marginal-savings-gate.C2b
    def _MakeMediaFile(self, sourceResolution: str) -> MediaFileModel:
        Mf = MediaFileModel()
        Mf.Resolution = sourceResolution
        Mf.SizeMB = 5000
        Mf.DurationMinutes = 60
        return Mf

    # directive: profile-row-lookup | # see marginal-savings-gate.C2b
    def _Settings(self, TargetLabel: str) -> dict:
        return {'TargetResolution': TargetLabel, 'TargetKbps': 0, 'Codec': 'libsvtav1', 'Quality': 28}

    # directive: profile-row-lookup | # see marginal-savings-gate.C2b
    def test_every_upscale_pair_blocks(self):
        Cfg = _AdmissionConfigStub()
        for SourceLabel in RESOLUTIONS:
            for TargetLabel in RESOLUTIONS:
                if RANK[SourceLabel] >= RANK[TargetLabel]:
                    continue
                with self.subTest(source=SourceLabel, target=TargetLabel):
                    ShouldBlock, Reason = self.Service.EvaluateQueueAdmission(self._MakeMediaFile(SourceLabel), self._Settings(TargetLabel), Cfg)
                    self.assertTrue(ShouldBlock, f"Upscale {SourceLabel}->{TargetLabel} was NOT blocked")
                    self.assertTrue(Reason.startswith('Upscale'), f"Upscale {SourceLabel}->{TargetLabel} blocked with non-Upscale reason: {Reason}")

    # directive: profile-row-lookup | # see marginal-savings-gate.C2b
    def test_same_resolution_pairs_not_blocked_for_upscale(self):
        Cfg = _AdmissionConfigStub()
        for Label in RESOLUTIONS:
            with self.subTest(resolution=Label):
                _ShouldBlock, Reason = self.Service.EvaluateQueueAdmission(self._MakeMediaFile(Label), self._Settings(Label), Cfg)
                self.assertFalse(Reason.startswith('Upscale'), f"Same-resolution {Label} blocked as upscale: {Reason}")

    # directive: profile-row-lookup | # see marginal-savings-gate.C2b
    def test_downscale_pairs_not_blocked_for_upscale(self):
        Cfg = _AdmissionConfigStub()
        for SourceLabel in RESOLUTIONS:
            for TargetLabel in RESOLUTIONS:
                if RANK[SourceLabel] <= RANK[TargetLabel]:
                    continue
                with self.subTest(source=SourceLabel, target=TargetLabel):
                    _ShouldBlock, Reason = self.Service.EvaluateQueueAdmission(self._MakeMediaFile(SourceLabel), self._Settings(TargetLabel), Cfg)
                    self.assertFalse(Reason.startswith('Upscale'), f"Downscale {SourceLabel}->{TargetLabel} blocked as upscale: {Reason}")


if __name__ == '__main__':
    unittest.main()
