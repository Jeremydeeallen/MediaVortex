# directive: db-monolith-decompose
import argparse
import ast
import csv
import difflib
import re
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
INVENTORY_FILE = Path(__file__).resolve().parent / "inventory.csv"

EXCLUDE_DIRS = {"venv", ".git", "__pycache__", "node_modules", ".claude", ".github", "Scripts"}


# directive: db-monolith-decompose
def LoadAggregateMethods(AggregateName: str) -> tuple[list[str], str, str]:
    if not INVENTORY_FILE.exists():
        raise SystemExit(f"inventory.csv missing; run Inventory.py first: {INVENTORY_FILE}")
    Methods: list[str] = []
    TargetFile = ""
    with INVENTORY_FILE.open("r", encoding="utf-8", newline="") as Handle:
        for Row in csv.DictReader(Handle):
            if Row["target_aggregate"] == AggregateName and Row["classification"] == "clean":
                Methods.append(Row["method_name"])
                TargetFile = Row["target_file"]
    UniqueMethods = sorted(set(Methods), key=lambda M: -len(M))
    ClassName = Path(TargetFile.replace("\\", "/")).stem if TargetFile else ""
    ImportModule = TargetFile.replace("\\", "/").replace("/", ".").removesuffix(".py") if TargetFile else ""
    return UniqueMethods, ClassName, ImportModule


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
def RewriteCallSites(Content: str, Methods: list[str], ClassName: str) -> tuple[str, int]:
    Count = 0
    Result = Content
    for Method in Methods:
        Needle = f"self.DatabaseManager.{Method}("
        Replacement = f"self.{ClassName}.{Method}("
        N = Result.count(Needle)
        if N:
            Result = Result.replace(Needle, Replacement)
            Count += N
    return Result, Count


# directive: db-monolith-decompose
def FindContainingClasses(Content: str, Methods: list[str]) -> set[str]:
    try:
        Tree = ast.parse(Content)
    except SyntaxError:
        return set()
    Targets = set()
    MethodSet = set(Methods)
    for Node in ast.walk(Tree):
        if not isinstance(Node, ast.ClassDef):
            continue
        for Sub in ast.walk(Node):
            if not isinstance(Sub, ast.Call):
                continue
            Func = Sub.func
            if not isinstance(Func, ast.Attribute):
                continue
            if Func.attr not in MethodSet:
                continue
            Outer = Func.value
            if not isinstance(Outer, ast.Attribute) or Outer.attr != "DatabaseManager":
                continue
            Inner = Outer.value
            if isinstance(Inner, ast.Name) and Inner.id == "self":
                Targets.add(Node.name)
                break
    return Targets


# directive: db-monolith-decompose
def InjectImport(Content: str, ImportModule: str, ClassName: str) -> str:
    ImportLine = f"from {ImportModule} import {ClassName}"
    if ImportLine in Content:
        return Content
    Lines = Content.splitlines(keepends=True)
    InsertIndex = 0
    for I, Line in enumerate(Lines):
        if Line and not Line[0].isspace():
            if Line.startswith("from ") or Line.startswith("import "):
                InsertIndex = I + 1
            elif Line.startswith(("class ", "def ", "@", "async ")):
                break
    Lines.insert(InsertIndex, ImportLine + "\n")
    return "".join(Lines)


# directive: db-monolith-decompose
def InjectInitField(Content: str, TargetClasses: set[str], ClassName: str) -> str:
    try:
        Tree = ast.parse(Content)
    except SyntaxError:
        return Content
    Lines = Content.splitlines(keepends=True)
    ClassNodes: list[ast.ClassDef] = []
    for Node in ast.walk(Tree):
        if isinstance(Node, ast.ClassDef) and Node.name in TargetClasses:
            ClassNodes.append(Node)
    ClassNodes.sort(key=lambda N: N.lineno, reverse=True)
    ParamName = f"{ClassName}Instance"
    AssignLine = f"        self.{ClassName} = {ParamName} or {ClassName}()\n"
    SignatureAdd = f", {ParamName}: Optional[{ClassName}] = None"
    for Class in ClassNodes:
        Init = None
        for Item in Class.body:
            if isinstance(Item, ast.FunctionDef) and Item.name == "__init__":
                Init = Item
                break
        if Init is None:
            ClassBodyEndLine = Class.end_lineno or Class.lineno
            Indent = "    "
            InitBlock = [
                f"{Indent}def __init__(self{SignatureAdd}):\n",
                f"{Indent}    self.{ClassName} = {ParamName} or {ClassName}()\n",
                "\n",
            ]
            Lines = Lines[:ClassBodyEndLine] + InitBlock + Lines[ClassBodyEndLine:]
            continue
        BodyText = "".join(Lines[Init.lineno - 1:(Init.end_lineno or Init.lineno)])
        if f"self.{ClassName}" in BodyText:
            continue
        SignatureLineIndex = FindSignatureCloseLineIndex(Lines, Init.lineno - 1)
        if SignatureLineIndex is None:
            continue
        Lines[SignatureLineIndex] = InjectIntoSignature(Lines[SignatureLineIndex], SignatureAdd)
        InsertAt = (Init.end_lineno or Init.lineno)
        Lines.insert(InsertAt, AssignLine)
    return EnsureOptionalImport("".join(Lines))


