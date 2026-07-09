# see transcode-flow-canonical.C25
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import re


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLAIM_SOURCE = REPO_ROOT / 'Features' / 'TranscodeQueue' / 'TranscodeQueueRepository.py'


# directive: transcode-flow-canonical
def _NormalizedSource():
    Text = CLAIM_SOURCE.read_text(encoding='utf-8')
    return re.sub(r'\s+', ' ', Text)


# directive: transcode-flow-canonical
def test_claim_query_contains_encoder_agnostic_av1_guard():
    Normalized = _NormalizedSource()
    Pattern = r"AND\s*\(\s*COALESCE\(p\.codec,\s*''\)\s*<>\s*'av1'[^)]*OR\s+w\.nvenccapable\s*=\s*TRUE\s+OR\s+w\.qsvcapable\s*=\s*TRUE\s*\)"
    assert re.search(Pattern, Normalized), "ClaimNextPendingJob must include the family-agnostic av1 guard from C25 (COALESCE av1 -> either encoder capability)"


# directive: transcode-flow-canonical
def test_claim_query_joins_profiles_on_assigned_profile():
    Normalized = _NormalizedSource()
    Assertion = "LEFT JOIN Profiles p ON p.profilename = mf.AssignedProfile"
    NormalizedAssertion = re.sub(r'\s+', ' ', Assertion)
    assert NormalizedAssertion in Normalized, "Claim query must LEFT JOIN Profiles to read codec for the av1 guard"


# directive: transcode-flow-canonical
def test_claim_query_does_not_re_gate_on_specific_family_literal():
    Normalized = _NormalizedSource()
    assert "p.family = 'NVENC AV1 CANARY'" not in Normalized, "Claim query must not re-introduce NVENC-Family predicate"
    assert "p.family = 'QSV AV1 CANARY'" not in Normalized, "Claim query must not re-introduce QSV-Family predicate"


# directive: transcode-flow-canonical
def test_guard_allows_non_av1_codecs_unconditionally():
    Normalized = _NormalizedSource()
    assert "COALESCE(p.codec,'') <> 'av1'" in Normalized, "Guard must let non-av1 profiles pass without capability check"


# directive: transcode-flow-canonical
def test_guard_admits_either_encoder_family_for_av1():
    Normalized = _NormalizedSource()
    assert "w.nvenccapable = TRUE OR w.qsvcapable = TRUE" in Normalized, "For av1 profiles, either NVENC or QSV capability must satisfy the guard"


# directive: transcode-flow-canonical
def test_worker_capability_predicate_whitelist_covers_both_encoders():
    from Core.Database.WorkerCapabilityPredicate import _ALLOWED_CAPABILITIES
    assert 'nvenccapable' in _ALLOWED_CAPABILITIES, "nvenccapable must be whitelisted for BuildClaimPredicate"
    assert 'qsvcapable' in _ALLOWED_CAPABILITIES, "qsvcapable must be whitelisted for BuildClaimPredicate"


if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__, '-v']))
