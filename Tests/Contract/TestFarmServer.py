import ast
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from flask import Flask

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from Core.CodeVersion import ResolveCodeVersion
from Core.Database.DatabaseService import DatabaseService
from deploy.common import LoadBaremetalDeployModule

TestServiceName = 'ContractTestWebService'


# directive: farm-server | # see worker-deploy-baremetal.S7
class TestHostRoles(unittest.TestCase):

    @classmethod
    # directive: farm-server | # see worker-deploy-baremetal.S7
    def setUpClass(cls):
        cls.Mod = LoadBaremetalDeployModule()
        cls.Sha = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=str(REPO_ROOT),
                                 capture_output=True, text=True, check=True).stdout.strip()

    # directive: farm-server | # see worker-deploy-baremetal.ST3
    def test_fingerprint_is_stable_per_sha_and_differs_by_role(self):
        Worker = self.Mod.Roles['worker']['Requirements']
        Server = self.Mod.Roles['server']['Requirements']
        First = self.Mod._ComputeDepsFingerprint('cpu', self.Sha, Worker)
        self.assertEqual(First, self.Mod._ComputeDepsFingerprint('cpu', self.Sha, Worker))
        self.assertNotEqual(First, self.Mod._ComputeDepsFingerprint('cpu', self.Sha, Server))

    # directive: farm-server | # see worker-deploy-baremetal.S7
    def test_server_role_runs_webservice_under_its_own_identity(self):
        Role = self.Mod.Roles['server']
        Body = Role['UnitBody']('/opt/mediavortex/src-abc', '/opt/mediavortex/host-venv-def', '6G')
        self.assertIn('ExecStart=/opt/mediavortex/host-venv-def/bin/python /opt/mediavortex/src-abc/WebService/Main.py', Body)
        self.assertIn('WorkingDirectory=/opt/mediavortex/src-abc', Body)
        self.assertIn('EnvironmentFile=/etc/mediavortex/server.env', Body)
        self.assertIn('Restart=always', Body)
        self.assertEqual(Role['IdentityFiles']('mediavortex-server', 4),
                         {'server.env': 'MEDIAVORTEX_WORKER_NAME=mediavortex-server'})
        self.assertEqual(Role['Units'](4), ['mediavortex-server.service'])


# directive: farm-server | # see startup.S5
class TestCodeVersion(unittest.TestCase):

    # directive: farm-server | # see startup.S5
    def test_deployed_tree_reports_version_file(self):
        with tempfile.TemporaryDirectory() as Tmp:
            (Path(Tmp) / 'VERSION').write_text('a' * 40, encoding='utf-8')
            self.assertEqual(ResolveCodeVersion(Tmp), ('a' * 40, None))

    # directive: farm-server | # see startup.S5
    def test_git_checkout_reports_head_over_version_file(self):
        with tempfile.TemporaryDirectory() as Tmp:
            (Path(Tmp) / 'VERSION').write_text('a' * 40, encoding='utf-8')
            (Path(Tmp) / '.git' / 'refs' / 'heads').mkdir(parents=True)
            (Path(Tmp) / '.git' / 'HEAD').write_text('ref: refs/heads/main\n', encoding='utf-8')
            (Path(Tmp) / '.git' / 'refs' / 'heads' / 'main').write_text('b' * 40 + '\n', encoding='utf-8')
            self.assertEqual(ResolveCodeVersion(Tmp)[0], 'b' * 40)

    # directive: farm-server | # see startup.S5
    def test_tree_without_either_reports_unknown(self):
        with tempfile.TemporaryDirectory() as Tmp:
            self.assertEqual(ResolveCodeVersion(Tmp), ('unknown', None))

    # directive: farm-server | # see startup.S5
    def test_version_route_reports_configured_sha(self):
        from Features.ServiceControl.ServiceStatusController import ServiceStatusBlueprint
        App = Flask(__name__)
        App.config['CodeSha'] = 'c' * 40
        App.config['InstanceName'] = TestServiceName
        App.register_blueprint(ServiceStatusBlueprint, url_prefix='/api')
        Response = App.test_client().get('/api/Version')
        self.assertEqual(Response.status_code, 200)
        Body = Response.get_json()
        self.assertTrue(Body['Success'])
        self.assertEqual(Body['Data'], {'Sha': 'c' * 40, 'Instance': TestServiceName})


