"""Smoke tests for r12-edited-region-only directive.

Drives `.claude/hooks/pre-edit-standards.ps1` with synthetic tool inputs and
checks whether R12 allow/deny matches expected outcomes per the directive's
acceptance criteria. Faster than the PowerShell test runner because subprocess
management is cheaper in Python.

Run from repo root:
    py .claude/hooks/tests/smoke_r12_edit_region.py
Exit 0 = all pass. Exit 1 = at least one fail.
"""

import json
import os
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
HOOK = os.path.join(REPO_ROOT, '.claude', 'hooks', 'pre-edit-standards.ps1')

TARGET_WITH_VIOLATIONS = '''\
"""Module-level docstring.

Spans multiple lines.
"""

from typing import List


def Foo():
    """First docstring.

    With multiple lines.
    Three lines total.
    """
    return 1


def Bar():
    """Second function with single-line docstring."""
    return 2
'''

TARGET_CLEAN = '''\
from typing import List


def Foo():
    return 1


def Bar():
    return 2
'''


def invoke_hook(tool_name, tool_input):
    payload = json.dumps({
        'tool_name': tool_name,
        'tool_input': tool_input,
        'transcript_path': '',
    })
    proc = subprocess.run(
        ['powershell.exe', '-NoProfile', '-File', HOOK],
        input=payload,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=20,
    )
    return proc.stdout.strip(), proc.returncode


def is_deny(out):
    return '"permissionDecision":"deny"' in out.replace(' ', '')


def write_target(content):
    fd, path = tempfile.mkstemp(suffix='.py')
    with os.fdopen(fd, 'w', encoding='utf-8', newline='') as f:
        f.write(content)
    return path


def main():
    target = write_target(TARGET_WITH_VIOLATIONS)
    clean = write_target(TARGET_CLEAN)

    tests = []

    def run(name, expected, tool_name, tool_input):
        try:
            out, rc = invoke_hook(tool_name, tool_input)
            actual = 'DENY' if is_deny(out) else 'ALLOW'
            ok = actual == expected
            tests.append((name, expected, actual, ok, out))
            tag = 'PASS' if ok else 'FAIL'
            print(f'  [{tag}] {name} -> expected {expected}, got {actual}')
            if not ok and out:
                print(f'         hook output: {out[:300]}')
        except Exception as e:
            tests.append((name, expected, 'ERROR', False, str(e)))
            print(f'  [ERROR] {name}: {e}')

    # C1: Edit outside violation region -> ALLOW
    run('C1 Edit outside region (preexisting docstrings untouched)',
        'ALLOW', 'Edit', {
            'file_path': target,
            'old_string': 'from typing import List',
            'new_string': 'from typing import List, Optional',
        })

    # C2a: Edit adds NEW multi-line docstring -> DENY
    run('C2a Edit introduces new multi-line docstring',
        'DENY', 'Edit', {
            'file_path': clean,
            'old_string': 'def Bar():\n    return 2',
            'new_string': 'def Bar():\n    return 2\n\n\ndef Baz():\n    """New function\n    with multi-line docstring.\n    """\n    return 3',
        })

    # C2b: Edit whose new_string keeps a multi-line docstring in its region -> DENY
    run('C2b Edit new_string covers preexisting multi-line docstring',
        'DENY', 'Edit', {
            'file_path': target,
            'old_string': 'def Foo():\n    """First docstring.\n\n    With multiple lines.\n    Three lines total.\n    """\n    return 1',
            'new_string': 'def Foo():\n    """First docstring.\n\n    With multiple lines.\n    Three lines total.\n    """\n    return 99',
        })

    # C3: Write whole file with preexisting violations -> DENY
    run('C3 Write whole file containing multi-line docstring',
        'DENY', 'Write', {
            'file_path': target,
            'content': TARGET_WITH_VIOLATIONS,
        })

    # C4a: MultiEdit, all edits outside violation regions -> ALLOW
    run('C4a MultiEdit union misses preexisting violations',
        'ALLOW', 'MultiEdit', {
            'file_path': target,
            'edits': [
                {'old_string': 'from typing import List', 'new_string': 'from typing import List, Dict'},
                {'old_string': 'return 2', 'new_string': 'return 22'},
            ],
        })

    # C4b: MultiEdit, one edit covers a violation -> DENY
    run('C4b MultiEdit union covers preexisting multi-line docstring',
        'DENY', 'MultiEdit', {
            'file_path': target,
            'edits': [
                {'old_string': 'from typing import List', 'new_string': 'from typing import List, Dict'},
                {'old_string': 'def Foo():\n    """First docstring.\n\n    With multiple lines.\n    Three lines total.\n    """\n    return 1',
                 'new_string': 'def Foo():\n    """First docstring.\n\n    With multiple lines.\n    Three lines total.\n    """\n    return 1000'},
            ],
        })

    # C5a: Edit introduces multi-line # comment block -> DENY
    run('C5a Edit introduces multi-line # comment block',
        'DENY', 'Edit', {
            'file_path': clean,
            'old_string': 'def Bar():\n    return 2',
            'new_string': '# First comment line\n# Second comment line\ndef Bar():\n    return 2',
        })

    # C5b: Edit introduces triple-quoted SQL -> DENY
    run('C5b Edit introduces triple-quoted SQL',
        'DENY', 'Edit', {
            'file_path': clean,
            'old_string': 'def Bar():\n    return 2',
            'new_string': 'def Bar():\n    Query = """\n        SELECT Id FROM MediaFiles\n        WHERE Foo = %s\n        """\n    return 2',
        })

    # C5c: Edit introduces module-level docstring at file start -> DENY
    run('C5c Edit introduces module-level docstring',
        'DENY', 'Edit', {
            'file_path': clean,
            'old_string': 'from typing import List',
            'new_string': '"""Module docstring.\n\nSecond line.\n"""\n\nfrom typing import List',
        })

    # C6: # allow: override inside edit region -> ALLOW
    run('C6 Edit adds violation with # allow: override',
        'ALLOW', 'Edit', {
            'file_path': clean,
            'old_string': 'def Bar():\n    return 2',
            'new_string': '# allow: R12 smoke-test override\ndef Bar():\n    """Multi-line\n    docstring.\n    """\n    return 2',
        })

    # Bonus: pure deletion of preexisting violation -> ALLOW (NoRegion)
    run('Bonus Pure deletion of preexisting multi-line docstring',
        'ALLOW', 'Edit', {
            'file_path': target,
            'old_string': '    """First docstring.\n\n    With multiple lines.\n    Three lines total.\n    """\n',
            'new_string': '',
        })

    os.unlink(target)
    os.unlink(clean)

    fails = [t for t in tests if not t[3]]
    print()
    print(f'Ran {len(tests)} tests. Failures: {len(fails)}')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
