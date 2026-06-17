import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.SelfHealing.Invariants.PreVerticalTranscodedFile import PreVerticalTranscodedFile
from Features.AudioNormalization.AudioNormalizationConfigValidator import ValidatePreVerticalPolicy


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.O2
class TestPreVerticalPolicyValidator(unittest.TestCase):
    """O2: API rejects out-of-CHECK-set policy values before they reach the DB."""

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.O2
    def test_accepts_aggressive(self):
        self.assertEqual(ValidatePreVerticalPolicy('aggressive'), 'aggressive')

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.O2
    def test_accepts_lazy(self):
        self.assertEqual(ValidatePreVerticalPolicy('lazy'), 'lazy')

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.O2
    def test_accepts_none(self):
        self.assertEqual(ValidatePreVerticalPolicy('none'), 'none')

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.O2
    def test_case_insensitive(self):
        self.assertEqual(ValidatePreVerticalPolicy('AGGRESSIVE'), 'aggressive')

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.O2
    def test_blank_falls_back_to_lazy(self):
        self.assertEqual(ValidatePreVerticalPolicy(''), 'lazy')
        self.assertEqual(ValidatePreVerticalPolicy(None), 'lazy')

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.O2
    def test_rejects_unknown(self):
        with self.assertRaises(ValueError):
            ValidatePreVerticalPolicy('rocket')


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.O2
class TestPreVerticalInvariantHonorsLivePolicy(unittest.TestCase):
    """O2 live-DB: the invariant reads PreVerticalReNormalizePolicy fresh per Detect() per db-is-authority.md."""

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.O2
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('MEDIAVORTEX_DB_HOST', '10.0.0.15')

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.O2
    def test_under_lazy_invariant_returns_empty(self):
        from Core.Database.DatabaseService import DatabaseService
        Db = DatabaseService()
        Db.ExecuteNonQuery(
            "UPDATE AudioNormalizationConfig SET PreVerticalReNormalizePolicy='lazy' WHERE Scope='global'"
        )
        Detected = PreVerticalTranscodedFile().Detect()
        self.assertEqual(Detected, [])

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.O2
    def test_under_none_invariant_returns_empty(self):
        from Core.Database.DatabaseService import DatabaseService
        Db = DatabaseService()
        Db.ExecuteNonQuery(
            "UPDATE AudioNormalizationConfig SET PreVerticalReNormalizePolicy='none' WHERE Scope='global'"
        )
        try:
            self.assertEqual(PreVerticalTranscodedFile().Detect(), [])
        finally:
            Db.ExecuteNonQuery(
                "UPDATE AudioNormalizationConfig SET PreVerticalReNormalizePolicy='lazy' WHERE Scope='global'"
            )


if __name__ == '__main__':
    unittest.main()
