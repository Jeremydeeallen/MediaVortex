# see failure-accounting.C10 -- adds worker_crashed_restarted seed rule so cgroup OOM writes classify
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


_SEED_ROW = (
    'worker_crashed_restarted',
    75,
    r'worker crashed/restarted',
    False,
    'Worker was killed mid-job (systemd cgroup OOM or system restart). Check MemoryMax + host memory pressure; see worker-deploy-baremetal.md.',
)


def Main():
    Db = DatabaseService()
    Db.ExecuteNonQuery(
        "INSERT INTO FailureClasses (ClassName, Priority, ErrorPattern, Terminal, Remediation) "
        "VALUES (%s, %s, %s, %s, %s) "
        "ON CONFLICT (ClassName) DO NOTHING",
        _SEED_ROW,
    )
    Rows = Db.ExecuteQuery(
        "SELECT ClassName, Priority, Terminal FROM FailureClasses WHERE ClassName = %s",
        (_SEED_ROW[0],),
    )
    if not Rows:
        raise RuntimeError(f"seed row {_SEED_ROW[0]} missing after upsert")
    print(f"Applied. FailureClasses row present: {Rows[0]}")


if __name__ == '__main__':
    Main()
