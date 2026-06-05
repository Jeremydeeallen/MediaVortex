import sys
import time
from pathlib import Path as PyPath
sys.path.insert(0, str(PyPath(__file__).resolve().parent))

from Core.Database.DatabaseService import DatabaseService


# directive: path-schema-migration | # see path.S8
def Snapshot(Db, QueueId: int):
    Q = Db.ExecuteQuery(
        "SELECT Id, Status, Priority, ClaimedBy, DateStarted, "
        "EXTRACT(EPOCH FROM (NOW() - DateStarted))::int AS RunSec, "
        "ProcessingMode "
        "FROM TranscodeQueue WHERE Id = %s",
        (QueueId,),
    )[0]
    Att = Db.ExecuteQuery(
        "SELECT ta.Id, ta.Success, ta.ProfileName, ta.VMAF, ta.FileReplaced, ta.AttemptDate, "
        "ta.NewSizeBytes, ta.OldSizeBytes, ta.TranscodeDurationSeconds "
        "FROM TranscodeAttempts ta "
        "WHERE ta.MediaFileId = ("
        "  SELECT MediaFileId FROM TranscodeQueue WHERE Id = %s"
        ") "
        "ORDER BY ta.AttemptDate DESC LIMIT 1",
        (QueueId,),
    )
    Prog = Db.ExecuteQuery(
        "SELECT tp.ProgressPercent, tp.CurrentPhase, tp.CurrentFPS, tp.CurrentSpeed, tp.ETA "
        "FROM TranscodeProgress tp "
        "JOIN TranscodeAttempts ta ON tp.TranscodeAttemptId = ta.Id "
        "WHERE ta.MediaFileId = ("
        "  SELECT MediaFileId FROM TranscodeQueue WHERE Id = %s"
        ") "
        "ORDER BY tp.LastProgressUpdate DESC LIMIT 1",
        (QueueId,),
    )
    return {"queue": Q, "attempt": Att[0] if Att else None, "progress": Prog[0] if Prog else None}


# directive: path-schema-migration | # see path.S8
def Render(S):
    Q = S["queue"]
    Out = f"[Q] Status={Q['status']} Priority={Q['priority']} ClaimedBy={Q['claimedby']} RunSec={Q.get('runsec') or 0}"
    A = S["attempt"]
    if A:
        Out += f"  [A] AttId={A['id']} Success={A['success']} Profile={A['profilename']} VMAF={A['vmaf']} Replaced={A['filereplaced']}"
        if A.get('newsizebytes') and A.get('oldsizebytes'):
            ReductionPct = (1 - A['newsizebytes'] / A['oldsizebytes']) * 100
            Out += f"  Old={A['oldsizebytes']//1_048_576}MB->New={A['newsizebytes']//1_048_576}MB ({ReductionPct:.1f}% saved)"
    P = S["progress"]
    if P:
        Out += f"\n      [P] {P['progresspercent']:.1f}% phase={P['currentphase']} fps={P['currentfps']} speed={P['currentspeed']} eta={P['eta']}"
    return Out


if __name__ == "__main__":
    Db = DatabaseService()
    QueueId = int(sys.argv[1]) if len(sys.argv) > 1 else 128276
    Iterations = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    SleepSec = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    for I in range(Iterations):
        print(f"t+{I*SleepSec}s  " + Render(Snapshot(Db, QueueId)))
        if I < Iterations - 1:
            time.sleep(SleepSec)
