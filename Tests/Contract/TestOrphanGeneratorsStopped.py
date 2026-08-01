# see orphan-generators-stop -- prevents regression of the two orphan-generation paths fixed 2026-08-01.
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TOP = Path(__file__).resolve().parents[2]

TRANSCODED_OUTPUT_PLACEMENT = REPO_ROOT / 'Features' / 'FileReplacement' / 'TranscodedOutputPlacement.py'
FILE_MANAGER_SERVICE = REPO_ROOT / 'Services' / 'FileManagerService.py'


class TestOrphanGeneratorsStopped(unittest.TestCase):

    def test_reparent_precedes_delete_in_transcoded_output_placement(self):
        Src = TRANSCODED_OUTPUT_PLACEMENT.read_text(encoding='utf-8')
        DeleteMatch = re.search(
            r'DELETE\s+FROM\s+MediaFiles\s+WHERE\s+StorageRootId\s*=\s*%s\s+AND\s+LOWER\(RelativePath\)\s*=\s*LOWER\(%s\)',
            Src, re.IGNORECASE,
        )
        self.assertIsNotNone(
            DeleteMatch,
            'Expected DELETE FROM MediaFiles collision-dedupe query in TranscodedOutputPlacement (invariant of orphan-generators-stop C1).'
        )
        WindowStart = max(0, DeleteMatch.start() - 4000)
        Window = Src[WindowStart:DeleteMatch.start()]
        ReparentAttempts = re.search(
            r'UPDATE\s+TranscodeAttempts\s+SET\s+MediaFileId\s*=\s*%s',
            Window, re.IGNORECASE,
        )
        ReparentFiles = re.search(
            r'UPDATE\s+TranscodeFiles\s+SET\s+MediaFileId\s*=\s*%s',
            Window, re.IGNORECASE,
        )
        self.assertIsNotNone(
            ReparentAttempts,
            'TranscodeAttempts reparent UPDATE must precede the MediaFiles DELETE (C1). See orphan-generators-stop directive.'
        )
        self.assertIsNotNone(
            ReparentFiles,
            'TranscodeFiles reparent UPDATE must precede the MediaFiles DELETE (C1). See orphan-generators-stop directive.'
        )

    def test_staging_basename_exclusions_present(self):
        Src = FILE_MANAGER_SERVICE.read_text(encoding='utf-8')
        Match = re.search(
            r"STAGING_BASENAME_EXCLUSIONS\s*=\s*\(([^)]+)\)",
            Src,
        )
        self.assertIsNotNone(
            Match,
            'FileManagerService must declare STAGING_BASENAME_EXCLUSIONS tuple (C3). See orphan-generators-stop directive.'
        )
        Body = Match.group(1).lower()
        for Expected in ('_downloads', '_audiotests', '_testing'):
            self.assertIn(
                Expected, Body,
                f'STAGING_BASENAME_EXCLUSIONS must include {Expected!r} (C3).'
            )


if __name__ == '__main__':
    unittest.main()
