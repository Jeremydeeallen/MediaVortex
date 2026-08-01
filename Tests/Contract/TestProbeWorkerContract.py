# see probe-worker-decoupled.C1 + C3 -- ProbeWorker is standalone capability + scan cycle no longer probes.
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestProbeWorkerContract(unittest.TestCase):

    def test_probe_worker_class_exists(self):
        Src = (REPO_ROOT / 'WorkerService' / 'ProbeWorker.py').read_text(encoding='utf-8')
        self.assertIn('class ProbeWorker', Src)
        self.assertIn("BuildClaimPredicate(self.WorkerName, 'ProbeEnabled')", Src)
        self.assertIn('FOR UPDATE OF mf SKIP LOCKED', Src)

    def test_probe_enabled_in_allowed_capabilities(self):
        Src = (REPO_ROOT / 'Core' / 'Database' / 'WorkerCapabilityPredicate.py').read_text(encoding='utf-8')
        self.assertIn('"ProbeEnabled"', Src)

    def test_scan_cycle_no_longer_probes(self):
        Src = (REPO_ROOT / 'Features' / 'FileScanning' / 'FileScanningBusinessService.py').read_text(encoding='utf-8')
        self.assertNotIn('ProbeFilesNeedingMetadata', Src,
            'FileScanningBusinessService must not call ProbeFilesNeedingMetadata (C3). ProbeWorker owns probing.')

    def test_worker_service_wires_probe_capability(self):
        Src = (REPO_ROOT / 'WorkerService' / 'Main.py').read_text(encoding='utf-8')
        self.assertIn('_StartProbeCapability', Src)
        self.assertIn('_StopProbeCapability', Src)
        self.assertIn('self.ProbeEnabled', Src)


if __name__ == '__main__':
    unittest.main()
