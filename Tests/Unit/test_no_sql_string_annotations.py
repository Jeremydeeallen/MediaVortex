import ast
import re
from pathlib import Path as PathlibPath


REPO_ROOT = PathlibPath(__file__).resolve().parents[2]
PROD_DIRS = ["Core", "Features", "Services", "Repositories", "Models", "WebService", "WorkerService", "Scripts"]
SQL_KEYWORDS = re.compile(
    r'\b(SELECT\s+[\*\w(]|INSERT\s+INTO\s+\w|UPDATE\s+\w+\s+SET|DELETE\s+FROM\s+\w|'
    r'CREATE\s+(TABLE|INDEX|VIEW|UNIQUE)|ALTER\s+TABLE\s+\w|DROP\s+(TABLE|INDEX|VIEW)|'
    r'WITH\s+\w+\s+AS\s*\()',
    re.IGNORECASE,
)
ANNOTATION_RE = re.compile(r'#\s*allow:')


def iter_py_files():
    for sub in PROD_DIRS:
        d = REPO_ROOT / sub
        if not d.is_dir():
            continue
        for p in d.rglob("*.py"):
            yield p


def find_sql_string_annotations(src: str):
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            s = node.value
            if SQL_KEYWORDS.search(s) and ANNOTATION_RE.search(s):
                lineno = getattr(node, "lineno", 0)
                out.append((lineno, s[:100].replace("\n", " | ")))
    return out


# directive: path-class-perfection | # see path.C22
def test_no_allow_annotation_in_sql_strings():
    violations = []
    for p in iter_py_files():
        try:
            src = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, snippet in find_sql_string_annotations(src):
            violations.append(f"{p.relative_to(REPO_ROOT)}:{lineno} :: {snippet}")
    assert not violations, (
        "C22 violation: '# allow:' baked inside SQL string literal -- PostgreSQL treats '#' "
        "as a syntax error. Move the annotation to the Python line OUTSIDE the string:\n"
        + "\n".join(violations)
    )


# directive: path-class-perfection | # see path.C22
def test_gate_catches_deliberate_violation():
    bad = (
        'QUERY = """\n'
        '    SELECT id, name # allow: R12 -- preexisting\n'
        '    FROM mytable\n'
        '"""\n'
    )
    found = find_sql_string_annotations(bad)
    assert len(found) == 1, f"expected 1 violation, got {len(found)}: {found}"
    assert "# allow:" in found[0][1]


# directive: path-class-perfection | # see path.C22
def test_gate_ignores_annotation_outside_string():
    good = (
        'QUERY = (\n'
        '    "SELECT id, name "  # allow: R12 -- legitimate line-level override\n'
        '    "FROM mytable"\n'
        ')\n'
    )
    found = find_sql_string_annotations(good)
    assert len(found) == 0, f"false positive on out-of-string annotation: {found}"


# directive: path-class-perfection | # see path.C22
def test_gate_ignores_non_sql_string_with_annotation():
    good = '''MSG = "# allow: this is a literal message about allow syntax, not SQL"\n'''
    found = find_sql_string_annotations(good)
    assert len(found) == 0, f"false positive on non-SQL string: {found}"
