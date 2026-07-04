import re
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

TARGET = REPO_ROOT / 'Services' / 'QualityTestQueueService.py'


# directive: transcode-flow-canonical | # see transcode.ST8
class TestQualityTestQueueFreezeMarkerRefusal(unittest.TestCase):

    def _Source(self):
        return TARGET.read_text(encoding='utf-8')

    def test_refuses_success_false_freeze_marker(self):
        Src = self._Source()
        Pattern = re.compile(r"Attempt\.Success\s+is\s+False", re.MULTILINE)
        self.assertIsNotNone(
            Pattern.search(Src),
            "AddToQualityTestQueue must explicitly refuse Attempt.Success is False (freeze marker). "
            "Truthy `if not Attempt.Success` conflates freeze with in-flight.",
        )

    def test_refuses_success_none_in_flight(self):
        Src = self._Source()
        Pattern = re.compile(r"Attempt\.Success\s+is\s+None", re.MULTILINE)
        self.assertIsNotNone(
            Pattern.search(Src),
            "AddToQualityTestQueue must explicitly refuse Attempt.Success is None (in-flight).",
        )

    def test_freeze_marker_log_names_freeze(self):
        Src = self._Source()
        self.assertIn(
            'freeze marker', Src,
            "Refusal log for Success=False must name 'freeze marker' so operator can distinguish it from in-flight.",
        )

    def test_refusal_precedes_queue_insert(self):
        Src = self._Source()
        FreezeIdx = Src.find('freeze marker')
        InsertIdx = Src.find('CreateQualityTestQueueEntry')
        self.assertGreater(
            FreezeIdx, -1,
            "Freeze-marker refusal message not found.",
        )
        self.assertGreater(
            InsertIdx, -1,
            "CreateQualityTestQueueEntry call site not found.",
        )
        self.assertLess(
            FreezeIdx, InsertIdx,
            "Freeze-marker refusal must occur before the QualityTestingQueue INSERT call.",
        )


if __name__ == '__main__':
    unittest.main()
