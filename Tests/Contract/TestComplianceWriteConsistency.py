import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Core.Database.DatabaseService import DatabaseService
from Features.Compliance.Models.ComplianceDecision import ComplianceDecision, ContradictoryDecisionError
from Features.Compliance.Services.ComplianceBucketResolver import ComplianceBucketResolver
from Features.Compliance.Repositories.ComplianceWriteRepository import ComplianceWriteRepository


CONTRADICTION_COUNT_SQL = (
    "SELECT COUNT(*) AS n FROM MediaFiles WHERE NOT ("
    "(IsCompliant = TRUE AND WorkBucket IS NULL "
    "AND (OperationsNeededCsv IS NULL OR OperationsNeededCsv = '')) "
    "OR (IsCompliant = FALSE AND WorkBucket IS NOT NULL "
    "AND OperationsNeededCsv IS NOT NULL AND OperationsNeededCsv != '') "
    "OR (IsCompliant IS NULL AND ComplianceGateBlocked IS NOT NULL) "
    "OR (IsCompliant IS NULL AND WorkBucket IS NULL "
    "AND (OperationsNeededCsv IS NULL OR OperationsNeededCsv = '') "
    "AND ComplianceGateBlocked IS NULL)"
    ")"
)

NARROW_BUG_COUNT_SQL = (
    "SELECT COUNT(*) AS n FROM MediaFiles "
    "WHERE IsCompliant = TRUE AND WorkBucket IS NOT NULL"
)


# directive: compliance-writeback-invariant | # see compliance.C7
class TestLayer1Constructor(unittest.TestCase):
    """Layer 1: ComplianceDecision.__post_init__ raises on contradictory tuples (compliance.C7)."""

    # directive: compliance-writeback-invariant | # see compliance.C7
    def test_compliant_clean_state_accepted(self):
        D = ComplianceDecision(IsCompliant=True, OperationsNeeded=frozenset(), WorkBucket=None, GateBlocked=None)
        self.assertTrue(D.IsCompliant)

    # directive: compliance-writeback-invariant | # see compliance.C7
    def test_non_compliant_bucketed_state_accepted(self):
        D = ComplianceDecision(IsCompliant=False, OperationsNeeded=frozenset({'Transcode'}), WorkBucket='Transcode', GateBlocked=None)
        self.assertFalse(D.IsCompliant)

    # directive: compliance-writeback-invariant | # see compliance.C7
    def test_gate_blocked_state_accepted(self):
        D = ComplianceDecision(IsCompliant=None, OperationsNeeded=frozenset(), WorkBucket=None, GateBlocked='EffectiveProfile')
        self.assertEqual(D.GateBlocked, 'EffectiveProfile')

    # directive: compliance-writeback-invariant | # see compliance.C7
    def test_compliant_with_non_null_bucket_refused(self):
        with self.assertRaises(ContradictoryDecisionError):
            ComplianceDecision(IsCompliant=True, OperationsNeeded=frozenset({'Transcode'}), WorkBucket='Transcode', GateBlocked=None)

    # directive: compliance-writeback-invariant | # see compliance.C7
    def test_compliant_with_ops_refused(self):
        with self.assertRaises(ContradictoryDecisionError):
            ComplianceDecision(IsCompliant=True, OperationsNeeded=frozenset({'Remux'}), WorkBucket=None, GateBlocked=None)

    # directive: compliance-writeback-invariant | # see compliance.C7
    def test_non_compliant_without_bucket_refused(self):
        with self.assertRaises(ContradictoryDecisionError):
            ComplianceDecision(IsCompliant=False, OperationsNeeded=frozenset({'Transcode'}), WorkBucket=None, GateBlocked=None)

    # directive: compliance-writeback-invariant | # see compliance.C7
    def test_unknown_operation_refused(self):
        with self.assertRaises(ContradictoryDecisionError):
            ComplianceDecision(IsCompliant=False, OperationsNeeded=frozenset({'PolishAlgorithm'}), WorkBucket='Transcode', GateBlocked=None)

    # directive: compliance-writeback-invariant | # see compliance.C7
    def test_gate_blocked_with_bucket_refused(self):
        with self.assertRaises(ContradictoryDecisionError):
            ComplianceDecision(IsCompliant=None, OperationsNeeded=frozenset(), WorkBucket='Transcode', GateBlocked='EffectiveProfile')


