import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Core.Database.DatabaseService import DatabaseService


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PRODUCTION_TREES = ['Features', 'Workers', 'WorkerService', 'WebService', 'Repositories', 'Core']
INSERT_PATTERN = re.compile(r'INSERT\s+INTO\s+TranscodeAttempts\b', re.IGNORECASE)


# directive: bug-0096-scan-delete-restore-archival | # see scan.C15
class TestSchemaShape(unittest.TestCase):
    # schema aligns with transcodefiles archival pattern: nullable + FK ON DELETE SET NULL

    # directive: bug-0096-scan-delete-restore-archival | # see scan.C15
    def test_column_is_nullable(self):
        Rows = DatabaseService().ExecuteQuery(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name = 'transcodeattempts' AND column_name = 'mediafileid'"
        )
        self.assertEqual(str(Rows[0]['is_nullable']).upper(), 'YES')

    # directive: bug-0096-scan-delete-restore-archival | # see scan.C15
    def test_fk_cascade_rule_is_set_null(self):
        Rows = DatabaseService().ExecuteQuery(
            "SELECT rc.delete_rule FROM information_schema.referential_constraints rc "
            "WHERE rc.constraint_name = 'fk_transcodeattempts_mediafileid'"
        )
        self.assertEqual(str(Rows[0]['delete_rule']).upper(), 'SET NULL')


# directive: bug-0096-scan-delete-restore-archival | # see scan.C15
class TestInsertSitesPopulateMediaFileId(unittest.TestCase):
    # BUG-0061 accountability intent preserved at app layer

    # directive: bug-0096-scan-delete-restore-archival | # see scan.C15
    def test_every_production_insert_lists_mediafileid(self):
        Offenders = []
        for Tree in PRODUCTION_TREES:
            TreePath = REPO_ROOT / Tree
            if not TreePath.exists():
                continue
            for PyFile in TreePath.rglob('*.py'):
                Text = PyFile.read_text(encoding='utf-8', errors='replace')
                if not INSERT_PATTERN.search(Text):
                    continue
                if 'MediaFileId' not in Text:
                    Offenders.append(str(PyFile.relative_to(REPO_ROOT)))
        self.assertEqual(
            Offenders, [],
            f"Production INSERT sites missing MediaFileId: {Offenders}"
        )


if __name__ == '__main__':
    unittest.main()
