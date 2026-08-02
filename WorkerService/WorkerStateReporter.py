from datetime import datetime


# directive: worker-runtime-state | see workerservice.ST14
class WorkerStateReporter:
    """Sole writer of Workers.RuntimeState + Workers.CurrentAttemptId."""

    # directive: worker-runtime-state
    def __init__(self, Db, WorkerName, Clock=None):
        self.Db = Db
        self.WorkerName = WorkerName
        self.Clock = Clock if Clock is not None else datetime.utcnow

    # directive: worker-runtime-state
    def Transition(self, NewState, AttemptId=None):
        self.Db.ExecuteNonQuery(
            "UPDATE Workers SET RuntimeState = %s, CurrentAttemptId = %s "
            "WHERE WorkerName = %s",
            (NewState, AttemptId, self.WorkerName),
        )
