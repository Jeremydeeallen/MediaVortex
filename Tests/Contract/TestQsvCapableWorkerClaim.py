# Asserts BuildQsvPredicate emits correct SQL fragment + params for Intel QSV claim gating.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Core.Database.WorkerCapabilityPredicate import (
    BuildQsvPredicate, BuildClaimPredicate, _ALLOWED_CAPABILITIES,
)


def test_qsvcapable_is_in_allowed_capabilities():
    """BuildClaimPredicate must accept 'qsvcapable' (parallel to 'nvenccapable')."""
    assert 'qsvcapable' in _ALLOWED_CAPABILITIES


def test_buildclaimpredicate_qsvcapable_returns_expected_fragment():
    """BuildClaimPredicate('worker', 'qsvcapable') emits the standard EXISTS Online + capability fragment."""
    Fragment, Params = BuildClaimPredicate('wakko-worker-1', 'qsvcapable')
    assert 'w.qsvcapable = TRUE' in Fragment
    assert "w.Status = 'Online'" in Fragment
    assert Params == ('wakko-worker-1',)


def test_buildqsvpredicate_gates_only_qsv_profiles():
    """BuildQsvPredicate: non-QSV profiles bypass the gate; QSV profiles require qsvcapable=TRUE workers."""
    Fragment, Params = BuildQsvPredicate('wakko-worker-2')
    assert 'COALESCE(p.useintelhardware, 0) = 0' in Fragment
    assert 'w4.qsvcapable = TRUE' in Fragment
    assert 'w4.WorkerName = %s' in Fragment
    assert Params == ('wakko-worker-2',)


def test_buildqsvpredicate_uses_unique_alias():
    """BuildQsvPredicate uses w4 (not w/w2/w3) so its EXISTS can coexist with other claim-gate fragments in one query."""
    Fragment, _ = BuildQsvPredicate('wakko-worker-2')
    assert 'w4.' in Fragment
    assert 'w2.' not in Fragment
    assert 'w3.' not in Fragment
