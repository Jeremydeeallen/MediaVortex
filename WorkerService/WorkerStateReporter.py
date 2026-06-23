from datetime import datetime


# directive: worker-runtime-state | see workerservice.ST14
class WorkerStateReporter:
    """Sole writer of Workers.RuntimeState / CurrentAttemptId / LastRuntimeStateUpdate."""

    # directive: worker-runtime-state
    def __init__(self, Db, WorkerName, Clock=None):
        self.Db = Db
        self.WorkerName = WorkerName
        self.Clock = Clock if Clock is not None else datetime.utcnow

    # directive: worker-runtime-state
    def Transition(self, NewState, AttemptId=None):
        Now = self.Clock()
        self.Db.ExecuteNonQuery(
            "UPDATE Workers SET RuntimeState = %s, CurrentAttemptId = %s, LastRuntimeStateUpdate = %s "
            "WHERE WorkerName = %s",
            (NewState, AttemptId, Now, self.WorkerName),
        )

    # directive: worker-runtime-state
    def Tick(self):
        Now = self.Clock()
        self.Db.ExecuteNonQuery(
            "UPDATE Workers SET LastRuntimeStateUpdate = %s WHERE WorkerName = %s",
            (Now, self.WorkerName),
        )
