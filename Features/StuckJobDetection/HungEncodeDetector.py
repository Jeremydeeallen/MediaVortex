# directive: worker-runtime-state | # see admin-workers.C9
def IsHung(RuntimeState, HeartbeatAgeSec, ProgressAgeSec, ThresholdSec):
    """Pure: a worker reporting RuntimeState='Encoding' with both ages > threshold and no progress signal is hung."""
    if RuntimeState != 'Encoding':
        return False
    if HeartbeatAgeSec is None or int(HeartbeatAgeSec) <= int(ThresholdSec):
        return False
    if ProgressAgeSec is None:
        return True
    return int(ProgressAgeSec) > int(ThresholdSec)
