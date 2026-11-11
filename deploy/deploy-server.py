import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

Root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Root))

from deploy.common import MediaVortexRoot, SshOpts, ServerDeployTarget, Sh, ResolveInventory

ServerUnit = "mediavortex-server.service"
ServerPort = 5000
VerifyTimeoutSec = 60


# directive: farm-server | # see worker-deploy-baremetal.ST7
def _Git(*Args) -> subprocess.CompletedProcess:
    return Sh(["git", *Args], cwd=str(MediaVortexRoot), timeout=120)


# directive: farm-server | # see worker-deploy-baremetal.ST7
def _ResolveSha(Ref: str) -> str:
    R = _Git("rev-parse", "--verify", f"{Ref}^{{commit}}")
    if R.returncode != 0:
        raise SystemExit(f"[FAIL] cannot resolve commit {Ref}: {R.stderr.strip()}")
    return R.stdout.strip()


# directive: farm-server | # see worker-deploy-baremetal.ST7 -- default target is CI-green origin/main; --sha must already be on main; --rollback toggles to the sha the last OK server deploy replaced
def _ResolveNewSha(Args, Db) -> str:
    if Args.rollback:
        Rows = Db.ExecuteQuery(
            "SELECT PriorSha FROM DeployHistory WHERE Outcome='OK' AND HostsAttempted=%s ORDER BY Id DESC LIMIT 1",
            (ServerDeployTarget,))
        if not Rows or not Rows[0]["PriorSha"]:
            raise SystemExit("[FAIL] no prior OK server deploy to roll back to")
        return _ResolveSha(Rows[0]["PriorSha"])
    Main = _ResolveSha("origin/main")
    if not Args.sha:
        return Main
    Sha = _ResolveSha(Args.sha)
    if _Git("merge-base", "--is-ancestor", Sha, Main).returncode != 0:
        raise SystemExit(f"[FAIL] {Sha[:8]} is not on origin/main; only committed main history deploys")
    return Sha


