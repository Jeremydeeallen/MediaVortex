import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.append(str(Path(__file__).resolve().parents[2]))

import pytest

from Features.TranscodeQueue.AdequacyGate import AdequacyGate, AdequacyDecision


def _MockDb(FamilyRows=None, TargetRows=None):
    Db = MagicMock()
    def FakeExecuteQuery(Sql, Params=None):
        if 'FROM Profiles WHERE ProfileName' in Sql:
            return FamilyRows or []
        if 'FROM Profiles p JOIN ProfileThresholds' in Sql:
            return TargetRows or []
        return []
    Db.ExecuteQuery.side_effect = FakeExecuteQuery
    Db.ExecuteNonQuery = MagicMock()
    return Db


def _MakeMediaFile(**kwargs):
    Defaults = dict(Id=1, AssignedProfile='NVENC AV1 P7 CANARY VBR -720p',
                  ResolutionCategory='720p', VideoBitrateKbps=1500,
                  ContentClass='live_action')
    Defaults.update(kwargs)
    return SimpleNamespace(**Defaults)


# directive: transcode-flow-canonical | # see transcode.ST2
class TestAdequacyGate:

    # directive: transcode-flow-canonical | # see transcode.ST2
    def test_source_at_tier1_minus_1_excluded(self):
        Db = _MockDb(FamilyRows=[{'family': 'NVENC AV1 CANARY'}], TargetRows=[{'targetkbps': 900}])
        Result = AdequacyGate(Db=Db).Evaluate(_MakeMediaFile(VideoBitrateKbps=899))
        assert Result.Excluded is True
        assert Result.Reason == 'ExcludedCompactSource'
        assert Result.SourceKbps == 899
        assert Result.Tier1TargetKbps == 900

    # directive: transcode-flow-canonical | # see transcode.ST2
    def test_source_equal_tier1_excluded(self):
        Db = _MockDb(FamilyRows=[{'family': 'NVENC AV1 CANARY'}], TargetRows=[{'targetkbps': 900}])
        Result = AdequacyGate(Db=Db).Evaluate(_MakeMediaFile(VideoBitrateKbps=900))
        assert Result.Excluded is True

    # directive: transcode-flow-canonical | # see transcode.ST2
    def test_source_at_tier1_plus_1_admitted(self):
        Db = _MockDb(FamilyRows=[{'family': 'NVENC AV1 CANARY'}], TargetRows=[{'targetkbps': 900}])
        Result = AdequacyGate(Db=Db).Evaluate(_MakeMediaFile(VideoBitrateKbps=901))
        assert Result.Excluded is False
        assert Result.Reason == 'Admitted'

    # directive: transcode-flow-canonical | # see transcode.ST2
    def test_no_family_admitted_no_data(self):
        Db = _MockDb(FamilyRows=[])
        Result = AdequacyGate(Db=Db).Evaluate(_MakeMediaFile(AssignedProfile='SomeOldProfile'))
        assert Result.Excluded is False
        assert Result.Reason == 'InsufficientData:NoFamily'

    # directive: transcode-flow-canonical | # see transcode.ST2
    def test_no_source_kbps_admitted_no_data(self):
        Db = _MockDb(FamilyRows=[{'family': 'NVENC AV1 CANARY'}], TargetRows=[{'targetkbps': 900}])
        Result = AdequacyGate(Db=Db).Evaluate(_MakeMediaFile(VideoBitrateKbps=None, OverallBitrate=None))
        assert Result.Excluded is False
        assert Result.Reason == 'InsufficientData:NoSourceKbps'

    # directive: transcode-flow-canonical | # see transcode.ST2
    def test_no_resolution_admitted_no_data(self):
        Db = _MockDb(FamilyRows=[{'family': 'NVENC AV1 CANARY'}], TargetRows=[])
        Result = AdequacyGate(Db=Db).Evaluate(_MakeMediaFile(ResolutionCategory=None))
        assert Result.Excluded is False
        assert Result.Reason == 'InsufficientData:NoResolutionCategory'

    # directive: transcode-flow-canonical | # see transcode.ST2
    def test_no_tier1_reference_admitted(self):
        Db = _MockDb(FamilyRows=[{'family': 'ANIME NVENC AV1'}], TargetRows=[])
        Result = AdequacyGate(Db=Db).Evaluate(_MakeMediaFile())
        assert Result.Excluded is False
        assert 'NoTier1Reference' in Result.Reason

    # directive: transcode-flow-canonical | # see transcode.ST2
    def test_overall_bitrate_fallback_when_video_kbps_missing(self):
        Db = _MockDb(FamilyRows=[{'family': 'NVENC AV1 CANARY'}], TargetRows=[{'targetkbps': 900}])
        Result = AdequacyGate(Db=Db).Evaluate(_MakeMediaFile(VideoBitrateKbps=None, OverallBitrate=850))
        assert Result.Excluded is True
        assert Result.SourceKbps == 850

    # directive: transcode-flow-canonical | # see transcode.ST2
    def test_writes_adequacydecision_column(self):
        Db = _MockDb(FamilyRows=[{'family': 'NVENC AV1 CANARY'}], TargetRows=[{'targetkbps': 900}])
        AdequacyGate(Db=Db).Evaluate(_MakeMediaFile(Id=42, VideoBitrateKbps=899))
        Called = Db.ExecuteNonQuery.call_args
        assert 'UPDATE MediaFiles SET AdequacyDecision' in Called.args[0]
        assert Called.args[1][1] == 42
        assert 'ExcludedCompactSource' in Called.args[1][0]


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))
