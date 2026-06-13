# see marginal-savings-gate.C2b -- Cartesian upscale-block coverage.
import unittest
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
from Core.Models.MediaFileModel import MediaFileModel


RESOLUTIONS = ['480p', '720p', '1080p', '2160p']
RANK = {label: idx for idx, label in enumerate(RESOLUTIONS)}


class _AdmissionConfigStub:
    MinTranscodeSavingsMB = 150
    MissingEstimatePolicy = 'admit'


class TestUpscaleBlockEnforcement(unittest.TestCase):

    def setUp(self):
        self.Service = QueueManagementBusinessService()

    def _MakeMediaFile(self, sourceResolution: str) -> MediaFileModel:
        Mf = MediaFileModel()
        Mf.Resolution = sourceResolution
        Mf.SizeMB = 5000
        Mf.DurationMinutes = 60
        return Mf

    def test_every_upscale_pair_blocks(self):
        Cfg = _AdmissionConfigStub()
        for SourceLabel in RESOLUTIONS:
            for TargetLabel in RESOLUTIONS:
                if RANK[SourceLabel] >= RANK[TargetLabel]:
                    continue
                with self.subTest(source=SourceLabel, target=TargetLabel):
                    Mf = self._MakeMediaFile(SourceLabel)
                    Settings = {
                        'TargetResolution': SourceLabel,
                        'ProfileMaxTarget': TargetLabel,
                        'VideoBitrateKbps': 0,
                        'Codec': 'libsvtav1',
                        'Quality': 28,
                    }
                    ShouldBlock, Reason = self.Service.EvaluateQueueAdmission(
                        Mf, Settings, Cfg,
                    )
                    self.assertTrue(
                        ShouldBlock,
                        f"Upscale {SourceLabel}->{TargetLabel} was NOT blocked",
                    )
                    self.assertTrue(
                        Reason.startswith('Upscale'),
                        f"Upscale {SourceLabel}->{TargetLabel} blocked with non-Upscale reason: {Reason}",
                    )

    def test_same_resolution_pairs_not_blocked_for_upscale(self):
        Cfg = _AdmissionConfigStub()
        for Label in RESOLUTIONS:
            with self.subTest(resolution=Label):
                Mf = self._MakeMediaFile(Label)
                Settings = {
                    'TargetResolution': Label,
                    'ProfileMaxTarget': Label,
                    'VideoBitrateKbps': 0,
                    'Codec': 'libsvtav1',
                    'Quality': 28,
                }
                _ShouldBlock, Reason = self.Service.EvaluateQueueAdmission(
                    Mf, Settings, Cfg,
                )
                self.assertFalse(
                    Reason.startswith('Upscale'),
                    f"Same-resolution {Label} blocked as upscale: {Reason}",
                )

    def test_downscale_pairs_not_blocked_for_upscale(self):
        Cfg = _AdmissionConfigStub()
        for SourceLabel in RESOLUTIONS:
            for TargetLabel in RESOLUTIONS:
                if RANK[SourceLabel] <= RANK[TargetLabel]:
                    continue
                with self.subTest(source=SourceLabel, target=TargetLabel):
                    Mf = self._MakeMediaFile(SourceLabel)
                    Settings = {
                        'TargetResolution': TargetLabel,
                        'ProfileMaxTarget': TargetLabel,
                        'VideoBitrateKbps': 0,
                        'Codec': 'libsvtav1',
                        'Quality': 28,
                    }
                    _ShouldBlock, Reason = self.Service.EvaluateQueueAdmission(
                        Mf, Settings, Cfg,
                    )
                    self.assertFalse(
                        Reason.startswith('Upscale'),
                        f"Downscale {SourceLabel}->{TargetLabel} blocked as upscale: {Reason}",
                    )

    def test_bug_0054_repro_blank_transcodedownto_blocked(self):
        # see marginal-savings-gate.C2b -- collapsed-TargetResolution repro
        Cfg = _AdmissionConfigStub()
        Mf = self._MakeMediaFile('480p')
        Settings = {
            'TargetResolution': '480p',
            'ProfileMaxTarget': '720p',
            'VideoBitrateKbps': 0,
            'Codec': 'libsvtav1',
            'Quality': 28,
        }
        ShouldBlock, Reason = self.Service.EvaluateQueueAdmission(Mf, Settings, Cfg)
        self.assertTrue(ShouldBlock, "upscale gate regression: 480p->720p with collapsed TargetResolution not blocked")
        self.assertTrue(Reason.startswith('Upscale'), f"not Upscale reason: {Reason}")


if __name__ == '__main__':
    unittest.main()
