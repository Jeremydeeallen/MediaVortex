import json
import os
import unittest

from Core.Database.DatabaseService import DatabaseService
from Features.QualityTesting.PostTranscodeGateConfigRepository import PostTranscodeGateConfigRepository
from WebService.Main import WebServiceApp


# directive: transcode-flow-canonical | # see systemsettings.C10
class TestTranscodingSettingsRoundTrip(unittest.TestCase):
    """Live GET/PUT round-trip for /api/SystemSettings/Transcoding covering the six C15 sections."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('MEDIAVORTEX_DB_HOST', '10.0.0.15')
        cls.App = WebServiceApp().App
        cls.App.config['TESTING'] = True
        cls.Client = cls.App.test_client()
        cls.Db = DatabaseService()

    def _Get(self):
        Response = self.Client.get('/api/SystemSettings/Transcoding')
        self.assertEqual(Response.status_code, 200, Response.data)
        Body = json.loads(Response.data)
        self.assertTrue(Body.get('Success'), Body)
        return Body

    def _Put(self, Body):
        Response = self.Client.put('/api/SystemSettings/Transcoding',
                                    data=json.dumps(Body),
                                    content_type='application/json')
        self.assertEqual(Response.status_code, 200, Response.data)
        Result = json.loads(Response.data)
        self.assertTrue(Result.get('Success'), Result)
        return Result

    def test_get_returns_all_six_sections(self):
        Body = self._Get()
        self.assertIn('BitrateLadder', Body)
        self.assertIn('IcqLadder', Body)
        self.assertIn('Adequacy', Body)
        self.assertIn('Confidence', Body)
        self.assertIn('QualityTestEnabled', Body)
        self.assertIn('ConfidenceStats', Body)
        self.assertIn('Enabled', Body['Adequacy'])
        self.assertIn('MarginPercent', Body['Adequacy'])
        for Knob in ('MinConfidenceSampleCount', 'MinConfidencePassRate', 'SigmaMargin'):
            self.assertIn(Knob, Body['Confidence'])

    def test_bitrate_ladder_populated_for_canary_families(self):
        Body = self._Get()
        Families = {R['Family'] for R in Body['BitrateLadder']}
        self.assertIn('NVENC AV1 CANARY', Families)
        # QSV AV1 CANARY populated only if TargetKbps present per row; verify at least NVENC family shape.
        LiveAction = [R for R in Body['BitrateLadder']
                      if R['Family'] == 'NVENC AV1 CANARY' and R['ContentClass'] == 'live_action']
        Resolutions = {R['Resolution'] for R in LiveAction}
        for Res in ('480p', '720p', '1080p', '2160p'):
            self.assertIn(Res, Resolutions, f"Resolution {Res} missing for NVENC live_action")

    def test_icq_ladder_populated_for_qsv_family(self):
        Body = self._Get()
        Families = {R['Family'] for R in Body['IcqLadder']}
        self.assertIn('QSV AV1 CANARY', Families)
        QsvRows = [R for R in Body['IcqLadder']
                   if R['Family'] == 'QSV AV1 CANARY' and R['ContentClass'] == 'live_action']
        self.assertGreaterEqual(len(QsvRows), 1)
        for Tier in range(1, 6):
            self.assertIn(f'Tier{Tier}', QsvRows[0])

    def test_adequacy_toggle_round_trips(self):
        Original = self._Get()['Adequacy']
        try:
            self._Put({'Adequacy': {'Enabled': False, 'MarginPercent': 12.5}})
            After = self._Get()['Adequacy']
            self.assertFalse(After['Enabled'])
            self.assertAlmostEqual(float(After['MarginPercent']), 12.5, places=2)

            self._Put({'Adequacy': {'Enabled': True, 'MarginPercent': 0.0}})
            Restored = self._Get()['Adequacy']
            self.assertTrue(Restored['Enabled'])
            self.assertAlmostEqual(float(Restored['MarginPercent']), 0.0, places=2)
        finally:
            self._Put({'Adequacy': {
                'Enabled': bool(Original['Enabled']),
                'MarginPercent': float(Original['MarginPercent']),
            }})

    def test_confidence_knobs_round_trip(self):
        Original = self._Get()['Confidence']
        try:
            self._Put({'Confidence': {
                'MinConfidenceSampleCount': 15,
                'MinConfidencePassRate': 0.90,
                'SigmaMargin': 1.5,
            }})
            After = self._Get()['Confidence']
            self.assertEqual(int(After['MinConfidenceSampleCount']), 15)
            self.assertAlmostEqual(float(After['MinConfidencePassRate']), 0.90, places=3)
            self.assertAlmostEqual(float(After['SigmaMargin']), 1.5, places=2)
        finally:
            self._Put({'Confidence': {
                'MinConfidenceSampleCount': int(Original['MinConfidenceSampleCount']),
                'MinConfidencePassRate': float(Original['MinConfidencePassRate']),
                'SigmaMargin': float(Original['SigmaMargin']),
            }})

    def test_confidence_pass_rate_rejects_out_of_range(self):
        Response = self.Client.put(
            '/api/SystemSettings/Transcoding',
            data=json.dumps({'Confidence': {'MinConfidencePassRate': 1.5}}),
            content_type='application/json',
        )
        self.assertEqual(Response.status_code, 400)

    def test_global_off_round_trip(self):
        Original = self._Get()['QualityTestEnabled']
        try:
            self._Put({'QualityTestEnabled': not Original})
            Flipped = self._Get()['QualityTestEnabled']
            self.assertEqual(bool(Flipped), not bool(Original))
        finally:
            self._Put({'QualityTestEnabled': bool(Original)})

    def test_bitrate_cell_updates_profilethresholds(self):
        Body = self._Get()
        Sample = None
        for R in Body['BitrateLadder']:
            if R['Family'] == 'NVENC AV1 CANARY' and R['ContentClass'] == 'live_action' and R['Resolution'] == '480p':
                Sample = R
                break
        self.assertIsNotNone(Sample, 'NVENC live_action 480p row missing')
        Original = Sample.get('Tier2')
        self.assertIsNotNone(Original)
        Bumped = int(Original) + 7
        try:
            self._Put({'BitrateLadder': [{
                'Family': 'NVENC AV1 CANARY',
                'ContentClass': 'live_action',
                'Resolution': '480p',
                'Tier2': Bumped,
            }]})
            Rows = self.Db.ExecuteQuery(
                "SELECT MIN(pt.TargetKbps) AS v FROM Profiles p "
                "JOIN ProfileThresholds pt ON pt.ProfileId = p.Id "
                "WHERE p.Family = %s AND p.ContentClass = %s AND p.QualityTier = %s AND pt.Resolution = %s",
                ('NVENC AV1 CANARY', 'live_action', 2, '480p'),
            )
            self.assertEqual(int(Rows[0]['v']), Bumped)
        finally:
            self._Put({'BitrateLadder': [{
                'Family': 'NVENC AV1 CANARY',
                'ContentClass': 'live_action',
                'Resolution': '480p',
                'Tier2': int(Original),
            }]})

    def test_confidence_stats_review_returns_list(self):
        Body = self._Get()
        Stats = Body.get('ConfidenceStats')
        self.assertIsInstance(Stats, list)

    def test_confidence_stats_filter_narrows_results(self):
        Response = self.Client.get('/api/SystemSettings/Transcoding?filter=CANARY&limit=5')
        self.assertEqual(Response.status_code, 200)
        Body = json.loads(Response.data)
        self.assertTrue(Body.get('Success'))
        self.assertLessEqual(len(Body.get('ConfidenceStats') or []), 5)

    def test_persistence_reaches_db_authority(self):
        Repo = PostTranscodeGateConfigRepository()
        Original = Repo.Get()
        try:
            self._Put({'Confidence': {'SigmaMargin': 2.75}})
            Fresh = Repo.Get()
            self.assertAlmostEqual(float(Fresh.SigmaMargin), 2.75, places=2)
        finally:
            self._Put({'Confidence': {'SigmaMargin': float(Original.SigmaMargin)}})


if __name__ == '__main__':
    unittest.main()
