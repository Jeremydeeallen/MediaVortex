import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Core.Database.DatabaseService import DatabaseService


def _HeadSha() -> str:
    R = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
    return (R.stdout or "").strip()


def Main() -> int:
    Hosts = sys.argv[1:] if len(sys.argv) > 1 else ["dot", "wakko", "larry"]
    Sha = _HeadSha()
    if not Sha:
        print("[FAIL] cannot resolve git HEAD")
        return 2
    Prefix = Sha[:8]
    print(f"[wait] HEAD={Prefix}; hosts={Hosts}; will Online <host>-worker-1 as each arrives.")

    Db = DatabaseService()
    Pending = set(Hosts)
    Deadline = time.time() + 1500

    while Pending and time.time() < Deadline:
        for Host in list(Pending):
            Wn = f"{Host}-worker-1"
            Rows = Db.ExecuteQuery(
                "SELECT COALESCE(Version,'') AS Version, "
                "EXTRACT(EPOCH FROM (NOW() - LastHeartbeat))::int AS HbAge, "
                "Status FROM Workers WHERE WorkerName = %s",
                (Wn,),
            )
            if not Rows:
                continue
            R = Rows[0]
            Version = (R.get("version") or R.get("Version") or "")
            HbAge = R.get("hbage") if "hbage" in R else R.get("HbAge")
            HbAge = int(HbAge or 999)
            Status = R.get("status") or R.get("Status") or ""
            if Version.startswith(Prefix) and HbAge < 60:
                if Status != "Online":
                    Db.ExecuteNonQuery(
                        "UPDATE Workers SET Status='Online' WHERE WorkerName=%s",
                        (Wn,),
                    )
                    print(f"[ONLINE] {Wn} version={Version[:8]} hb={HbAge}s")
                else:
                    print(f"[ONLINE-already] {Wn} version={Version[:8]} hb={HbAge}s")
                Pending.discard(Host)
        if Pending:
            time.sleep(10)

    if Pending:
        print(f"[TIMEOUT] still pending: {sorted(Pending)}")
        return 1
    print("[OK] all requested hosts Online")
    return 0


if __name__ == "__main__":
    sys.exit(Main())
