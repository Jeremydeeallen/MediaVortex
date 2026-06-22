import json
import unittest
import urllib.request
import urllib.error

from Core.Database.DatabaseService import DatabaseService


_BASE = 'http://127.0.0.1:5000'


# directive: compliance-symmetry
def _Get(Path):
    Req = urllib.request.Request(_BASE + Path, method='GET')
    try:
        with urllib.request.urlopen(Req, timeout=5) as Resp:
            return Resp.status, json.loads(Resp.read())
    except urllib.error.HTTPError as Ex:
        return Ex.code, json.loads(Ex.read())


# directive: compliance-symmetry
class TestComplianceSummaryEndpoint(unittest.TestCase):

    # directive: compliance-symmetry
    @classmethod
    def setUpClass(cls):
        cls.Db = DatabaseService()
        Rows = cls.Db.ExecuteQuery("SELECT Id FROM MediaFiles WHERE Id = 388 LIMIT 1")
        cls.SampleId = Rows[0]['id'] if Rows else None

    # directive: compliance-symmetry
    def test_returns_shape_with_all_required_keys(self):
        if self.SampleId is None:
            self.skipTest('Sample MediaFile 388 not available')
            return
        Status, Body = _Get(f'/api/MediaFile/{self.SampleId}/ComplianceSummary')
        self.assertEqual(Status, 200, f'Got {Status}: {Body}')
        self.assertTrue(Body.get('success'))
        for K in ('media_file_id', 'effective_profile', 'audio_policy', 'verdicts', 'work_bucket', 'planned_operations'):
            self.assertIn(K, Body, f'Missing key: {K}')
        Verdicts = Body['verdicts']
        for D in ('video', 'audio', 'container'):
            self.assertIn(D, Verdicts)
            self.assertIn('compliant', Verdicts[D])
            self.assertIn('reason', Verdicts[D])
        EP = Body['effective_profile']
        for K in ('name', 'stream_codec_name', 'target_resolution_category',
                  'target_video_kbps', 'allow_upscale', 'audio_codec', 'target_audio_kbps', 'container'):
            self.assertIn(K, EP, f'EffectiveProfile missing key: {K}')

    # directive: compliance-symmetry
    def test_unknown_media_file_returns_404(self):
        Status, Body = _Get('/api/MediaFile/999999999/ComplianceSummary')
        self.assertEqual(Status, 404)
        self.assertFalse(Body.get('success'))


if __name__ == '__main__':
    unittest.main()
