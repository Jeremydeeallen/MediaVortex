import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.append(str(Path(__file__).resolve().parents[2]))

import pytest

from Features.TranscodeJob.Adjustments.NextTierAdjustmentCalculator import NextTierAdjuster, NextTierProfile


def _MockDb(CurrentRows=None, NextRows=None):
    Db = MagicMock()
    Calls = {'n': 0}
    def FakeExecuteQuery(Sql, Params=None):
        Calls['n'] += 1
        if Calls['n'] == 1:
            return CurrentRows or []
        return NextRows or []
    Db.ExecuteQuery.side_effect = FakeExecuteQuery
    return Db


# directive: transcode-flow-canonical | # see transcode.ST7
class TestNextTierAdjuster:

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_none_input_returns_none(self):
        assert NextTierAdjuster(Db=MagicMock()).Get(None) is None

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_unknown_profile_returns_none(self):
        Db = _MockDb(CurrentRows=[])
        assert NextTierAdjuster(Db=Db).Get('DoesNotExist') is None

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_missing_tier_returns_none(self):
        Db = _MockDb(CurrentRows=[{
            'family': 'NVENC AV1 CANARY',
            'qualitytier': None,
            'contentclass': 'live_action',
            'targetresolutioncategory': '720p',
        }])
        assert NextTierAdjuster(Db=Db).Get('Weird Legacy Profile') is None

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_ceiling_returns_none(self):
        Db = _MockDb(
            CurrentRows=[{
                'family': 'NVENC AV1 CANARY', 'qualitytier': 4,
                'contentclass': 'live_action', 'targetresolutioncategory': '720p',
            }],
            NextRows=[],
        )
        assert NextTierAdjuster(Db=Db).Get('Tier 4 Profile') is None

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_escalation_returns_next_tier(self):
        Db = _MockDb(
            CurrentRows=[{
                'family': 'NVENC AV1 CANARY', 'qualitytier': 2,
                'contentclass': 'live_action', 'targetresolutioncategory': '720p',
            }],
            NextRows=[{
                'id': 40, 'profilename': 'NVENC AV1 P7 CANARY VBR -720p HQ',
                'family': 'NVENC AV1 CANARY', 'qualitytier': 4,
                'contentclass': 'live_action', 'targetresolutioncategory': '720p',
            }],
        )
        Result = NextTierAdjuster(Db=Db).Get('NVENC AV1 P7 CANARY VBR -720p')
        assert isinstance(Result, NextTierProfile)
        assert Result.ProfileId == 40
        assert Result.QualityTier == 4
        assert Result.Family == 'NVENC AV1 CANARY'


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))
