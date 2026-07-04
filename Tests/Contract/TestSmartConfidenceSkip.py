import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.append(str(Path(__file__).resolve().parents[2]))

import pytest

from Features.QualityTesting.Disposition.PostTranscodeDispositionDecider import PostTranscodeDispositionDecider
from Features.QualityTesting.VmafConfidenceStatsRepository import BucketKey, BucketStats


def _Gate(**overrides):
    Base = {
        'VmafAutoReplaceMinThreshold': 80.0,
        'VmafAutoReplaceMaxThreshold': 97.0,
        'QualityTestEnabled': True,
        'MinConfidenceSampleCount': 10,
        'MinConfidencePassRate': 0.95,
        'SigmaMargin': 2.0,
    }
    Base.update(overrides)
    return Base


def _Attempt(**overrides):
    Base = {'Success': True, 'OldSize': 1000, 'NewSize': 800,
          'QualityTestRequired': True, 'VmafScore': None,
          'BucketKey': BucketKey(ProfileId=44, SourceCodec='h264', SourceResolutionTier='1080p',
                                BitratePerPixelBucket=3, ContentClass='live_action')}
    Base.update(overrides)
    return Base


def _RepoStub(Stats):
    Repo = MagicMock()
    Repo.LookupBucket.return_value = Stats
    return Repo


# directive: transcode-flow-canonical | # see transcode.ST7
class TestSmartConfidenceSkip:

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_no_repo_falls_through_to_pending(self):
        Result = PostTranscodeDispositionDecider().Decide(_Attempt(), _Gate())
        assert Result.Action == 'Pending'
        assert Result.Reason == 'AwaitingVmaf'

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_no_bucket_key_falls_through_to_pending(self):
        Repo = _RepoStub(BucketStats(SampleCount=0, VmafMean=None, VmafStdDev=None, PassRate=None))
        Result = PostTranscodeDispositionDecider(SmartConfidenceRepo=Repo).Decide(_Attempt(BucketKey=None), _Gate())
        assert Result.Action == 'Pending'

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_below_min_samplecount_falls_through(self):
        Repo = _RepoStub(BucketStats(SampleCount=9, VmafMean=94.0, VmafStdDev=1.0, PassRate=1.0))
        Result = PostTranscodeDispositionDecider(SmartConfidenceRepo=Repo).Decide(_Attempt(), _Gate(MinConfidenceSampleCount=10))
        assert Result.Action == 'Pending'

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_below_min_passrate_falls_through(self):
        Repo = _RepoStub(BucketStats(SampleCount=15, VmafMean=94.0, VmafStdDev=1.0, PassRate=0.94))
        Result = PostTranscodeDispositionDecider(SmartConfidenceRepo=Repo).Decide(_Attempt(), _Gate(MinConfidencePassRate=0.95))
        assert Result.Action == 'Pending'

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_lower_bound_below_threshold_falls_through(self):
        # Mean 82, StdDev 2, Sigma 2 -> lower = 78 < 80 min -> no skip
        Repo = _RepoStub(BucketStats(SampleCount=15, VmafMean=82.0, VmafStdDev=2.0, PassRate=0.96))
        Result = PostTranscodeDispositionDecider(SmartConfidenceRepo=Repo).Decide(_Attempt(), _Gate())
        assert Result.Action == 'Pending'

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_confident_bucket_skips_to_replace(self):
        # Mean 95, StdDev 1, Sigma 2 -> lower = 93 >= 80 -> skip
        Repo = _RepoStub(BucketStats(SampleCount=20, VmafMean=95.0, VmafStdDev=1.0, PassRate=1.0))
        Result = PostTranscodeDispositionDecider(SmartConfidenceRepo=Repo).Decide(_Attempt(), _Gate())
        assert Result.Action == 'Replace'
        assert Result.Reason == 'QualityTestConfident'

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_smart_skip_bypassed_when_vmaf_score_already_present(self):
        Repo = _RepoStub(BucketStats(SampleCount=20, VmafMean=95.0, VmafStdDev=1.0, PassRate=1.0))
        Result = PostTranscodeDispositionDecider(SmartConfidenceRepo=Repo).Decide(_Attempt(VmafScore=85.0), _Gate())
        assert Result.Reason == 'VmafPassed'

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_global_off_beats_smart_skip(self):
        Repo = _RepoStub(BucketStats(SampleCount=20, VmafMean=95.0, VmafStdDev=1.0, PassRate=1.0))
        Result = PostTranscodeDispositionDecider(SmartConfidenceRepo=Repo).Decide(_Attempt(), _Gate(QualityTestEnabled=False))
        assert Result.Reason == 'QualityTestingGloballyDisabled'


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))
