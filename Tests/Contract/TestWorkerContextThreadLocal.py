import threading

import pytest

from Core.WorkerContext import WorkerContext, WorkerContextNotBoundError


@pytest.fixture(autouse=True)
def _ResetContext():
    WorkerContext.Reset()
    yield
    WorkerContext.Reset()


def test_Current_raises_on_unbound_thread():
    with pytest.raises(WorkerContextNotBoundError):
        WorkerContext.Current()


def test_TryCurrent_returns_none_on_unbound_thread():
    assert WorkerContext.TryCurrent() is None


def test_Bind_from_template_seeds_current_thread():
    WorkerContext.Initialize(WorkerName="main-worker", Platform="linux", FFmpegPath="/opt/ffmpeg", FFprobePath="/opt/ffprobe")
    WorkerContext.Bind()
    Ctx = WorkerContext.Current()
    assert Ctx.WorkerName == "main-worker"
    assert Ctx.FFmpegPath == "/opt/ffmpeg"


def test_Bind_with_no_template_raises():
    with pytest.raises(WorkerContextNotBoundError):
        WorkerContext.Bind()


def test_Bind_isolates_between_threads():
    WorkerContext.Initialize(WorkerName="template-worker", Platform="linux", FFmpegPath="/opt/ffmpeg")
    Seen = {}

    def RunOnChild(WorkerName, FFmpegPath, Key):
        Custom = WorkerContext(WorkerName=WorkerName, Platform="linux", FFmpegPath=FFmpegPath)
        WorkerContext.Bind(Custom)
        Seen[Key] = (WorkerContext.Current().WorkerName, WorkerContext.Current().FFmpegPath)

    T1 = threading.Thread(target=RunOnChild, args=("child-1", "/opt/ff1", "t1"))
    T2 = threading.Thread(target=RunOnChild, args=("child-2", "/opt/ff2", "t2"))
    T1.start(); T2.start(); T1.join(); T2.join()

    assert Seen["t1"] == ("child-1", "/opt/ff1")
    assert Seen["t2"] == ("child-2", "/opt/ff2")
    assert WorkerContext.Current().WorkerName == "template-worker"


def test_child_thread_without_Bind_raises():
    WorkerContext.Initialize(WorkerName="main-worker", Platform="linux")
    Raised = {}

    def RunOnChildNoBind():
        try:
            WorkerContext.Current()
            Raised["value"] = None
        except WorkerContextNotBoundError as Ex:
            Raised["value"] = Ex

    T = threading.Thread(target=RunOnChildNoBind)
    T.start(); T.join()
    assert isinstance(Raised["value"], WorkerContextNotBoundError)


def test_child_thread_Bind_from_template_gets_template_values():
    WorkerContext.Initialize(WorkerName="main-worker", Platform="linux", FFmpegPath="/opt/ffmpeg")
    Seen = {}

    def RunOnChildImplicit():
        WorkerContext.Bind()
        Seen["name"] = WorkerContext.Current().WorkerName

    T = threading.Thread(target=RunOnChildImplicit)
    T.start(); T.join()
    assert Seen["name"] == "main-worker"


def test_Reset_clears_current_thread():
    WorkerContext.Initialize(WorkerName="main-worker", Platform="linux")
    assert WorkerContext.Current().WorkerName == "main-worker"
    WorkerContext.Reset()
    assert WorkerContext.TryCurrent() is None
    with pytest.raises(WorkerContextNotBoundError):
        WorkerContext.Current()
