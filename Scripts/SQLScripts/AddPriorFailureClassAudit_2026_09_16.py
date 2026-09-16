# directive: bug-0095-failure-classification
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


# directive: bug-0095-failure-classification
def Main():
    Db = DatabaseService()
    Db.ExecuteNonQuery(
        "ALTER TABLE FailureBudgetResets ADD COLUMN IF NOT EXISTS PriorFailureClass TEXT NULL"
    )
    Rows = Db.ExecuteQuery(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'failurebudgetresets' AND column_name = 'priorfailureclass'"
    )
    if not Rows:
        raise RuntimeError("PriorFailureClass column not present after ALTER")
    print("Applied. FailureBudgetResets.PriorFailureClass TEXT NULL column present.")


if __name__ == '__main__':
    Main()