# directive: farm-server | # see worker-deploy-baremetal.ST7
def _Ssh(Target: str, Command: str, Timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(["ssh", *SshOpts, Target, Command], capture_output=True, text=True, timeout=Timeout)


# directive: farm-server | # see worker-deploy-baremetal.ST7 -- the running sha is the VERSION file inside the unit's WorkingDirectory; empty on the first deploy
def _RunningSha(Target: str) -> str:
    R = _Ssh(Target, f"D=$(systemctl show -p WorkingDirectory --value {ServerUnit}); [ -n \"$D\" ] && cat \"$D/VERSION\" 2>/dev/null", 15)
    return (R.stdout or "").strip()


# directive: farm-server | # see worker-deploy-baremetal.ST7
def _FetchVersion(Ip: str) -> dict:
    with urllib.request.urlopen(f"http://{Ip}:{ServerPort}/api/Version", timeout=3) as Resp:
        return json.loads(Resp.read().decode("utf-8"))


# directive: farm-server | # see worker-deploy-baremetal.ST7 -- the deploy is done only when the restarted process itself reports the target sha over HTTP
def _VerifySha(Ip: str, Sha: str) -> tuple:
    Deadline = time.time() + VerifyTimeoutSec
    Last = "no response"
    while time.time() < Deadline:
        try:
            Body = _FetchVersion(Ip)
            Reported = (Body.get("Data") or {}).get("Sha")
            if Reported == Sha:
                return True, ""
            Last = f"reports sha {Reported!r}"
        except (urllib.error.URLError, ConnectionError, TimeoutError, json.JSONDecodeError) as Ex:
            Last = f"{type(Ex).__name__}: {Ex}"
        time.sleep(1)
    return False, f"/api/Version did not report {Sha[:8]} within {VerifyTimeoutSec}s ({Last})"


# directive: farm-server | # see worker-deploy-baremetal.ST7
def _Ship(Target: str, Ip: str, Sha: str, Timings: list) -> tuple:
    T = time.time()
    Rc = subprocess.run([sys.executable, "-u", str(MediaVortexRoot / "deploy" / "deploy-baremetal-worker.py"),
                         ServerDeployTarget, "--role", "server", "--sha", Sha]).returncode
    Timings.append((f"sync {Sha[:8]}", time.time() - T))
    if Rc != 0:
        return False, f"host sync rc={Rc}"
    T = time.time()
    R = _Ssh(Target, f"systemctl restart {ServerUnit}", 60)
    Timings.append((f"restart {Sha[:8]}", time.time() - T))
    if R.returncode != 0:
        return False, f"systemctl restart rc={R.returncode}: {(R.stderr or '').strip()[-200:]}"
    T = time.time()
    Ok, Err = _VerifySha(Ip, Sha)
    Timings.append((f"verify {Sha[:8]}", time.time() - T))
    return Ok, Err


# directive: farm-server | # see worker-deploy-baremetal.ST7
def Main(Argv=None) -> int:
    P = argparse.ArgumentParser(description="Deploy the WebService to the farm server: origin/main by default, verified by /api/Version, auto-revert on failure.")
    Group = P.add_mutually_exclusive_group()
    Group.add_argument("--sha", default=None, help="Deploy this commit (must be on origin/main).")
    Group.add_argument("--rollback", action="store_true", help="Redeploy the sha the last OK server deploy replaced.")
    Args = P.parse_args(Argv)

    T0 = time.time()
    Timings = []
    if _Git("fetch", "-q", "origin", "main").returncode != 0:
        print("[FAIL] git fetch origin main failed")
        return 2
    Timings.append(("git fetch", time.time() - T0))

    from Core.Database.DatabaseService import DatabaseService
    Db = DatabaseService()
    _, Ip, User = ResolveInventory(ServerDeployTarget)
    Target = f"{User}@{Ip}"
    NewSha = _ResolveNewSha(Args, Db)
    PriorSha = _RunningSha(Target)
    print(f"deploy-server: {ServerDeployTarget} ({Target}) {PriorSha[:8] or '(none)'} -> {NewSha[:8]}", flush=True)

    HistId = Db.ExecuteReturning(
        "INSERT INTO DeployHistory (StartedAt, PriorSha, NewSha, HostsAttempted, Outcome) "
        "VALUES (NOW(), %s, %s, %s, 'RUNNING') RETURNING Id",
        (PriorSha or None, NewSha, ServerDeployTarget))[0]["Id"]

    def _Finish(Outcome: str, Succeeded: str, ErrorMessage) -> None:
        Db.ExecuteNonQuery(
            "UPDATE DeployHistory SET CompletedAt=NOW(), ElapsedSeconds=EXTRACT(EPOCH FROM (NOW() - StartedAt))::int, "
            "HostsSucceeded=%s, Outcome=%s, ErrorMessage=%s WHERE Id=%s",
            (Succeeded, Outcome, ErrorMessage, HistId))

    Ok, Err = _Ship(Target, Ip, NewSha, Timings)
    if not Ok:
        print(f"[FAIL] {NewSha[:8]}: {Err}", flush=True)
        if PriorSha:
            print(f"reverting to {PriorSha[:8]}", flush=True)
            RevertOk, RevertErr = _Ship(Target, Ip, PriorSha, Timings)
            Err = f"{Err}; revert to {PriorSha[:8]} {'OK' if RevertOk else 'FAILED: ' + RevertErr}"
        _Finish("FAILED", "", Err)
        _PrintTimings(Timings, T0)
        print(f"== FAILED (DeployHistory Id={HistId}): {Err} ==")
        return 1

    _Finish("OK", ServerDeployTarget, None)
    _PrintTimings(Timings, T0)
    print(f"== SERVER ON {NewSha[:8]} (DeployHistory Id={HistId}) ==")
    return 0


# directive: farm-server | # see worker-deploy-baremetal.ST7
def _PrintTimings(Timings: list, T0: float) -> None:
    print()
    for Name, Seconds in Timings:
        print(f"  {Name:<24} {Seconds:6.1f}s")
    print(f"  {'total':<24} {time.time() - T0:6.1f}s")


if __name__ == "__main__":
    sys.exit(Main())
