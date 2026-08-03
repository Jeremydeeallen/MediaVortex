import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.MediaFiles.MediaFilesRepository import MediaFilesRepository


class TestNoStuckCompliance(unittest.TestCase):

    def test_zero_rows_stuck_on_populated_input(self):
        Repo = MediaFilesRepository()
        Rows = Repo.GetStaleComplianceRows()
        self.assertEqual(
            len(Rows), 0,
            f"{len(Rows)} MediaFiles rows have videocompliantreason='missing_input:*' "
            f"AND the referenced input IS NOT NULL. First few: "
            f"{[(R.get('id'), R.get('videocompliantreason'), R.get('filename')) for R in Rows[:5]]}"
        )


if __name__ == '__main__':
    unittest.main()
