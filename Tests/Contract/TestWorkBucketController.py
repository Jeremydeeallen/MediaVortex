import os
import unittest
from WebService.Main import WebServiceApp


# directive: work-transcode-unified | # see work-bucket.C1
class TestWorkBucketController(unittest.TestCase):
    """Live HTTP route contract for /Work/<bucket> + /api/Work/<bucket> routes."""

    @classmethod
    # directive: work-transcode-unified | # see work-bucket.C1
    def setUpClass(cls):
        os.environ.setdefault('MEDIAVORTEX_DB_HOST', '10.0.0.15')
        cls.App = WebServiceApp().App
        cls.App.config['TESTING'] = True
        cls.Client = cls.App.test_client()

    # directive: work-transcode-unified | # see work-bucket.C1
    def test_render_transcode_page(self):
        # see work-bucket.C1
        Response = self.Client.get('/Work/Transcode')
        self.assertEqual(Response.status_code, 200)
        self.assertIn(b'Transcode', Response.data)

    # directive: work-transcode-unified | # see work-bucket.C1
    def test_render_remux_page(self):
        # see work-bucket.C1
        Response = self.Client.get('/Work/Remux')
        self.assertEqual(Response.status_code, 200)
        self.assertIn(b'Remux', Response.data)

    # directive: work-transcode-unified | # see work-bucket.C1
    def test_render_audio_page(self):
        # see work-bucket.C1
        Response = self.Client.get('/Work/Audio')
        self.assertEqual(Response.status_code, 200)
        self.assertIn(b'Audio', Response.data)

    # directive: work-transcode-unified | # see work-bucket.C1
    def test_unknown_bucket_404(self):
        # see work-bucket.C1
        Response = self.Client.get('/Work/Bogus')
        self.assertEqual(Response.status_code, 404)

    # directive: work-transcode-unified | # see work-bucket.C1
    def test_api_series_list_envelope(self):
        # see work-bucket.C1
        Response = self.Client.get('/api/Work/Transcode?page=1&pageSize=5')
        self.assertEqual(Response.status_code, 200)
        Payload = Response.get_json()
        self.assertTrue(Payload['Success'])
        self.assertIn('Series', Payload['Data'])
        self.assertIn('Total', Payload['Data'])
        self.assertIn('Page', Payload['Data'])
        self.assertIn('PageSize', Payload['Data'])

    # directive: work-transcode-unified | # see work-bucket.C1
    def test_api_unknown_bucket_404(self):
        # see work-bucket.C1
        Response = self.Client.get('/api/Work/Bogus')
        self.assertEqual(Response.status_code, 404)


if __name__ == '__main__':
    unittest.main()
