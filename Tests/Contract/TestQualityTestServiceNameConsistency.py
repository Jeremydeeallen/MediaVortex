import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# directive: transcode-flow-canonical
PRODUCTION_ROOTS = ('Features', 'Workers', 'WorkerService', 'WebService', 'Repositories', 'Core', 'Composition', 'Services')


# directive: transcode-flow-canonical
CANONICAL_SERVICE_NAME = 'QualityTestService'


# directive: transcode-flow-canonical
WRONG_ACTIVEJOBS_LITERALS = (
    "'QualityTestingService'",
    '"QualityTestingService"',
    "'QualityTest'",
    '"QualityTest"',
)


# directive: transcode-flow-canonical
WHITELIST_PATH_SUBSTRINGS = (
    'SystemSettings\\SystemSettingsRepository.py',
    'SystemSettings/SystemSettingsRepository.py',
    'GracefulStopService.py',
    'FailureTracking\\FailureTrackingController.py',
    'FailureTracking/FailureTrackingController.py',
)


# directive: transcode-flow-canonical
def _EnumeratePythonFiles():
    Files = []
    for Root in PRODUCTION_ROOTS:
        Base = REPO_ROOT / Root
        if not Base.exists():
            continue
        for P in Base.rglob('*.py'):
            Files.append(P)
    return Files


# directive: transcode-flow-canonical
def _IsWhitelisted(FileRelPath: str) -> bool:
    for Sub in WHITELIST_PATH_SUBSTRINGS:
        if Sub in FileRelPath:
            return True
    return False


# directive: transcode-flow-canonical
class TestQualityTestServiceNameConsistency(unittest.TestCase):

    def test_no_wrong_service_name_literals_in_activejobs_contexts(self):
        Offenders = []
        for File in _EnumeratePythonFiles():
            Rel = str(File.relative_to(REPO_ROOT))
            if _IsWhitelisted(Rel):
                continue
            try:
                Source = File.read_text(encoding='utf-8')
            except Exception:
                continue
            if 'ActiveJobs' not in Source and 'activejobs' not in Source:
                continue
            for Bad in WRONG_ACTIVEJOBS_LITERALS:
                if Bad in Source:
                    for LineNo, Line in enumerate(Source.splitlines(), start=1):
                        if Bad in Line and ('ActiveJobs' in Line or 'activejobs' in Line or 'ServiceName' in Line):
                            Offenders.append(f'{Rel}:{LineNo}: {Line.strip()[:120]}')
        self.assertEqual(
            [], Offenders,
            f'QT ActiveJobs ServiceName must be {CANONICAL_SERVICE_NAME!r}. Offenders:\n  ' + '\n  '.join(Offenders),
        )

    def test_getrunningqualitytestprogress_has_status_filter(self):
        Path_ = REPO_ROOT / 'Features' / 'QualityTesting' / 'QualityTestRepository.py'
        Source = Path_.read_text(encoding='utf-8')
        Match = re.search(
            r"def\s+GetRunningQualityTestProgress\s*\(.*?\n(?:.*?\n){2,200}?\s*return\s+Results",
            Source, re.DOTALL,
        )
        self.assertIsNotNone(Match, 'GetRunningQualityTestProgress function body not found')
        Body = Match.group(0)
        self.assertIn(
            "aj.Status", Body,
            'GetRunningQualityTestProgress must gate on aj.Status to avoid surfacing Completed rows.',
        )
        self.assertRegex(
            Body, r"Status\s+IN\s*\(\s*'Running'",
            "GetRunningQualityTestProgress must filter aj.Status IN ('Running', ...).",
        )


if __name__ == '__main__':
    unittest.main()
