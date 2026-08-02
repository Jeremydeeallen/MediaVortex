# see .claude/rules/worker-lifecycle-invariants.md I3 -- LastRuntimeStateUpdate was a duplicate of LastHeartbeat (both written in the same health-check tick). Consolidated to LastHeartbeat; drop column + delete redundant setting.
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from Core.Database.DatabaseService import DatabaseService

def Run():
    Db = DatabaseService()
    Db.ExecuteNonQuery("ALTER TABLE Workers DROP COLUMN IF EXISTS LastRuntimeStateUpdate")
    Db.ExecuteNonQuery("DELETE FROM SystemSettings WHERE SettingKey='WorkerIntentDivergenceSec'")
    print("Dropped LastRuntimeStateUpdate column + WorkerIntentDivergenceSec setting")

if __name__ == '__main__':
    Run()
