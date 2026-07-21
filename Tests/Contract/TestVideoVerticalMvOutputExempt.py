# directive: e2e-bug-fixes | # see e2e-bug-fixes.C31
import unittest

from Features.VideoEncoding.VideoVertical import VideoVertical


class _Mf:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class TestVideoVerticalMvOutputExempt(unittest.TestCase):

    def _NewVertical(self):
        # No DB access needed -- the TranscodedByMediaVortex short-circuit fires before _LoadRules.
        return VideoVertical()

    def test_mv_output_short_circuits_to_accepted(self):
        Mf = _Mf(TranscodedByMediaVortex=True, Codec='av1', VideoBitrateKbps=600, Resolution='1280x720', FrameRate=24.0, ResolutionCategory='720p')
        Ok, Reason = self._NewVertical().Evaluate(Mf)
        self.assertTrue(Ok)
        self.assertEqual(Reason, 'mediavortex_output_accepted')

    def test_mv_output_ignores_high_bitrate(self):
        Mf = _Mf(TranscodedByMediaVortex=True, Codec='av1', VideoBitrateKbps=99999, Resolution='1920x1080', FrameRate=30.0, ResolutionCategory='1080p')
        Ok, Reason = self._NewVertical().Evaluate(Mf)
        self.assertTrue(Ok)
        self.assertEqual(Reason, 'mediavortex_output_accepted')

    def test_mv_output_ignores_disallowed_codec(self):
        Mf = _Mf(TranscodedByMediaVortex=True, Codec='theora', VideoBitrateKbps=500, Resolution='1280x720', FrameRate=24.0, ResolutionCategory='720p')
        Ok, Reason = self._NewVertical().Evaluate(Mf)
        self.assertTrue(Ok)
        self.assertEqual(Reason, 'mediavortex_output_accepted')

    def test_non_mv_output_falls_through_to_normal_rules(self):
        # False (not True) means normal rules apply -- test that we get past the short-circuit into _LoadRules territory.
        Mf = _Mf(TranscodedByMediaVortex=False, Codec='av1', VideoBitrateKbps=600, Resolution='1280x720', FrameRate=24.0, ResolutionCategory='720p', AssignedProfile='AV1 Tier 1 Efficient')
        # Not asserting specific outcome -- only asserting the short-circuit did NOT fire (Reason not the exempt string).
        Ok, Reason = self._NewVertical().Evaluate(Mf)
        self.assertNotEqual(Reason, 'mediavortex_output_accepted')


if __name__ == '__main__':
    unittest.main()