# directive: compliance-writeback-invariant | # see compliance.C8
class TestLayer1BucketResolverSoleProducer(unittest.TestCase):
    """Layer 1 cont.: BucketResolver returns co-mutated (IsCompliant, WorkBucket) tuples that always pass C7 (compliance.C8)."""

    # directive: compliance-writeback-invariant | # see compliance.C8
    def setUp(self):
        self.R = ComplianceBucketResolver()

    # directive: compliance-writeback-invariant | # see compliance.C8
    def test_every_legal_input_produces_C7_passing_tuple(self):
        LegalInputs = [
            frozenset(),
            frozenset({'Transcode'}),
            frozenset({'Remux'}),
            frozenset({'AudioFix'}),
            frozenset({'SubtitleFix'}),
            frozenset({'AudioFix', 'SubtitleFix'}),
            frozenset({'Transcode', 'Remux'}),
            frozenset({'Transcode', 'Remux', 'AudioFix', 'SubtitleFix'}),
        ]
        for Ops in LegalInputs:
            IsCompliant, Bucket = self.R.Resolve(Ops)
            with self.subTest(ops=Ops):
                D = ComplianceDecision(IsCompliant=IsCompliant, OperationsNeeded=Ops, WorkBucket=Bucket, GateBlocked=None)
                self.assertEqual(D.IsCompliant, IsCompliant)
                self.assertEqual(D.WorkBucket, Bucket)


# directive: compliance-writeback-invariant | # see compliance.C8
class TestLayer2WriteRepositoryValidation(unittest.TestCase):
    """Layer 2: BulkWriteRecomputeResults refuses contradictory tuples and reports refused count (compliance.C8 / ST9)."""

    # directive: compliance-writeback-invariant | # see compliance.C8
    def test_valid_compliant_tuple_passes_layer2(self):
        Tuple = (1, 'AV1', 100, True, None, None, None, None)
        self.assertTrue(ComplianceWriteRepository._IsCompliantTuple(Tuple))

    # directive: compliance-writeback-invariant | # see compliance.C8
    def test_valid_non_compliant_tuple_passes_layer2(self):
        Tuple = (1, 'AV1', 100, False, None, 'Transcode', 'Transcode', None)
        self.assertTrue(ComplianceWriteRepository._IsCompliantTuple(Tuple))

    # directive: compliance-writeback-invariant | # see compliance.C8
    def test_valid_gate_blocked_tuple_passes_layer2(self):
        Tuple = (1, 'AV1', 100, None, 'LoudnessMeasurements', None, None, 'LoudnessMeasurements')
        self.assertTrue(ComplianceWriteRepository._IsCompliantTuple(Tuple))

    # directive: compliance-writeback-invariant | # see compliance.C8
    def test_compliant_with_bucket_refused_at_layer2(self):
        Tuple = (1, 'AV1', 100, True, None, 'Transcode', 'Transcode', None)
        self.assertFalse(ComplianceWriteRepository._IsCompliantTuple(Tuple))

    # directive: compliance-writeback-invariant | # see compliance.C8
    def test_compliant_with_ops_refused_at_layer2(self):
        Tuple = (1, 'AV1', 100, True, None, None, 'Transcode', None)
        self.assertFalse(ComplianceWriteRepository._IsCompliantTuple(Tuple))

    # directive: compliance-writeback-invariant | # see compliance.C8
    def test_non_compliant_without_bucket_refused_at_layer2(self):
        Tuple = (1, 'AV1', 100, False, None, None, 'Transcode', None)
        self.assertFalse(ComplianceWriteRepository._IsCompliantTuple(Tuple))

    # directive: compliance-writeback-invariant | # see compliance.C8
    def test_bulk_write_returns_refused_counts(self):
        Repo = ComplianceWriteRepository()
        Repo.ExecuteNonQuery = MagicMock(return_value=None)
        Updates = [
            (1, 'AV1', 100, True, None, None, None, None),
            (2, 'AV1', 100, True, None, 'Transcode', 'Transcode', None),
            (3, 'AV1', 100, False, None, 'Remux', 'Remux', None),
        ]
        Written, Refused = Repo.BulkWriteRecomputeResults(Updates)
        self.assertEqual(Refused, 1)
        self.assertEqual(Written, 2)


# directive: compliance-writeback-invariant | # see compliance.C9
class TestLayer3SqlCheckConstraint(unittest.TestCase):
    """Layer 3: SQL CHECK constraint chk_compliance_consistency exists on MediaFiles (compliance.C9)."""

    # directive: compliance-writeback-invariant | # see compliance.C9
    def test_check_constraint_exists(self):
        Rows = DatabaseService().ExecuteQuery(
            "SELECT conname FROM pg_constraint WHERE conname = 'chk_compliance_consistency'"
        )
        self.assertGreaterEqual(len(Rows), 1, "CHECK chk_compliance_consistency missing -- run Scripts/SQLScripts/AddComplianceConsistencyCheck.py")


# directive: compliance-writeback-invariant | # see compliance.C7
class TestDbWideInvariant(unittest.TestCase):
    """AC1: live DB count of contradictory MediaFiles rows is 0. see compliance.C9"""

    # directive: compliance-writeback-invariant | # see compliance.C7
    def test_narrow_bug_count_is_zero(self):
        N = int(DatabaseService().ExecuteQuery(NARROW_BUG_COUNT_SQL)[0]['n'])
        self.assertEqual(N, 0, "MediaFiles still contain " + str(N) + " IsCompliant=TRUE rows with non-null WorkBucket -- compliance writeback invariant not remediated")


if __name__ == '__main__':
    unittest.main()
