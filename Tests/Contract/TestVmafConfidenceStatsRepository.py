import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.append(str(Path(__file__).resolve().parents[2]))

import pytest

from Features.QualityTesting.VmafConfidenceStatsRepository import (
    VmafConfidenceStatsRepository, BucketKey, BucketStats, ROLLING_WINDOW_N,
)


def _Key():
    return BucketKey(ProfileId=44, SourceCodec='h264', SourceResolutionTier='1080p',
                    BitratePerPixelBucket=3, ContentClass='live_action')


# directive: transcode-flow-canonical | # see transcode.ST7
class TestVmafConfidenceStatsRepository:

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_lookup_missing_bucket_returns_zero_count(self):
        Db = MagicMock()
        Db.ExecuteQuery.return_value = []
        Result = VmafConfidenceStatsRepository(Db=Db).LookupBucket(_Key())
        assert Result.SampleCount == 0
        assert Result.VmafMean is None

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_lookup_existing_bucket_returns_stats(self):
        Db = MagicMock()
        Db.ExecuteQuery.return_value = [{
            'samplecount': 15, 'vmafmean': 92.5, 'vmafstddev': 2.1, 'passrate': 0.98,
        }]
        Result = VmafConfidenceStatsRepository(Db=Db).LookupBucket(_Key())
        assert Result.SampleCount == 15
        assert Result.VmafMean == 92.5
        assert Result.VmafStdDev == 2.1
        assert Result.PassRate == 0.98

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_record_result_first_sample_upserts_count_1(self):
        Db = MagicMock()
        Db.ExecuteQuery.return_value = []
        VmafConfidenceStatsRepository(Db=Db).RecordResult(_Key(), VmafScore=90.0, Passed=True)
        Args = Db.ExecuteNonQuery.call_args.args
        assert 'INSERT INTO VmafConfidenceStats' in Args[0]
        assert Args[1][5] == 1
        assert Args[1][6] == 90.00
        assert Args[1][7] == 0.00
        assert Args[1][8] == 1.0

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_record_result_second_sample_computes_mean(self):
        Db = MagicMock()
        Db.ExecuteQuery.return_value = [{'samplesjson': '[{"vmaf": 90.0, "passed": true}]'}]
        VmafConfidenceStatsRepository(Db=Db).RecordResult(_Key(), VmafScore=92.0, Passed=True)
        Args = Db.ExecuteNonQuery.call_args.args
        assert Args[1][5] == 2
        assert Args[1][6] == 91.00
        assert Args[1][8] == 1.0

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_pass_rate_reflects_fail_mix(self):
        Db = MagicMock()
        SamplesJson = '[{"vmaf": 90.0, "passed": true}, {"vmaf": 88.0, "passed": true}, {"vmaf": 70.0, "passed": false}]'
        Db.ExecuteQuery.return_value = [{'samplesjson': SamplesJson}]
        VmafConfidenceStatsRepository(Db=Db).RecordResult(_Key(), VmafScore=91.0, Passed=True)
        Args = Db.ExecuteNonQuery.call_args.args
        assert Args[1][5] == 4
        assert Args[1][8] == 0.75

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_rolling_window_trims_oldest_at_capacity(self):
        Db = MagicMock()
        Samples = [{'vmaf': 50.0, 'passed': False}] + [{'vmaf': 95.0, 'passed': True}] * ROLLING_WINDOW_N
        import json
        Db.ExecuteQuery.return_value = [{'samplesjson': json.dumps(Samples)}]
        VmafConfidenceStatsRepository(Db=Db).RecordResult(_Key(), VmafScore=96.0, Passed=True)
        Args = Db.ExecuteNonQuery.call_args.args
        assert Args[1][5] == ROLLING_WINDOW_N
        assert Args[1][6] > 94.0


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))
