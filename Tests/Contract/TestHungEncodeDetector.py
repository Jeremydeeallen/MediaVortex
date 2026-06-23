import unittest

from Features.StuckJobDetection.HungEncodeDetector import IsHung


# directive: worker-runtime-state | # see admin-workers.C9
class TestHungEncodeDetector(unittest.TestCase):

    # directive: worker-runtime-state | # see admin-workers.C9
    def test_idle_worker_never_hung(self):
        self.assertFalse(IsHung('Idle', 99999, 99999, 600))
        self.assertFalse(IsHung('Paused', 99999, 99999, 600))
        self.assertFalse(IsHung(None, 99999, 99999, 600))

    # directive: worker-runtime-state | # see admin-workers.C9
    def test_encoding_within_threshold_not_hung(self):
        self.assertFalse(IsHung('Encoding', 30, 30, 600))
        self.assertFalse(IsHung('Encoding', 700, 30, 600))

    # directive: worker-runtime-state | # see admin-workers.C9
    def test_encoding_progress_stale_and_state_stale_is_hung(self):
        self.assertTrue(IsHung('Encoding', 900, 900, 600))

    # directive: worker-runtime-state | # see admin-workers.C9
    def test_encoding_state_stale_no_progress_row_is_hung(self):
        self.assertTrue(IsHung('Encoding', 900, None, 600))

    # directive: worker-runtime-state | # see admin-workers.C9
    def test_threshold_change_reflected_immediately(self):
        self.assertFalse(IsHung('Encoding', 150, 150, 600))
        self.assertTrue(IsHung('Encoding', 150, 150, 120))


if __name__ == '__main__':
    unittest.main()
