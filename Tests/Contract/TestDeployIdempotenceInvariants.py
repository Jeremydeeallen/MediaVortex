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


class TestDeterministicWorkerIdentity(unittest.TestCase):
    """WorkerName is deploy-assigned. Runtime slot-claim + advisory locks + prefix env + hostname fallback are retired. See .claude/rules/claim-authority.md#worker-identity-is-deterministic-deploy-assigned."""

    def test_claim_prefixed_worker_name_retired(self):
        for Py in WORKER_SERVICE.rglob('*.py'):
            Src = Py.read_text(encoding='utf-8', errors='replace')
            self.assertNotIn(
                '_ClaimPrefixedWorkerName', Src,
                f'{Py.relative_to(REPO_ROOT)}: _ClaimPrefixedWorkerName must be deleted; identity is deploy-assigned via MEDIAVORTEX_WORKER_NAME.',
            )

    def test_prefix_env_retired(self):
        for Root in (WORKER_SERVICE, DEPLOY_DIR):
            for Path_ in Root.rglob('*'):
                if not Path_.is_file():
                    continue
                if Path_.suffix.lower() not in ('.py', '.service', '.yml', '.env', '.template'):
                    continue
                Src = Path_.read_text(encoding='utf-8', errors='replace')
                self.assertNotIn(
                    'MEDIAVORTEX_WORKER_PREFIX', Src,
                    f'{Path_.relative_to(REPO_ROOT)}: MEDIAVORTEX_WORKER_PREFIX must be retired; systemd EnvironmentFile=/etc/mediavortex/instance-%i.env sets MEDIAVORTEX_WORKER_NAME.',
                )

    def test_worker_prefix_env_write_retired(self):
        for Py in DEPLOY_DIR.rglob('*.py'):
            Src = Py.read_text(encoding='utf-8', errors='replace')
            self.assertNotIn(
                'worker-prefix.env', Src.replace("rm -f /etc/mediavortex/worker-prefix.env", ""),
                f'{Py.relative_to(REPO_ROOT)}: worker-prefix.env write must be retired (rm -f cleanup is allowed).',
            )

    def test_age_slot_heartbeats_retired(self):
        for Py in DEPLOY_DIR.rglob('*.py'):
            Src = Py.read_text(encoding='utf-8', errors='replace')
            self.assertNotIn(
                'StepAgeSlotHeartbeats', Src,
                f'{Py.relative_to(REPO_ROOT)}: StepAgeSlotHeartbeats must be retired; deterministic identity removes need to age slots.',
            )

    def test_worker_service_has_no_hostname_fallback(self):
        Src = (WORKER_SERVICE / 'Main.py').read_text(encoding='utf-8')
        self.assertNotIn(
            'socket.gethostname', Src,
            'WorkerService/Main.py must not fall back to socket.gethostname(); MEDIAVORTEX_WORKER_NAME is the sole source. See .claude/rules/claim-authority.md.',
        )

    def test_resolve_worker_name_fail_louds_on_missing_env(self):
        Src = (WORKER_SERVICE / 'Main.py').read_text(encoding='utf-8')
        StartIdx = Src.find('def _ResolveWorkerName')
        self.assertGreater(StartIdx, -1, '_ResolveWorkerName not found')
        NextDef = Src.find('\n    def ', StartIdx + 1)
        Body = Src[StartIdx:NextDef if NextDef > 0 else len(Src)]
        self.assertIn('MEDIAVORTEX_WORKER_NAME', Body, 'must read MEDIAVORTEX_WORKER_NAME')
        self.assertTrue(
            re.search(r'raise\s+\w+Error', Body),
            '_ResolveWorkerName must raise on missing MEDIAVORTEX_WORKER_NAME (no fallback).',
        )

    def test_systemd_unit_uses_per_instance_env_file(self):
        Unit = (DEPLOY_DIR / 'baremetal' / 'mediavortex-worker@.service').read_text(encoding='utf-8')
        self.assertIn(
            'EnvironmentFile=/etc/mediavortex/instance-%i.env', Unit,
            'systemd unit must load per-instance env file so MEDIAVORTEX_WORKER_NAME is set per systemd instance.',
        )


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


class TestDeployHistoryRecorded(unittest.TestCase):
    # see worker-deploy.C19

    def test_fleet_deploy_inserts_deployhistory_row(self):
        Src = (DEPLOY_DIR / 'deploy-fleet.py').read_text(encoding='utf-8')
        self.assertIn('DeployHistory', Src, 'deploy-fleet.py must write to DeployHistory')
        self.assertTrue(
            re.search(r'INSERT\s+INTO\s+DeployHistory', Src, re.IGNORECASE),
            'deploy-fleet.py must INSERT into DeployHistory at run start',
        )
        self.assertTrue(
            re.search(r'UPDATE\s+DeployHistory', Src, re.IGNORECASE),
            'deploy-fleet.py must UPDATE the DeployHistory row at run exit with CompletedAt + ElapsedSeconds',
        )
        self.assertIn('ElapsedSeconds', Src, 'exit UPDATE must set ElapsedSeconds')
        self.assertIn('Outcome', Src, 'exit UPDATE must set Outcome')

    def test_deployhistory_table_migration_exists(self):
        Migration = SCRIPTS_DIR / 'SQLScripts' / 'CreateDeployHistoryTable_2026_07_24.py'
        self.assertTrue(Migration.exists(), 'CreateDeployHistoryTable migration must exist')
        Src = Migration.read_text(encoding='utf-8')
        for Col in ('StartedAt', 'CompletedAt', 'PriorSha', 'NewSha', 'ElapsedSeconds', 'Outcome'):
            self.assertIn(Col, Src, f'DeployHistory schema must define {Col}')


if __name__ == '__main__':
    unittest.main()
