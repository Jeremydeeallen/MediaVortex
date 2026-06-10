import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from Features.TranscodeJob.Adjustments.KnobOverrides import KnobOverrides


class TestKnobOverrides(unittest.TestCase):
    """Verify KnobOverrides value object: instantiation, immutability, equality, defaults."""

    def test_defaults_are_all_none(self):
        """KnobOverrides with no args defaults every field to None."""
        K = KnobOverrides()
        self.assertIsNone(K.CRF)
        self.assertIsNone(K.BitrateKbps)
        self.assertIsNone(K.MaxrateKbps)

    def test_instantiation_with_all_fields(self):
        """KnobOverrides accepts all three int fields populated."""
        K = KnobOverrides(CRF=22, BitrateKbps=4500, MaxrateKbps=6000)
        self.assertEqual(K.CRF, 22)
        self.assertEqual(K.BitrateKbps, 4500)
        self.assertEqual(K.MaxrateKbps, 6000)

    def test_instantiation_with_partial_fields(self):
        """KnobOverrides accepts a subset of fields (CRF only)."""
        K = KnobOverrides(CRF=20)
        self.assertEqual(K.CRF, 20)
        self.assertIsNone(K.BitrateKbps)
        self.assertIsNone(K.MaxrateKbps)

    def test_immutability_raises_on_mutation(self):
        """KnobOverrides is frozen; mutation raises FrozenInstanceError."""
        K = KnobOverrides(CRF=20)
        with self.assertRaises(FrozenInstanceError):
            K.CRF = 18
        with self.assertRaises(FrozenInstanceError):
            K.BitrateKbps = 1000

    def test_equality_between_equal_valued_instances(self):
        """Two KnobOverrides instances with equal fields compare equal."""
        A = KnobOverrides(CRF=22, BitrateKbps=4500)
        B = KnobOverrides(CRF=22, BitrateKbps=4500)
        self.assertEqual(A, B)

    def test_inequality_when_fields_differ(self):
        """KnobOverrides instances with differing fields are not equal."""
        A = KnobOverrides(CRF=22)
        B = KnobOverrides(CRF=20)
        self.assertNotEqual(A, B)


if __name__ == '__main__':
    unittest.main()
