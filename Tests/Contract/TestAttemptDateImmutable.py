# directive: e2e-bug-fixes | # see e2e-bug-fixes.C32
import re
import unittest
from pathlib import Path as _PyPath


_REPO = _PyPath(__file__).resolve().parents[2]

_SANCTIONED_INSERT_FILES = {
    _REPO / 'Features' / 'TranscodeJob' / 'TranscodeJobRepository.py',
    _REPO / 'Core' / 'Models' / 'TranscodeAttemptModel.py',
    _REPO / 'Features' / 'TranscodeJob' / 'ProcessTranscodeQueueService.py',
    _REPO / 'Features' / 'TranscodeJob' / 'Worker' / 'AttemptRecordService.py',
}

_FORBIDDEN_PATTERNS = [
    re.compile(r"'AttemptDate'\s*:\s*datetime\."),
    re.compile(r"'AttemptDate'\s*:\s*NOW"),
    re.compile(r"(?<![A-Za-z])AttemptDate\s*=\s*NOW", re.IGNORECASE),
    re.compile(r"(?<![A-Za-z])AttemptDate\s*=\s*%s"),
    re.compile(r"SET\s+AttemptDate\b", re.IGNORECASE),
]


class TestAttemptDateImmutable(unittest.TestCase):

    def test_no_attemptdate_writes_outside_sanctioned_files(self):
        Roots = [_REPO / 'Features', _REPO / 'Core', _REPO / 'Repositories',
                 _REPO / 'Services', _REPO / 'WorkerService', _REPO / 'WebService']
        Violations = []
        for Root in Roots:
            if not Root.exists():
                continue
            for Py in Root.rglob('*.py'):
                if Py in _SANCTIONED_INSERT_FILES:
                    continue
                try:
                    Source = Py.read_text(encoding='utf-8')
                except Exception:
                    continue
                for Pattern in _FORBIDDEN_PATTERNS:
                    for Match in Pattern.finditer(Source):
                        LineNo = Source[:Match.start()].count('\n') + 1
                        Violations.append(f"{Py.relative_to(_REPO)}:{LineNo}  '{Match.group(0)}'")
        self.assertEqual(Violations, [],
            "AttemptDate is IMMUTABLE after CreateTranscodeAttempt (e2e-bug-fixes.C32). "
            "The following write-sites violate the invariant:\n  " + "\n  ".join(Violations))

    def test_sanctioned_files_still_contain_insert_or_post_init(self):
        Repo = (_REPO / 'Features' / 'TranscodeJob' / 'TranscodeJobRepository.py').read_text(encoding='utf-8')
        self.assertIn('INSERT INTO TranscodeAttempts', Repo,
            "TranscodeJobRepository must retain the sanctioned INSERT path")
        self.assertIn('AttemptDate', Repo,
            "TranscodeJobRepository INSERT must set AttemptDate")

        Model = (_REPO / 'Core' / 'Models' / 'TranscodeAttemptModel.py').read_text(encoding='utf-8')
        self.assertIn('self.AttemptDate = datetime.now', Model,
            "TranscodeAttemptModel.__post_init__ must default AttemptDate")

    def test_updatetranscodeattempt_refuses_attemptdate(self):
        Repo = (_REPO / 'Features' / 'TranscodeJob' / 'TranscodeJobRepository.py').read_text(encoding='utf-8')
        self.assertIn("if 'AttemptDate' in Updates:", Repo,
            "UpdateTranscodeAttempt must fail-loud when caller passes AttemptDate")
        self.assertIn('AttemptDate is immutable', Repo,
            "Guard raise-message must name the invariant")


if __name__ == '__main__':
    unittest.main()
