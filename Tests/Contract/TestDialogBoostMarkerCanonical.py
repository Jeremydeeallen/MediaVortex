# directive: dialog-boost-marker-unify | # see dialog-boost-marker-unify.C7
import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PROD_DIRS = ['Features', 'Workers', 'WorkerService', 'Core']


def _iter_py_files(root):
    for base in PROD_DIRS:
        base_path = REPO_ROOT / base
        if not base_path.is_dir():
            continue
        for dirpath, _dirs, files in os.walk(base_path):
            for name in files:
                if name.endswith('.py'):
                    yield Path(dirpath) / name


class TestDialogBoostMarkerCanonical(unittest.TestCase):

    def test_no_dialog_boost_emitted_literal_in_production_paths(self):
        hits = []
        for path in _iter_py_files(REPO_ROOT):
            text = path.read_text(encoding='utf-8', errors='replace')
            if 'dialog_boost_emitted' in text:
                hits.append(str(path.relative_to(REPO_ROOT)))
        self.assertEqual(hits, [], f"dialog_boost_emitted literal must not appear in production code; found in: {hits}")

    def test_no_jsonb_containment_on_audio_tracks_emitted_json_in_production(self):
        pattern = re.compile(r"AudioTracksEmittedJson::jsonb\s*@>")
        hits = []
        for path in _iter_py_files(REPO_ROOT):
            text = path.read_text(encoding='utf-8', errors='replace')
            if pattern.search(text):
                hits.append(str(path.relative_to(REPO_ROOT)))
        self.assertEqual(hits, [], f"JSONB containment on AudioTracksEmittedJson must not appear in production code; found in: {hits}")

    def test_single_writer_of_dialog_boost_emitted_column(self):
        pattern = re.compile(r"UPDATE\s+TranscodeAttempts\s+SET\s+DialogBoostEmitted", re.IGNORECASE)
        writers = []
        for path in _iter_py_files(REPO_ROOT):
            text = path.read_text(encoding='utf-8', errors='replace')
            if pattern.search(text):
                writers.append(str(path.relative_to(REPO_ROOT)))
        self.assertEqual(len(writers), 1, f"Expected exactly one production writer of TranscodeAttempts.DialogBoostEmitted; found: {writers}")

    def test_column_exists_and_round_trip(self):
        from Core.Database.DatabaseService import DatabaseService
        Db = DatabaseService()
        Cols = Db.ExecuteQuery(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'transcodeattempts' AND column_name = 'dialogboostemitted'"
        )
        self.assertTrue(Cols, "TranscodeAttempts.DialogBoostEmitted column must exist")
        Rows = Db.ExecuteQuery(
            "SELECT DialogBoostEmitted FROM TranscodeAttempts "
            "WHERE DialogBoostEmitted = TRUE LIMIT 1"
        )
        self.assertTrue(Rows, "At least one attempt must have DialogBoostEmitted=TRUE post-backfill")


if __name__ == '__main__':
    unittest.main()