# directive: db-monolith-decompose
def FindSignatureCloseLineIndex(Lines: list[str], StartIndex: int) -> Optional[int]:
    Depth = 0
    Started = False
    for I in range(StartIndex, len(Lines)):
        for Ch in Lines[I]:
            if Ch == "(":
                Depth += 1
                Started = True
            elif Ch == ")":
                Depth -= 1
                if Started and Depth == 0:
                    return I
    return None


# directive: db-monolith-decompose
def InjectIntoSignature(Line: str, SignatureAdd: str) -> str:
    Match = re.search(r"\)\s*(->\s*[^:]+)?\s*:\s*$", Line.rstrip("\r\n"))
    if Match is None:
        return Line
    Before = Line[:Match.start()]
    After = Line[Match.start():]
    return Before + SignatureAdd + After


# directive: db-monolith-decompose
def EnsureOptionalImport(Content: str) -> str:
    if re.search(r"\bfrom\s+typing\s+import[^\n]*\bOptional\b", Content):
        return Content
    if re.search(r"\bimport\s+typing\b", Content):
        return Content
    Lines = Content.splitlines(keepends=True)
    InsertIndex = 0
    for I, Line in enumerate(Lines):
        if Line and not Line[0].isspace():
            if Line.startswith("from ") or Line.startswith("import "):
                InsertIndex = I + 1
            elif Line.startswith(("class ", "def ", "@", "async ")):
                break
    Lines.insert(InsertIndex, "from typing import Optional\n")
    return "".join(Lines)


# directive: db-monolith-decompose
def ProcessFile(FilePath: Path, Methods: list[str], ClassName: str, ImportModule: str) -> tuple[str, str, int]:
    try:
        Original = FilePath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return "", "", 0
    AnyMatch = any(f"self.DatabaseManager.{M}(" in Original for M in Methods)
    if not AnyMatch:
        return Original, Original, 0
    TargetClasses = FindContainingClasses(Original, Methods)
    Updated, CallCount = RewriteCallSites(Original, Methods, ClassName)
    if TargetClasses:
        Updated = InjectInitField(Updated, TargetClasses, ClassName)
        Updated = InjectImport(Updated, ImportModule, ClassName)
    return Original, Updated, CallCount


# directive: db-monolith-decompose
def PrintDiff(Label: str, A: str, B: str) -> None:
    Diff = difflib.unified_diff(
        A.splitlines(keepends=True),
        B.splitlines(keepends=True),
        fromfile=Label,
        tofile=Label + " (after)",
    )
    sys.stdout.writelines(Diff)


# directive: db-monolith-decompose
def Sweep(AggregateName: str, DryRun: bool) -> int:
    Methods, ClassName, ImportModule = LoadAggregateMethods(AggregateName)
    if not Methods:
        print(f"No clean methods for aggregate '{AggregateName}' in inventory.csv", file=sys.stderr)
        return 2
    if not ClassName or not ImportModule:
        print(f"Could not derive class/module for aggregate '{AggregateName}'", file=sys.stderr)
        return 2
    print(f"Aggregate: {AggregateName} -> {ClassName} ({ImportModule}); {len(Methods)} method(s)")
    TotalFiles = 0
    TotalCalls = 0
    for File in IterProductionPythonFiles(REPO_ROOT):
        if File.resolve() == (REPO_ROOT / "Repositories" / "DatabaseManager.py").resolve():
            continue
        Original, Updated, Count = ProcessFile(File, Methods, ClassName, ImportModule)
        if Count == 0 or Updated == Original:
            continue
        TotalFiles += 1
        TotalCalls += Count
        Rel = File.relative_to(REPO_ROOT)
        if DryRun:
            print(f"--- {Rel}: {Count} call site(s) rewritten")
            PrintDiff(str(Rel), Original, Updated)
            print()
        else:
            File.write_text(Updated, encoding="utf-8")
            print(f"Rewrote {Count} call site(s) in {Rel}")
    print(f"Total: {TotalCalls} call site(s) across {TotalFiles} file(s)")
    return 0


# directive: db-monolith-decompose
def Main() -> int:
    Parser = argparse.ArgumentParser(description="Rewrite self.DatabaseManager.X() -> self.<Agg>Repository.X() across the production tree; inject constructor field where needed.")
    Parser.add_argument("--aggregate", required=True, help="target aggregate name (from inventory.csv target_aggregate column)")
    Parser.add_argument("--dry-run", action="store_true", help="print unified diff to stdout; do not write")
    Args = Parser.parse_args()
    return Sweep(Args.aggregate, Args.dry_run)


if __name__ == "__main__":
    sys.exit(Main())
