from Core.Path.LocalPath import LocalExists, LocalIsFile, LocalIsDir, LocalGetSize, LocalGetMTime


# directive: path-perfect-implementation | # see path.S10
def Exists(P, Worker) -> bool:
    if P is None:
        return False
    try:
        return LocalExists(P.Resolve(Worker))
    except Exception:
        return False


# directive: path-perfect-implementation | # see path.S10
def IsFile(P, Worker) -> bool:
    if P is None:
        return False
    try:
        return LocalIsFile(P.Resolve(Worker))
    except Exception:
        return False


# directive: path-perfect-implementation | # see path.S10
def IsDir(P, Worker) -> bool:
    if P is None:
        return False
    try:
        return LocalIsDir(P.Resolve(Worker))
    except Exception:
        return False


# directive: path-perfect-implementation | # see path.S10
def GetSize(P, Worker) -> int:
    return LocalGetSize(P.Resolve(Worker))


# directive: path-perfect-implementation | # see path.S10
def GetMTime(P, Worker) -> float:
    return LocalGetMTime(P.Resolve(Worker))
