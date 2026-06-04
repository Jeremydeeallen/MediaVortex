"""Round-trip contract test for SaveMediaFile.

Owns criterion 2 of `.claude/directive.md` (clean happy-path transcode): every
MediaFiles column that FFprobe populates -- and AudioNormalizationMode, which
is derived from the just-run FFmpeg command -- must round-trip through
DatabaseManager.SaveMediaFile without silent column drops. Designed to catch
the BUG-0017 / BUG-0019 / BUG-0021 failure class at test time rather than
days later in a canary.

Inserts a synthetic MediaFiles row with a unique test FilePath, mutates every
directive-criterion-2 column to a non-default test value, calls SaveMediaFile,
re-loads, and asserts every mutated value persisted unchanged. Cleans up the
test row on tear-down.

Run: py -m pytest Tests/Contract/TestMediaFilePersistence.py -v
"""

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from Core.Models.MediaFileModel import MediaFileModel
from Repositories.DatabaseManager import DatabaseManager


# Directive .claude/directive.md criterion 2: columns that FFprobe populates
# (excluding AudioNormalizationMode, which has its own assertion because it's
# derived from the encode command rather than the probe).
PROBE_COLUMNS = [
    'Codec', 'AudioCodec', 'Resolution', 'ResolutionCategory',
    'VideoBitrateKbps', 'AudioBitrateKbps', 'DurationMinutes', 'FrameRate',
    'AudioChannels', 'AudioSampleRate', 'AudioSampleFormat',
    'AudioChannelLayout', 'ContainerFormat', 'OverallBitrate',
    'SubtitleFormats', 'AudioLanguages', 'HasExplicitEnglishAudio',
    'FileSize', 'ColorRange', 'FieldOrder', 'HasBFrames', 'RefFrames',
    'PixelFormat', 'Level', 'CodecProfile', 'TotalFrames', 'IsInterlaced',
    'LastModifiedDate', 'LastScannedDate',
]


class TestMediaFilePersistenceRoundTrip(unittest.TestCase):
    """Save -> reload -> compare for every directive-criterion-2 column."""

    # directive: path-schema-migration | # see path.S8
    TEST_STORAGE_ROOT_ID = 1
    TEST_REL_PREFIX = '__mvtest__/persistence-roundtrip'

    @classmethod
    def setUpClass(cls):
        cls.Db = DatabaseManager()

    # directive: path-schema-migration | # see path.S8
    def setUp(self):
        # Unique per-test RelativePath under the typed-pair identity.
        self.TestRelativePath = (
            f"{self.TEST_REL_PREFIX}/"
            f"{self._testMethodName}-"
            f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}.mp4"
        )

    # directive: path-schema-migration | # see path.S8
    def tearDown(self):
        try:
            self.Db.DatabaseService.ExecuteNonQuery(
                "DELETE FROM MediaFiles "
                "WHERE StorageRootId = %s AND RelativePath = %s",
                (self.TEST_STORAGE_ROOT_ID, self.TestRelativePath),
            )
        except Exception:
            pass

    # directive: path-schema-migration | # see path.S8
    def _BuildBaseRow(self):
        """Insert a baseline row -- every column at its column default."""
        Mf = MediaFileModel(
            StorageRootId=self.TEST_STORAGE_ROOT_ID,
            RelativePath=self.TestRelativePath,
            FileName='roundtrip.mp4',
            SizeMB=1.0,
            LastScannedDate=datetime(2026, 1, 1, 0, 0, 0),
        )
        Mf.Id = self.Db.SaveMediaFile(Mf)
        return Mf

    def _MutatedValues(self):
        """Test values for every probe-populated column + AudioNormalizationMode.

        Values chosen to be distinct from column defaults so a silent drop
        (column not in UPDATE) leaves the default in place and the assertion
        catches it.
        """
        return {
            'Codec': 'av1',
            'AudioCodec': 'eac3',
            'Resolution': '1920x1080',
            'ResolutionCategory': '1080p',
            'VideoBitrateKbps': 2500,
            'AudioBitrateKbps': 384,
            'DurationMinutes': 42.5,
            'FrameRate': 23.976,
            'AudioChannels': 6,
            'AudioSampleRate': 48000,
            'AudioSampleFormat': 'fltp',
            'AudioChannelLayout': '5.1',
            'ContainerFormat': 'mp4',
            'OverallBitrate': 3000,
            'SubtitleFormats': 'srt',
            'AudioLanguages': 'eng',
            'HasExplicitEnglishAudio': True,
            'FileSize': 1234567890,
            'ColorRange': 'tv',
            'FieldOrder': 'progressive',
            'HasBFrames': 3,
            'RefFrames': 4,
            'PixelFormat': 'yuv420p10le',
            'Level': 51,
            'CodecProfile': 'Main',
            'TotalFrames': 60000,
            'IsInterlaced': '0',
            'LastModifiedDate': datetime(2026, 5, 27, 12, 0, 0),
            'LastScannedDate': datetime(2026, 5, 27, 13, 0, 0),
            'AudioNormalizationMode': 'linear',
        }

    def test_every_directive_criterion_2_column_round_trips(self):
        """Mutate every probe column + AudioNormalizationMode; SaveMediaFile;
        re-load; assert each persisted unchanged."""
        Mf = self._BuildBaseRow()
        Values = self._MutatedValues()
        for Col, Val in Values.items():
            setattr(Mf, Col, Val)
        self.Db.SaveMediaFile(Mf)

        Reloaded = self.Db.GetMediaFileById(Mf.Id)
        self.assertIsNotNone(Reloaded, "Saved row could not be re-loaded by Id")

        Dropped = []
        for Col, Expected in Values.items():
            Actual = getattr(Reloaded, Col, None)
            if Actual != Expected:
                Dropped.append(f"{Col}: expected={Expected!r}, actual={Actual!r}")

        self.assertEqual(
            Dropped, [],
            "SaveMediaFile silently dropped one or more columns "
            "(directive criterion 2 violation):\n  " + "\n  ".join(Dropped),
        )

    # directive: path-schema-migration | # see path.S8
    def test_audio_normalization_mode_coalesce_protects_unset(self):
        """Criterion 2 + design-input criterion 4: partial-load caller must NOT blank existing non-None value."""
        Mf = self._BuildBaseRow()
        Mf.AudioNormalizationMode = 'dynamic'
        self.Db.SaveMediaFile(Mf)

        # Partial-load caller: typed pair matches existing row.
        Partial = MediaFileModel(
            Id=Mf.Id,
            StorageRootId=self.TEST_STORAGE_ROOT_ID,
            RelativePath=self.TestRelativePath,
            FileName='roundtrip.mp4',
            SizeMB=1.0,
        )
        self.Db.SaveMediaFile(Partial)

        Reloaded = self.Db.GetMediaFileById(Mf.Id)
        self.assertEqual(
            Reloaded.AudioNormalizationMode, 'dynamic',
            "COALESCE protection lost: a partial-load caller blanked "
            "AudioNormalizationMode from 'dynamic' to NULL.",
        )


if __name__ == '__main__':
    unittest.main()
