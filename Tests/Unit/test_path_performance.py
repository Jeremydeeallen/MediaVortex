# directive: path-performance-budget | # see path.C1
import sys
import time
from dataclasses import dataclass
from statistics import median, quantiles
from unittest.mock import patch

import pytest

from Core.Path.Path import Path, PathError


@dataclass(frozen=True)
# directive: path-performance-budget | # see path.C9
class _CachedWorker:
    """Worker stub whose ResolveStorageRoot returns a precomputed prefix (no I/O)."""

    Name: str = "perf-worker"
    Platform: str = "linux"
    Prefix: str = "/mnt/media/"

    # directive: path-performance-budget | # see path.C9
    def ResolveStorageRoot(self, Sid):
        """Constant-time prefix lookup; no DB."""
        return self.Prefix if Sid == 7 else None


# directive: path-performance-budget | # see path.C3
def _MeasureP99(Fn, Iterations: int = 10_000) -> tuple:
    """Time Fn() across Iterations; return (median_ns, p99_ns)."""
    Latencies = []
    for _ in range(Iterations):
        T0 = time.perf_counter_ns()
        Fn()
        T1 = time.perf_counter_ns()
        Latencies.append(T1 - T0)
    Qs = quantiles(Latencies, n=100)
    return median(Latencies), Qs[98]


@pytest.mark.perf
# directive: path-performance-budget | # see path.C2
def test_identity_methods_do_not_touch_filesystem():
    """C2: identity methods do not reach os.path or os.stat. unittest.mock.patch raises if they try."""
    P = Path(7, "Show/Season 1/Episode 1.mkv")
    Q = Path(7, "Show/Season 1/Episode 1.mkv")
    Targets = [
        "os.path.exists", "os.path.isfile", "os.path.isdir",
        "os.path.getsize", "os.path.getmtime", "os.stat",
    ]
    Patches = [patch(T, side_effect=AssertionError(f"identity method touched {T}")) for T in Targets]
    for Pp in Patches:
        Pp.start()
    try:
        assert P == Q
        assert hash(P) == hash(Q)
        assert repr(P) == "<Path #7:Show/Season 1/Episode 1.mkv>"
        assert str(P) == "<Path #7:Show/Season 1/Episode 1.mkv>"
        Payload = P.ToJsonDict()
        assert Payload == {"StorageRootId": 7, "RelativePath": "Show/Season 1/Episode 1.mkv"}
        assert Path.FromJsonDict(Payload) == P
    finally:
        for Pp in Patches:
            Pp.stop()


@pytest.mark.perf
# directive: path-performance-budget | # see path.C3
def test_eq_p99_under_10us():
    """C3: __eq__ p99 < 10 us across 10000 iterations on typical-length Paths."""
    A = Path(7, "Show/Season 1/Episode 1.mkv")
    B = Path(7, "Show/Season 1/Episode 1.mkv")
    Med, P99 = _MeasureP99(lambda: A == B)
    print(f"\n[perf] __eq__ median={Med}ns p99={P99}ns")
    assert P99 < 10_000


@pytest.mark.perf
# directive: path-performance-budget | # see path.C4
def test_hash_p99_under_10us():
    """C4: __hash__ p99 < 10 us."""
    P = Path(7, "Show/Season 1/Episode 1.mkv")
    Med, P99 = _MeasureP99(lambda: hash(P))
    print(f"\n[perf] __hash__ median={Med}ns p99={P99}ns")
    assert P99 < 10_000


@pytest.mark.perf
# directive: path-performance-budget | # see path.C5
def test_repr_p99_under_10us():
    """C5: __repr__ p99 < 10 us."""
    P = Path(7, "Show/Season 1/Episode 1.mkv")
    Med, P99 = _MeasureP99(lambda: repr(P))
    print(f"\n[perf] __repr__ median={Med}ns p99={P99}ns")
    assert P99 < 10_000


@pytest.mark.perf
# directive: path-performance-budget | # see path.C5
def test_str_p99_under_10us():
    """C6: __str__ p99 < 10 us."""
    P = Path(7, "Show/Season 1/Episode 1.mkv")
    Med, P99 = _MeasureP99(lambda: str(P))
    print(f"\n[perf] __str__ median={Med}ns p99={P99}ns")
    assert P99 < 10_000


@pytest.mark.perf
# directive: path-performance-budget | # see path.S2
def test_tojsondict_p99_under_10us():
    """C7: ToJsonDict p99 < 10 us."""
    P = Path(7, "Show/Season 1/Episode 1.mkv")
    Med, P99 = _MeasureP99(lambda: P.ToJsonDict())
    print(f"\n[perf] ToJsonDict median={Med}ns p99={P99}ns")
    assert P99 < 10_000


@pytest.mark.perf
# directive: path-performance-budget | # see path.C4
def test_construction_p99_under_100us():
    """C8: Path(...) construction p99 < 100 us across 10000 iterations."""
    Med, P99 = _MeasureP99(lambda: Path(7, "Show/Season 1/Episode 1.mkv"))
    print(f"\n[perf] Path(...) median={Med}ns p99={P99}ns")
    assert P99 < 100_000


@pytest.mark.perf
# directive: path-performance-budget | # see path.C8
def test_resolve_p99_under_1ms():
    """C9: Resolve(worker) p99 < 1 ms with cached ResolveStorageRoot."""
    P = Path(7, "Show/Season 1/Episode 1.mkv")
    W = _CachedWorker()
    Med, P99 = _MeasureP99(lambda: P.Resolve(W))
    print(f"\n[perf] Resolve median={Med}ns p99={P99}ns")
    assert P99 < 1_000_000


@pytest.mark.perf
# directive: path-performance-budget | # see path.C1
def test_slots_reduces_memory():
    """C16: slots=True reduces per-instance memory; instance has no __dict__."""
    P = Path(7, "Show/file.mkv")
    assert Path.__slots__ == ("StorageRootId", "RelativePath")
    assert not hasattr(P, "__dict__")
    InstanceSize = sys.getsizeof(P)
    print(f"\n[perf] sys.getsizeof(Path) = {InstanceSize} bytes (no __dict__)")
    assert InstanceSize < 200


@pytest.mark.perf
# directive: path-performance-budget | # see path.C4
def test_hot_path_50k_constructions_under_5s():
    """C14: 50,000 back-to-back constructions in < 5 seconds; projects per-iteration budget to FileScanning's batch size."""
    T0 = time.perf_counter_ns()
    Batch = [Path(7, f"Show/Season {I % 20}/Episode {I}.mkv") for I in range(50_000)]
    T1 = time.perf_counter_ns()
    ElapsedSec = (T1 - T0) / 1e9
    print(f"\n[perf] 50K constructions: {ElapsedSec:.3f}s total ({(T1-T0)/50_000:.0f}ns/op avg)")
    assert len(Batch) == 50_000
    assert ElapsedSec < 5.0


@pytest.mark.perf
# directive: path-performance-budget | # see path.C8
def test_hot_path_10k_resolves_under_10s():
    """C15: 10,000 Resolve calls on a single Path in < 10 seconds."""
    P = Path(7, "Show/Season 1/Episode 1.mkv")
    W = _CachedWorker()
    T0 = time.perf_counter_ns()
    Results = [P.Resolve(W) for _ in range(10_000)]
    T1 = time.perf_counter_ns()
    ElapsedSec = (T1 - T0) / 1e9
    print(f"\n[perf] 10K resolves: {ElapsedSec:.3f}s total ({(T1-T0)/10_000:.0f}ns/op avg)")
    assert len(Results) == 10_000
    assert ElapsedSec < 10.0
