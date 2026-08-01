# see probe-worker-decoupled -- ProbeWorker + OnDemandScanWorker record ActiveJobs with Phase='Probing'/'Scanning'; existing enum only allowed Setup/PreEncode/Encoding/PostEncode/Verifying so INSERTs failed CHECK, leaving drain blind.
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


def Run():
    Db = DatabaseService()
    Db.ExecuteNonQuery("ALTER TABLE ActiveJobs DROP CONSTRAINT IF EXISTS activejobs_phase_enum")
    Db.ExecuteNonQuery(
        "ALTER TABLE ActiveJobs ADD CONSTRAINT activejobs_phase_enum "
        "CHECK (Phase IS NULL OR Phase = ANY (ARRAY["
        "'Setup','PreEncode','Encoding','PostEncode','Verifying',"
        "'Probing','Scanning','DetectingLanguage'"
        "]))"
    )
    print("Expanded activejobs_phase_enum to include Probing/Scanning/DetectingLanguage")


if __name__ == '__main__':
    Run()
