# directive: tv-video-rule-tier1 | # see video-encoding.C1
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from Core.Database.DatabaseService import DatabaseService
from Features.Profiles.TierLadderRepository import TierLadderRepository
from Features.VideoEncoding.VideoVertical import VideoVertical


# directive: tv-video-rule-tier1 | # see video-encoding.C1
def _Mf(**Overrides):
    Fields = dict(Id=1, StorageRootId=1, Codec='h264', VideoBitrateKbps=1000, ResolutionCategory='1080p',
                  AssignedProfile=None, ContainerFormat='mkv')
    Fields.update(Overrides)
    return SimpleNamespace(**Fields)


# directive: tv-video-rule-tier1 | # see video-encoding.C1
class TestTvVideoRuleTier1(unittest.TestCase):

    # directive: tv-video-rule-tier1 | # see video-encoding.C1
    def _Vert(self, Tier=1, TierKbps=1000):
        self.Tiers = Mock(**{'GetTierEncodeKbps.return_value': TierKbps})
        return VideoVertical(
            Thresholds=Mock(**{'GetMultiplier.return_value': 2.0}),
            Tiers=self.Tiers,
            LibraryTiers=Mock(**{'GetDefaultQualityTier.return_value': Tier}),
        )

    # directive: tv-video-rule-tier1 | # see video-encoding.C1
    def test_at_ceiling_is_compliant(self):
        Ok, Reason = self._Vert().Evaluate(_Mf(VideoBitrateKbps=2000))
        self.assertTrue(Ok)
        self.assertEqual(Reason, 'source_at_or_below_ceiling:2000<=2000(tier=1:1000*2.0)')

    # directive: tv-video-rule-tier1 | # see video-encoding.C1
    def test_above_ceiling_is_noncompliant(self):
        Ok, Reason = self._Vert().Evaluate(_Mf(VideoBitrateKbps=2001))
        self.assertFalse(Ok)
        self.assertEqual(Reason, 'source_above_ceiling:2001>2000(tier=1:1000*2.0)')

    # directive: tv-video-rule-tier1 | # see video-encoding.C1
    def test_av1_source_above_ceiling_is_noncompliant(self):
        Ok, _ = self._Vert().Evaluate(_Mf(Codec='av1', VideoBitrateKbps=6000, AssignedProfile='AV1 Tier 1 Efficient'))
        self.assertFalse(Ok)

    # directive: tv-video-rule-tier1 | # see video-encoding.C1
    def test_assigned_profile_never_consulted(self):
        Vert = self._Vert()
        WithProfile = Vert.Evaluate(_Mf(VideoBitrateKbps=3000, AssignedProfile='AV1 Tier 3 Better'))
        WithoutProfile = Vert.Evaluate(_Mf(VideoBitrateKbps=3000, AssignedProfile=None))
        self.assertEqual(WithProfile, WithoutProfile)
        self.Tiers.GetProfileCodec.assert_not_called()
        self.Tiers.GetProfileTarget.assert_not_called()

    # directive: tv-video-rule-tier1 | # see video-encoding.C1
    def test_missing_tier_bitrate_is_undecided(self):
        Ok, Reason = self._Vert(TierKbps=None).Evaluate(_Mf())
        self.assertIsNone(Ok)
        self.assertTrue(Reason.startswith('missing_input:TierEncodeKbps'))

    # directive: tv-video-rule-tier1 | # see video-encoding.C1
    def test_library_without_tier_uses_profile_path(self):
        Ok, Reason = self._Vert(Tier=None).Evaluate(_Mf(AssignedProfile=None))
        self.assertIsNone(Ok)
        self.assertEqual(Reason, 'missing_input:AssignedProfile')


# directive: tv-video-rule-tier1 | # see video-encoding.C1
class TestTvVideoRuleTier1Live(unittest.TestCase):

    # directive: tv-video-rule-tier1 | # see video-encoding.C1
    def test_tier_bitrate_follows_downscale_target(self):
        Db = DatabaseService()
        Rows = Db.ExecuteQuery(
            "SELECT src.Resolution AS SrcRes, tgt.TargetKbps AS Kbps FROM Profiles p "
            "JOIN ProfileThresholds src ON src.ProfileId = p.Id AND src.ContentClass = 'live_action' "
            "JOIN ProfileThresholds tgt ON tgt.ProfileId = p.Id AND tgt.ContentClass = 'live_action' "
            "  AND tgt.Resolution = src.TranscodeDownTo "
            "WHERE p.Family = 'ANY' AND p.QualityTier = 1 AND p.QualityLabel IS NOT NULL"
        )
        self.assertTrue(Rows, 'Tier 1 ladder rows missing')
        Repo = TierLadderRepository(Db)
        for R in Rows:
            self.assertEqual(Repo.GetTierEncodeKbps(1, 'live_action', R.get('SrcRes')), int(R.get('Kbps')))

    # directive: tv-video-rule-tier1 | # see video-encoding.C1
    def test_stored_verdicts_match_rule_for_tiered_libraries(self):
        Rows = DatabaseService().ExecuteQuery(
            "SELECT COUNT(*) AS N FROM MediaFiles mf "
            "JOIN StorageRoots sr ON sr.Id = mf.StorageRootId AND sr.DefaultQualityTier IS NOT NULL "
            "JOIN Profiles p ON p.Family = 'ANY' AND p.QualityTier = sr.DefaultQualityTier AND p.QualityLabel IS NOT NULL "
            "JOIN ProfileThresholds src ON src.ProfileId = p.Id AND src.ContentClass = 'live_action' AND src.Resolution = mf.ResolutionCategory "
            "JOIN ProfileThresholds tgt ON tgt.ProfileId = p.Id AND tgt.ContentClass = 'live_action' "
            "  AND tgt.Resolution = CASE WHEN src.TranscodeDownTo IN ('', 'No downscaling') THEN src.Resolution ELSE src.TranscodeDownTo END "
            "JOIN VideoComplianceThresholds m ON m.ResolutionCategory = mf.ResolutionCategory "
            "WHERE mf.VideoBitrateKbps > 0 AND mf.VideoCompliantReason IS DISTINCT FROM 'non_video_scope' "
            "  AND mf.VideoCompliant IS DISTINCT FROM (mf.VideoBitrateKbps <= ROUND(tgt.TargetKbps * m.Multiplier))"
        )
        self.assertEqual(int(Rows[0].get('N')), 0)

    # directive: tv-video-rule-tier1 | # see video-encoding.C1
    def test_no_tiered_library_row_judged_by_codec_or_profile(self):
        Rows = DatabaseService().ExecuteQuery(
            "SELECT COUNT(*) AS N FROM MediaFiles mf "
            "JOIN StorageRoots sr ON sr.Id = mf.StorageRootId AND sr.DefaultQualityTier IS NOT NULL "
            "WHERE starts_with(mf.VideoCompliantReason, 'source_codec_matches_target') "
            "   OR mf.VideoCompliantReason = 'missing_input:AssignedProfile' "
            "   OR position('(profile=' in mf.VideoCompliantReason) > 0"
        )
        self.assertEqual(int(Rows[0].get('N')), 0)


if __name__ == '__main__':
    unittest.main()
