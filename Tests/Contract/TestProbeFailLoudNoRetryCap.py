# directive: probe-fail-loud-no-retry-cap | # see probe.C7
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.MediaProbe.MediaProbeBusinessService import MediaProbeBusinessService


class TestProbeFailLoudNoRetryCap(unittest.TestCase):
    """Cap deleted; NeedsReprobe=TRUE = one-shot operator command consumed each attempt."""

    def test_max_ffprobe_failures_constant_deleted(self):
        self.assertFalse(hasattr(MediaProbeBusinessService, 'MaxFFprobeFailures'),
                         'MaxFFprobeFailures constant should be deleted per probe-fail-loud-no-retry-cap')

    def test_fetch_predicate_has_no_failure_count_gate(self):
        Source = (Path(__file__).resolve().parents[2] / 'WorkerService' / 'ProbeWorker.py').read_text(encoding='utf-8')
        self.assertNotIn('FFprobeFailureCount <', Source,
                         'ProbeWorker fetch predicate must not gate on FFprobeFailureCount')

    def test_fetch_predicate_honors_needsreprobe_regardless_of_prior_failure(self):
        Source = (Path(__file__).resolve().parents[2] / 'WorkerService' / 'ProbeWorker.py').read_text(encoding='utf-8')
        self.assertIn('mf.NeedsReprobe = TRUE', Source)
        self.assertIn('mf.LastFFprobeError IS NULL', Source,
                      'Fetch should only skip failed rows when NeedsReprobe is not set')

    def test_record_probe_failure_clears_needsreprobe(self):
        Source = (Path(__file__).resolve().parents[2] / 'Features' / 'MediaProbe' / 'MediaProbeRepository.py').read_text(encoding='utf-8')
        Idx = Source.find('def RecordProbeFailure')
        self.assertGreater(Idx, -1)
        Body = Source[Idx:Idx + 800]
        self.assertIn('NeedsReprobe = FALSE', Body,
                      'RecordProbeFailure must clear NeedsReprobe so operator command is consumed each attempt')

    def test_reset_probe_failures_sets_needsreprobe_true(self):
        Source = (Path(__file__).resolve().parents[2] / 'Features' / 'MediaProbe' / 'MediaProbeRepository.py').read_text(encoding='utf-8')
        Idx = Source.find('def ResetProbeFailures')
        self.assertGreater(Idx, -1)
        Body = Source[Idx:Idx + 800]
        self.assertIn('NeedsReprobe = TRUE', Body,
                      'ResetProbeFailures should set NeedsReprobe=TRUE so the row is picked up on next tick')

    def test_failuresrepository_probe_query_uses_error_not_count(self):
        Source = (Path(__file__).resolve().parents[2] / 'Features' / 'Failures' / 'FailuresRepository.py').read_text(encoding='utf-8')
        self.assertNotIn('MaxFFprobeFailures', Source)
        self.assertIn('LastFFprobeError IS NOT NULL', Source)


if __name__ == '__main__':
    unittest.main()
