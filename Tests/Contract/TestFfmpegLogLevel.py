# see .claude/directives/closed/*ffmpeg-stderr-deadlock* -- covers C2 + C3 + C4 + C5

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Core.Database.DatabaseService import DatabaseService
from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository


VALID_LEVELS = {'quiet', 'fatal', 'error', 'warning', 'info', 'verbose', 'debug'}


class TestFfmpegLogLevelKnob(unittest.TestCase):
    """C2: SystemSettings.FfmpegLogLevel row exists with default 'error'."""

    def test_row_exists_with_default(self):
        Repo = SystemSettingsRepository()
        Val = Repo.GetSystemSetting('FfmpegLogLevel')
        self.assertIsNotNone(Val, "FfmpegLogLevel setting must exist. Run Scripts/SQLScripts/AddFfmpegLogLevelSetting_2026_08_05.py")
        self.assertIn(Val, VALID_LEVELS, f"FfmpegLogLevel={Val!r} outside enum whitelist")


class TestFfmpegLogLevelDbFresh(unittest.TestCase):
    """C3: Command emitter reads FfmpegLogLevel fresh per invocation (db-is-authority)."""

    def test_repository_reads_fresh_per_call(self):
        Repo = SystemSettingsRepository()
        Original = Repo.GetSystemSetting('FfmpegLogLevel')
        self.assertIsNotNone(Original)
        try:
            Repo.AddOrUpdateSystemSetting('FfmpegLogLevel', 'warning', 'test cycle', 'string')
            self.assertEqual(Repo.GetSystemSetting('FfmpegLogLevel'), 'warning')
            Repo.AddOrUpdateSystemSetting('FfmpegLogLevel', 'debug', 'test cycle', 'string')
            self.assertEqual(Repo.GetSystemSetting('FfmpegLogLevel'), 'debug')
        finally:
            Repo.AddOrUpdateSystemSetting('FfmpegLogLevel', Original, 'restored by TestFfmpegLogLevel', 'string')


class TestMonitorProgressNoSleep(unittest.TestCase):
    """C4: VideoTranscodingService.MonitorProgress contains no time.sleep in its body."""

    def test_monitor_progress_body_has_no_sleep(self):
        SourcePath = Path(__file__).resolve().parent.parent.parent / 'Features' / 'TranscodeJob' / 'VideoTranscodingService.py'
        Source = SourcePath.read_text(encoding='utf-8')
        Match = re.search(r'def MonitorProgress\(.*?(?=\n    def |\nclass )', Source, re.DOTALL)
        self.assertIsNotNone(Match, "MonitorProgress method not found")
        Body = Match.group(0)
        self.assertNotIn('time.sleep', Body,
            "MonitorProgress must not sleep between readline() calls -- the sleep-throttle caused stderr pipe deadlock (AoT 2026-07-30 / 2026-08-05)")


class TestFfmpegLogLevelWhitelist(unittest.TestCase):
    """C5: Whitelist rejection is enforced in the controller module."""

    def test_controller_defines_whitelist(self):
        SourcePath = Path(__file__).resolve().parent.parent.parent / 'Features' / 'SystemSettings' / 'SystemSettingsController.py'
        Source = SourcePath.read_text(encoding='utf-8')
        self.assertIn('_FFMPEG_LOG_LEVELS', Source,
            "SystemSettingsController must define _FFMPEG_LOG_LEVELS whitelist")
        for Level in VALID_LEVELS:
            self.assertIn(f"'{Level}'", Source,
                f"Whitelist must contain '{Level}'")
        self.assertIn("FfmpegLogLevel' and Value not in _FFMPEG_LOG_LEVELS", Source,
            "Controller must guard POST /api/SystemSettings/FfmpegLogLevel against non-whitelist values")


if __name__ == '__main__':
    unittest.main()
