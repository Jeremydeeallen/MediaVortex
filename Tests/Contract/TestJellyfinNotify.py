"""Unit tests for Services.JellyfinNotifyService.

Owns jellyfin-push-notify.feature.md criteria 3, 4, 5, 6, 8, 9. Mocks
requests.post and the SystemSettings read so no DB / network is touched.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.append(str(Path(__file__).parent.parent.parent))

from Services import JellyfinNotifyService


class _FakeResponse:
    def __init__(self, StatusCode=204, Body=''):
        self.status_code = StatusCode
        self.text = Body


def _MockSettings(Host='jellyfin.test', Port='8096', ApiKey='test-token'):
    """Patch JellyfinNotifyService._ReadSetting to return the given values."""
    def Fake(SettingKey: str) -> str:
        if SettingKey == JellyfinNotifyService.SETTING_HOST:
            return Host
        if SettingKey == JellyfinNotifyService.SETTING_API_PORT:
            return Port
        if SettingKey == JellyfinNotifyService.SETTING_API_KEY:
            return ApiKey
        return ''
    return patch.object(JellyfinNotifyService, '_ReadSetting', side_effect=Fake)


def _PatchTranslate(*ReturnValues):
    return patch.object(
        JellyfinNotifyService,
        'TranslateForJellyfin',
        side_effect=list(ReturnValues),
    )


class TestNotifyJellyfin(unittest.TestCase):

    def test_batches_n_updates_into_one_post(self):
        """Criterion 3: N updates -> one POST with N entries."""
        Updates = [
            {'Path': 'T:\\Show\\s01e01.mkv', 'UpdateType': 'Modified'},
            {'Path': 'M:\\Movie.mkv', 'UpdateType': 'Deleted'},
        ]
        with _MockSettings(), \
             _PatchTranslate('/mnt/BrainTv/Show/s01e01.mkv', '/mnt/SynologyMovies/Movie.mkv'), \
             patch('requests.post', return_value=_FakeResponse(204)) as MockPost:
            JellyfinNotifyService.NotifyJellyfin(Updates)
        self.assertEqual(MockPost.call_count, 1)
        Call = MockPost.call_args
        Body = Call.kwargs['json']
        self.assertEqual(len(Body['Updates']), 2)
        self.assertEqual(Body['Updates'][0]['Path'], '/mnt/BrainTv/Show/s01e01.mkv')
        self.assertEqual(Body['Updates'][1]['UpdateType'], 'Deleted')
        self.assertEqual(Call.kwargs['headers']['X-Emby-Token'], 'test-token')
        self.assertEqual(Call.kwargs['timeout'], 5)
        self.assertEqual(Call.args[0], 'http://jellyfin.test:8096/Library/Media/Updated')

    def test_500_response_does_not_raise(self):
        """Criterion 4: 5xx logs WARNING + returns normally."""
        with _MockSettings(), \
             _PatchTranslate('/mnt/x/a.mkv'), \
             patch('requests.post', return_value=_FakeResponse(500, 'boom')):
            JellyfinNotifyService.NotifyJellyfin(
                [{'Path': 'T:\\a.mkv', 'UpdateType': 'Modified'}]
            )  # must not raise

    def test_connection_error_does_not_raise(self):
        """Criterion 4: network failure logs WARNING + returns normally."""
        with _MockSettings(), \
             _PatchTranslate('/mnt/x/a.mkv'), \
             patch('requests.post', side_effect=ConnectionError('refused')):
            JellyfinNotifyService.NotifyJellyfin(
                [{'Path': 'T:\\a.mkv', 'UpdateType': 'Modified'}]
            )  # must not raise

    def test_timeout_uses_five_seconds(self):
        """Criterion 5: timeout kwarg is exactly 5."""
        with _MockSettings(), \
             _PatchTranslate('/mnt/x/a.mkv'), \
             patch('requests.post', return_value=_FakeResponse(204)) as MockPost:
            JellyfinNotifyService.NotifyJellyfin(
                [{'Path': 'T:\\a.mkv', 'UpdateType': 'Modified'}]
            )
        self.assertEqual(MockPost.call_args.kwargs['timeout'], 5)

    def test_missing_host_or_apikey_does_not_post(self):
        """Criterion 6: missing JellyfinHost/JellyfinApiKey => WARNING, no POST."""
        with _MockSettings(Host='', ApiKey=''), \
             _PatchTranslate('/mnt/x/a.mkv'), \
             patch('requests.post') as MockPost:
            JellyfinNotifyService.NotifyJellyfin(
                [{'Path': 'T:\\a.mkv', 'UpdateType': 'Modified'}]
            )
        MockPost.assert_not_called()

    def test_default_port_when_blank(self):
        """JellyfinApiPort defaults to 8096 when blank."""
        with _MockSettings(Port=''), \
             _PatchTranslate('/mnt/x/a.mkv'), \
             patch('requests.post', return_value=_FakeResponse(204)) as MockPost:
            JellyfinNotifyService.NotifyJellyfin(
                [{'Path': 'T:\\a.mkv', 'UpdateType': 'Modified'}]
            )
        self.assertIn(':8096/', MockPost.call_args.args[0])

    def test_empty_updates_is_noop(self):
        with patch('requests.post') as MockPost:
            JellyfinNotifyService.NotifyJellyfin([])
        MockPost.assert_not_called()

    def test_untranslatable_entries_are_skipped(self):
        """Entries whose path has no __jellyfin__ resolution are dropped;
        remaining entries still POST."""
        Updates = [
            {'Path': 'X:\\not-indexed.mkv', 'UpdateType': 'Modified'},
            {'Path': 'T:\\Show\\s01e01.mkv', 'UpdateType': 'Modified'},
        ]
        with _MockSettings(), \
             _PatchTranslate(None, '/mnt/BrainTv/Show/s01e01.mkv'), \
             patch('requests.post', return_value=_FakeResponse(204)) as MockPost:
            JellyfinNotifyService.NotifyJellyfin(Updates)
        self.assertEqual(MockPost.call_count, 1)
        Body = MockPost.call_args.kwargs['json']
        self.assertEqual(len(Body['Updates']), 1)
        self.assertEqual(Body['Updates'][0]['Path'], '/mnt/BrainTv/Show/s01e01.mkv')

    def test_all_untranslatable_entries_is_noop(self):
        """If every entry fails translation, no POST is made."""
        with _MockSettings(), \
             _PatchTranslate(None, None), \
             patch('requests.post') as MockPost:
            JellyfinNotifyService.NotifyJellyfin([
                {'Path': 'X:\\a.mkv', 'UpdateType': 'Modified'},
                {'Path': 'Y:\\b.mkv', 'UpdateType': 'Deleted'},
            ])
        MockPost.assert_not_called()

    def test_invalid_update_type_is_dropped(self):
        """Update entries with non-canonical UpdateType are dropped with a WARNING."""
        with _MockSettings(), \
             _PatchTranslate('/mnt/x/a.mkv'), \
             patch('requests.post', return_value=_FakeResponse(204)) as MockPost:
            JellyfinNotifyService.NotifyJellyfin([
                {'Path': 'T:\\bad.mkv', 'UpdateType': 'Updated'},  # invalid
                {'Path': 'T:\\good.mkv', 'UpdateType': 'Modified'},
            ])
        Body = MockPost.call_args.kwargs['json']
        self.assertEqual(len(Body['Updates']), 1)
        self.assertEqual(Body['Updates'][0]['Path'], '/mnt/x/a.mkv')

    def test_log_prefix_is_consistent(self):
        """Criterion 9: every log line starts with 'JellyfinNotify:'."""
        with _MockSettings(), \
             _PatchTranslate('/mnt/x/a.mkv'), \
             patch('requests.post', return_value=_FakeResponse(204)), \
             patch.object(JellyfinNotifyService.LoggingService, 'LogInfo') as MockInfo:
            JellyfinNotifyService.NotifyJellyfin(
                [{'Path': 'T:\\a.mkv', 'UpdateType': 'Modified'}]
            )
        self.assertTrue(MockInfo.called)
        for Call in MockInfo.call_args_list:
            self.assertIn('JellyfinNotify:', Call.args[0])

    def test_settings_read_fresh_on_every_call(self):
        """No-cached-settings rule: each NotifyJellyfin call reads SystemSettings."""
        with _MockSettings() as MockRead, \
             _PatchTranslate('/mnt/x/a.mkv', '/mnt/x/b.mkv'), \
             patch('requests.post', return_value=_FakeResponse(204)):
            JellyfinNotifyService.NotifyJellyfin(
                [{'Path': 'T:\\a.mkv', 'UpdateType': 'Modified'}]
            )
            FirstCallCount = MockRead.call_count
            self.assertGreater(FirstCallCount, 0)
            JellyfinNotifyService.NotifyJellyfin(
                [{'Path': 'T:\\b.mkv', 'UpdateType': 'Modified'}]
            )
            self.assertGreater(MockRead.call_count, FirstCallCount)


class TestExtensionOf(unittest.TestCase):

    def test_windows_path_mkv(self):
        self.assertEqual(JellyfinNotifyService._ExtensionOf('T:\\Show\\s01e01.mkv'), '.mkv')

    def test_windows_path_mp4(self):
        self.assertEqual(JellyfinNotifyService._ExtensionOf('T:\\Show\\s01e01-mv.mp4'), '.mp4')

    def test_posix_path(self):
        self.assertEqual(JellyfinNotifyService._ExtensionOf('/mnt/tv/show/e01.MKV'), '.mkv')

    def test_no_extension(self):
        self.assertEqual(JellyfinNotifyService._ExtensionOf('T:\\Show\\file'), '')

    def test_dot_in_directory_only(self):
        # dot appears in directory but not in filename -> no extension
        self.assertEqual(JellyfinNotifyService._ExtensionOf('T:\\Show.2020\\file'), '')

    def test_empty(self):
        self.assertEqual(JellyfinNotifyService._ExtensionOf(''), '')


class TestNotifyReplaced(unittest.TestCase):

    def test_same_extension_sends_modified_only(self):
        # Re-transcode -mv.mp4 -> -mv.mp4 -- Modified-only avoids the same-ext orphan bug (30 Rock S02E10, 2026-05-27).
        with _MockSettings(), _PatchTranslate('/mnt/tv/OLD.mp4', '/mnt/tv/NEW.mp4'), \
                patch('requests.post', return_value=_FakeResponse(204)) as MockPost:
            JellyfinNotifyService.NotifyReplaced(
                'T:\\Show\\s01e01-mv.mp4', 'T:\\Show\\s01e01-mv.mp4'
            )
            Sent = MockPost.call_args.kwargs['json']['Updates']
            self.assertEqual(len(Sent), 1)
            self.assertEqual(Sent[0]['UpdateType'], 'Modified')

    def test_different_extension_sends_deleted_plus_created(self):
        # First-time transcode .mkv -> .mp4 -- Jellyfin's coalescing sweep doesn't strip stale old-ext entries (Heroes S02E08, 2026-08-02).
        with _MockSettings(), _PatchTranslate('/mnt/tv/OLD.mkv', '/mnt/tv/NEW.mp4'), \
                patch('requests.post', return_value=_FakeResponse(204)) as MockPost:
            JellyfinNotifyService.NotifyReplaced(
                'T:\\Show\\s01e01.mkv', 'T:\\Show\\s01e01-mv.mp4'
            )
            Sent = MockPost.call_args.kwargs['json']['Updates']
            self.assertEqual(len(Sent), 2)
            Kinds = {(E['UpdateType'], E['Path']) for E in Sent}
            self.assertIn(('Deleted', '/mnt/tv/OLD.mkv'), Kinds)
            self.assertIn(('Created', '/mnt/tv/NEW.mp4'), Kinds)

    def test_missing_new_path_is_noop(self):
        with _MockSettings(), patch('requests.post') as MockPost:
            JellyfinNotifyService.NotifyReplaced('T:\\Show\\a.mkv', '')
            MockPost.assert_not_called()

    def test_missing_old_path_treated_as_same_extension(self):
        # No old path known -> can't diff extensions -> fall through to Modified-only (best-effort).
        with _MockSettings(), _PatchTranslate('/mnt/tv/NEW.mp4'), \
                patch('requests.post', return_value=_FakeResponse(204)) as MockPost:
            JellyfinNotifyService.NotifyReplaced('', 'T:\\Show\\a.mp4')
            Sent = MockPost.call_args.kwargs['json']['Updates']
            self.assertEqual(len(Sent), 1)
            self.assertEqual(Sent[0]['UpdateType'], 'Modified')


if __name__ == '__main__':
    unittest.main()
