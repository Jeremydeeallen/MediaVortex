# directive: pre-encode-savings-gate | # see video-encoding.C1
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


# directive: pre-encode-savings-gate
def Main():
    Db = DatabaseService()
    # from: .claude/directive.md D2 "20% flat across all resolutions"
    Db.ExecuteNonQuery(
        "ALTER TABLE QueueAdmissionConfig "
        "ADD COLUMN IF NOT EXISTS PreEncodeSavingsThresholdPercent "
        "INTEGER NOT NULL DEFAULT 20 "
        "CHECK (PreEncodeSavingsThresholdPercent BETWEEN 1 AND 99)"
    )
    Rows = Db.ExecuteQuery(
        "SELECT Id, MinTranscodeSavingsMB, PreEncodeSavingsThresholdPercent "
        "FROM QueueAdmissionConfig"
    )
    print("Applied. QueueAdmissionConfig rows:")
    for R in Rows:
        Id = R.get('id')
        MinMB = R.get('mintranscodesavingsmb')
        ThresholdPct = R.get('preencodesavingsthresholdpercent')
        print(f"  Id={Id} MinTranscodeSavingsMB={MinMB} PreEncodeSavingsThresholdPercent={ThresholdPct}%")


if __name__ == '__main__':
    Main()
