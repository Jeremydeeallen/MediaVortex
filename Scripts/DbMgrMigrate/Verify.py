# directive: db-monolith-decompose
import argparse
import csv
import importlib
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
INVENTORY_FILE = Path(__file__).resolve().parent / "inventory.csv"

EXCLUDE_DIRS = {"venv", ".git", "__pycache__", "node_modules", ".claude", ".github", "Scripts"}


# directive: db-monolith-decompose
def LoadAggregateMethods(AggregateName: str) -> tuple[list[str], str]:
    if not INVENTORY_FILE.exists():
        raise SystemExit(f"inventory.csv missing; run Inventory.py first: {INVENTORY_FILE}")
    Methods: list[str] = []
    TargetFile = ""
    with INVENTORY_FILE.open("r", encoding="utf-8", newline="") as Handle:
        for Row in csv.DictReader(Handle):
            if Row["target_aggregate"] == AggregateName and Row["classification"] == "clean":
                Methods.append(Row["method_name"])
                TargetFile = Row["target_file"]
    return sorted(set(Methods)), TargetFile


# directive: db-monolith-decompose
def IterProductionPythonFiles(Root: Path):
    for Candidate in Root.rglob("*.py"):
        Skip = False
        for Part in Candidate.relative_to(Root).parts[:-1]:
            if Part in EXCLUDE_DIRS:
                Skip = True
                break
        if not Skip:
            yield Candidate


# directive: db-monolith-decompose
def CheckResiduals(Methods: list[str]) -> tuple[bool, list[str]]:
    SourceFile = REPO_ROOT / "Repositories" / "DatabaseManager.py"
    Hits: list[str] = []
    Needles = [f"self.DatabaseManager.{M}(" for M in Methods]
    for File in IterProductionPythonFiles(REPO_ROOT):
        if File.resolve() == SourceFile.resolve():
            continue
        try:
            Text = File.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for Needle in Needles:
            if Needle in Text:
                Hits.append(f"{File.relative_to(REPO_ROOT)}: {Needle.rstrip('(')}")
    return (len(Hits) == 0), Hits


# directive: db-monolith-decompose
def CheckImportSanity(TargetFile: str) -> tuple[bool, str]:
    if not TargetFile:
        return False, "no target file in inventory"
    ModulePath = TargetFile.replace("\\", "/").removesuffix(".py").replace("/", ".")
    sys.path.insert(0, str(REPO_ROOT))
    try:
        Module = importlib.import_module(ModulePath)
        ClassName = Path(TargetFile.replace("\\", "/")).stem
        if not hasattr(Module, ClassName):
            return False, f"module {ModulePath} loaded but missing class {ClassName}"
        return True, f"import {ModulePath}.{ClassName} OK"
    except Exception as E:
        return False, f"import {ModulePath} failed: {type(E).__name__}: {E}"
    finally:
        if str(REPO_ROOT) in sys.path:
            sys.path.remove(str(REPO_ROOT))


# directive: db-monolith-decompose
def RunPytest(AggregateName: str) -> tuple[bool, str]:
    TestsDir = REPO_ROOT / "Tests" / "Unit"
    if not TestsDir.exists():
        return True, "Tests/Unit/ does not exist; skipping pytest (treated as pass)"
    Cmd = [sys.executable, "-m", "pytest", str(TestsDir), "-k", AggregateName, "-q", "--no-header"]
    Result = subprocess.run(Cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    if Result.returncode == 0:
        return True, f"pytest -k {AggregateName} passed"
    if Result.returncode == 5:
        return True, f"pytest -k {AggregateName}: no tests matched (treated as pass)"
    return False, f"pytest -k {AggregateName} failed (rc={Result.returncode}): {Result.stdout.strip()[-400:]} {Result.stderr.strip()[-200:]}"


# directive: db-monolith-decompose
def Verify(AggregateName: str) -> int:
    Methods, TargetFile = LoadAggregateMethods(AggregateName)
    if not Methods:
        print(f"FAIL: aggregate '{AggregateName}' has no clean methods in inventory.csv")
        return 2
    print(f"Aggregate: {AggregateName} ({len(Methods)} method(s), target {TargetFile})")
    ResidualOk, Hits = CheckResiduals(Methods)
    if ResidualOk:
        print("  PASS  residual-grep: zero self.DatabaseManager.<method> hits in production tree")
    else:
        print(f"  FAIL  residual-grep: {len(Hits)} hit(s):")
        for H in Hits[:10]:
            print(f"          {H}")
        if len(Hits) > 10:
            print(f"          ... and {len(Hits) - 10} more")
    ImportOk, ImportMsg = CheckImportSanity(TargetFile)
    print(f"  {'PASS' if ImportOk else 'FAIL'}  import-sanity: {ImportMsg}")
    PytestOk, PytestMsg = RunPytest(AggregateName)
    print(f"  {'PASS' if PytestOk else 'FAIL'}  pytest-k: {PytestMsg}")
    return 0 if (ResidualOk and ImportOk and PytestOk) else 1


# directive: db-monolith-decompose
def Main() -> int:
    Parser = argparse.ArgumentParser(description="Verify migration of one aggregate: residual grep + import-sanity + pytest -k.")
    Parser.add_argument("--aggregate", required=True, help="target aggregate name")
    Args = Parser.parse_args()
    return Verify(Args.aggregate)


if __name__ == "__main__":
    sys.exit(Main())