# directive: farm-server | # see single-instance-startup.C7
class TestCrossHostSingleInstance(unittest.TestCase):

    # directive: farm-server | # see single-instance-startup.C7
    def setUp(self):
        from Features.ServiceControl.ServiceStatusService import ServiceStatusService
        self.Db = DatabaseService()
        self.Db.ExecuteNonQuery("DELETE FROM ServiceStatus WHERE ServiceName = %s", (TestServiceName,))
        self.Service = ServiceStatusService()

    # directive: farm-server | # see single-instance-startup.C7
    def tearDown(self):
        self.Db.ExecuteNonQuery("DELETE FROM ServiceStatus WHERE ServiceName = %s", (TestServiceName,))

    # directive: farm-server | # see single-instance-startup.C7
    def _Owner(self):
        return self.Db.ExecuteQuery("SELECT InstanceName FROM ServiceStatus WHERE ServiceName = %s", (TestServiceName,))[0]['InstanceName']

    # directive: farm-server | # see single-instance-startup.C7
    def test_fresh_foreign_owner_refuses_and_stale_owner_is_taken_over(self):
        self.assertFalse(self.Service.RegisterServiceStartup(TestServiceName, 'contract-host-a'))
        self.assertEqual(self._Owner(), 'contract-host-a')

        self.assertTrue(self.Service.RegisterServiceStartup(TestServiceName, 'contract-host-b'))
        self.assertEqual(self._Owner(), 'contract-host-a')

        self.Db.ExecuteNonQuery(
            "UPDATE ServiceStatus SET UpdatedAt = NOW() - INTERVAL '5 minutes' WHERE ServiceName = %s",
            (TestServiceName,))
        self.assertFalse(self.Service.RegisterServiceStartup(TestServiceName, 'contract-host-b'))
        self.assertEqual(self._Owner(), 'contract-host-b')


# directive: farm-server | # see single-instance-startup.C8
class TestDeployAssignedIdentity(unittest.TestCase):

    # directive: farm-server | # see startup.ST0
    def test_unset_identity_refuses_to_start(self):
        from WebService.Main import _ResolveInstanceName
        Saved = os.environ.pop('MEDIAVORTEX_WORKER_NAME', None)
        try:
            with self.assertRaises(RuntimeError):
                _ResolveInstanceName()
            os.environ['MEDIAVORTEX_WORKER_NAME'] = ' mediavortex-server '
            self.assertEqual(_ResolveInstanceName(), 'mediavortex-server')
        finally:
            os.environ.pop('MEDIAVORTEX_WORKER_NAME', None)
            if Saved is not None:
                os.environ['MEDIAVORTEX_WORKER_NAME'] = Saved

    # directive: farm-server | # see single-instance-startup.C8
    def test_dev_launcher_starts_no_webservice(self):
        Tree = ast.parse((REPO_ROOT / 'StartMediaVortex.py').read_text(encoding='utf-8'))
        Names = []
        for Node in Tree.body:
            if isinstance(Node, ast.Assign) and any(getattr(T, 'id', None) == 'Services' for T in Node.targets):
                Names = [ast.literal_eval(E.values[[K.value for K in E.keys].index('Name')]) for E in Node.value.elts]
        self.assertEqual(Names, ['WorkerService'])

    # directive: farm-server | # see startup.S6
    def test_server_instance_resolves_storage_roots(self):
        Rows = DatabaseService().ExecuteQuery(
            "SELECT COUNT(*) AS N FROM StorageRootResolutions WHERE WorkerName = %s AND IsActive", ('mediavortex-server',))
        self.assertGreaterEqual(Rows[0]['N'], 3)


if __name__ == '__main__':
    unittest.main()
