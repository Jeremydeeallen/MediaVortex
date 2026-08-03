import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.Ingest.IngestWebhookController import _ExtractPath, IngestWebhookBlueprint


class TestExtractPath(unittest.TestCase):

    def test_test_event_returns_empty(self):
        self.assertEqual(_ExtractPath({'eventType': 'Test'}), '')

    def test_sonarr_ondownload_picks_episode_file_path(self):
        Payload = {
            'eventType': 'Download',
            'series': {'path': 'T:\\Full Circle (2023)'},
            'episodeFile': {'path': 'T:\\Full Circle (2023)\\Season 1\\Ep1.mkv'},
        }
        self.assertEqual(_ExtractPath(Payload), 'T:\\Full Circle (2023)\\Season 1\\Ep1.mkv')

    def test_radarr_ondownload_picks_movie_file_path(self):
        Payload = {
            'eventType': 'Download',
            'movie': {'folderPath': 'M:\\The Matrix (1999)'},
            'movieFile': {'path': 'M:\\The Matrix (1999)\\The Matrix (1999).mkv'},
        }
        self.assertEqual(_ExtractPath(Payload), 'M:\\The Matrix (1999)\\The Matrix (1999).mkv')

    def test_falls_back_to_folder_path(self):
        self.assertEqual(_ExtractPath({'eventType': 'Download', 'series': {'path': 'T:\\Show'}}), 'T:\\Show')
        self.assertEqual(_ExtractPath({'eventType': 'Download', 'movie': {'folderPath': 'M:\\Movie'}}), 'M:\\Movie')

    def test_returns_empty_on_unrecognized(self):
        self.assertEqual(_ExtractPath({'eventType': 'Unknown', 'foo': 'bar'}), '')


class TestWebhookEndpoint(unittest.TestCase):

    def _AppClient(self):
        from flask import Flask
        App = Flask(__name__)
        App.register_blueprint(IngestWebhookBlueprint)
        return App.test_client()

    def test_test_event_returns_200_without_scan(self):
        Client = self._AppClient()
        Response = Client.post('/api/Ingest/Webhook', json={'eventType': 'Test'})
        self.assertEqual(Response.status_code, 200)
        Data = Response.get_json()
        self.assertTrue(Data['Success'])

    def test_unrecognized_payload_returns_400(self):
        Client = self._AppClient()
        Response = Client.post('/api/Ingest/Webhook', json={'eventType': 'Unknown', 'random': 'data'})
        self.assertEqual(Response.status_code, 400)


if __name__ == '__main__':
    unittest.main()
