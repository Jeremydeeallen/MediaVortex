import os
import re
import unittest


# directive: worker-runtime-state | # see admin-workers.C7
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# directive: worker-runtime-state | # see admin-workers.C7
def _ScanPyFiles(Roots):
    for Subtree in Roots:
        Abs = _REPO_ROOT + os.sep + Subtree
        for DirName, _Dirs, Files in os.walk(Abs):
            if 'venv' in DirName or '__pycache__' in DirName:
                continue
            for F in Files:
                if not F.endswith('.py'):
                    continue
                Filename = DirName + os.sep + F
                with open(Filename, 'r', encoding='utf-8', errors='ignore') as Fh:
                    yield Filename, Fh.read()


# directive: worker-runtime-state | # see admin-workers.C7
class TestWorkerRuntimeStateAuthorship(unittest.TestCase):

    # directive: worker-runtime-state | # see admin-workers.C7
    def test_only_workerstatereporter_writes_the_three_columns(self):
        Pattern = re.compile(r"UPDATE\s+Workers\s+SET\s[^;]*?(RuntimeState|CurrentAttemptId|LastRuntimeStateUpdate)", re.IGNORECASE | re.DOTALL)
        Hits = []
        for Filename, Content in _ScanPyFiles(['Features', 'WebService']):
            for M in Pattern.finditer(Content):
                Hits.append((Filename, M.group(0)[:120]))
        if Hits:
            Lines = [f"  {F}: {Snippet}" for F, Snippet in Hits]
            self.fail("WebService / Features must NOT write the worker-truth columns. Offenders:\n" + "\n".join(Lines))
        WriterFile = _REPO_ROOT + os.sep + 'WorkerService' + os.sep + 'WorkerStateReporter.py'
        self.assertTrue(os.path.exists(WriterFile), "WorkerStateReporter.py must exist as the sole writer")
        with open(WriterFile, 'r', encoding='utf-8') as Fh:
            Content = Fh.read()
        self.assertIn('RuntimeState', Content)
        self.assertIn('CurrentAttemptId', Content)
        self.assertIn('LastRuntimeStateUpdate', Content)


if __name__ == '__main__':
    unittest.main()
