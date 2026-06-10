import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from Features.QualityTesting.Disposition.Disposition import Disposition


class TestDisposition(unittest.TestCase):
    """Verify Disposition value object: instantiation, immutability, equality."""

    def test_instantiation_with_required_fields_only(self):
        """Disposition accepts Action and Reason with optional fields defaulting to None."""
        D = Disposition(Action='Replace', Reason='VMAF 92 within band')
        self.assertEqual(D.Action, 'Replace')
        self.assertEqual(D.Reason, 'VMAF 92 within band')
        self.assertIsNone(D.NextRegime)
        self.assertIsNone(D.NextKnob)

    def test_instantiation_with_all_fields(self):
        """Disposition accepts all four fields populated."""
        D = Disposition(Action='Requeue', Reason='Below min threshold', NextRegime='cq', NextKnob={'CRF': 22})
        self.assertEqual(D.Action, 'Requeue')
        self.assertEqual(D.NextRegime, 'cq')
        self.assertEqual(D.NextKnob, {'CRF': 22})

    def test_immutability_raises_on_mutation(self):
        """Disposition is frozen; mutation raises FrozenInstanceError."""
        D = Disposition(Action='Discard', Reason='Retry budget exhausted')
        with self.assertRaises(FrozenInstanceError):
            D.Action = 'Replace'
        with self.assertRaises(FrozenInstanceError):
            D.Reason = 'other'

    def test_equality_between_equal_valued_instances(self):
        """Two Disposition instances with equal fields compare equal."""
        A = Disposition(Action='NoReplace', Reason='VMAF 100 ceiling')
        B = Disposition(Action='NoReplace', Reason='VMAF 100 ceiling')
        self.assertEqual(A, B)

    def test_inequality_when_fields_differ(self):
        """Disposition instances with differing fields are not equal."""
        A = Disposition(Action='Replace', Reason='ok')
        B = Disposition(Action='Discard', Reason='ok')
        self.assertNotEqual(A, B)


if __name__ == '__main__':
    unittest.main()
