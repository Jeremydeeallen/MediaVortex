# directive: deploy-worker-identity-invariants | # see worker-deploy.C15
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEPLOY_DIR = REPO_ROOT / 'deploy'
SCRIPTS_DIR = REPO_ROOT / 'Scripts'
FEATURES_DIR = REPO_ROOT / 'Features'
WORKER_SERVICE = REPO_ROOT / 'WorkerService'

OPERATOR_OWNED_COLUMNS = (
    'Status',
    'TranscodeEnabled',
    'RemuxEnabled',
    'QualityTestEnabled',
    'ScanEnabled',
    'MaxConcurrentJobs',
    'MaxConcurrentQualityTestJobs',
    'MaxCpuThreads',
    'AcceptsInterlaced',
    'ForceDisposition',
)


class TestNoDestructiveDeleteOnWorkers(unittest.TestCase):
    # see worker-deploy.C15

    def test_no_delete_from_workers_in_deploy(self):
        Hits = []
        for Py in DEPLOY_DIR.rglob('*.py'):
            Text = Py.read_text(encoding='utf-8', errors='replace')
            for LineNo, Line in enumerate(Text.splitlines(), start=1):
                if re.search(r'DELETE\s+FROM\s+Workers', Line, re.IGNORECASE):
                    Hits.append(f'{Py.relative_to(REPO_ROOT)}:{LineNo}: {Line.strip()}')
        self.assertFalse(
            Hits,
            'Deploy scripts must not DELETE FROM Workers. Per DOMAIN.md 2026-07-24 + worker-deploy.C15, '
            'deploy is idempotent and preserves operator state. Hits: ' + '; '.join(Hits),
        )


class TestNoStatusCoalesceInDeploy(unittest.TestCase):
    # see worker-deploy.C16

    def test_no_coalesce_status_to_online(self):
        Hits = []
        for Py in DEPLOY_DIR.rglob('*.py'):
            Text = Py.read_text(encoding='utf-8', errors='replace')
            for LineNo, Line in enumerate(Text.splitlines(), start=1):
                if re.search(r"COALESCE\s*\(\s*Status\s*,\s*['\"]Online['\"]\s*\)", Line, re.IGNORECASE):
                    Hits.append(f'{Py.relative_to(REPO_ROOT)}:{LineNo}: {Line.strip()}')
        self.assertFalse(
            Hits,
            "Deploy scripts must not default missing Status to 'Online'. Per DOMAIN.md 2026-07-24 + "
            'worker-deploy.C16, a NULL Status is a fail-loud condition. Hits: ' + '; '.join(Hits),
        )


class TestClaimPrefixedWorkerNameAtomicReserve(unittest.TestCase):
    # see worker-deploy.C17

    def test_insert_or_update_inside_advisory_lock_scope(self):
        Src = (WORKER_SERVICE / 'Main.py').read_text(encoding='utf-8')
        StartIdx = Src.find('def _ClaimPrefixedWorkerName')
        self.assertGreater(StartIdx, -1, '_ClaimPrefixedWorkerName not found')
        NextDef = Src.find('\n    def ', StartIdx + 1)
        Body = Src[StartIdx:NextDef if NextDef > 0 else len(Src)]
        self.assertIn('pg_advisory_lock', Body, 'must acquire advisory lock')
        self.assertIn('pg_advisory_unlock', Body, 'must release advisory lock')
        self.assertTrue(
            re.search(r'INSERT\s+INTO\s+Workers', Body, re.IGNORECASE),
            'must INSERT into Workers within the claim so slot is reserved before returning',
        )
        LockIdx = Body.find('pg_advisory_lock')
        UnlockIdx = Body.find('pg_advisory_unlock')
        InsertIdx = re.search(r'INSERT\s+INTO\s+Workers', Body, re.IGNORECASE).start()
        self.assertLess(LockIdx, InsertIdx, 'INSERT must be inside lock scope (after acquire)')
        self.assertLess(InsertIdx, UnlockIdx, 'INSERT must be inside lock scope (before release)')


class TestRegisterWorkerUpsertOperatorColumns(unittest.TestCase):
    # see worker-deploy.C18

    def test_upsert_does_not_touch_operator_owned_columns(self):
        Repo = REPO_ROOT / 'Features' / 'Workers' / 'WorkersRepository.py'
        Src = Repo.read_text(encoding='utf-8')
        MarkerIdx = Src.find('def RegisterWorker')
        self.assertGreater(MarkerIdx, -1, 'RegisterWorker not found')
        NextDef = Src.find('\n    def ', MarkerIdx + 1)
        Body = Src[MarkerIdx:NextDef if NextDef > 0 else len(Src)]
        UpdateMatch = re.search(r'ON\s+CONFLICT.*?DO\s+UPDATE\s+SET(.+?)(?:WHERE|"""|$)', Body, re.IGNORECASE | re.DOTALL)
        self.assertIsNotNone(UpdateMatch, 'ON CONFLICT DO UPDATE SET clause not found in RegisterWorker')
        UpdateClause = UpdateMatch.group(1)
        Violations = []
        for Col in OPERATOR_OWNED_COLUMNS:
            if re.search(rf'\b{Col}\s*=', UpdateClause, re.IGNORECASE):
                Violations.append(Col)
        self.assertFalse(
            Violations,
            'RegisterWorker ON CONFLICT DO UPDATE must not touch operator-owned columns: ' + ', '.join(Violations),
        )


if __name__ == '__main__':
    unittest.main()
