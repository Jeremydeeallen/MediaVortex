import json
import unittest

import urllib.request
import urllib.error

from Core.Database.DatabaseService import DatabaseService


_BASE = 'http://127.0.0.1:5000'


# directive: compliance-symmetry
def _Post(Path, Body=None):
    Url = _BASE + Path
    Data = json.dumps(Body or {}).encode('utf-8')
    Req = urllib.request.Request(Url, data=Data, method='POST',
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(Req, timeout=5) as Resp:
            return Resp.status, json.loads(Resp.read())
    except urllib.error.HTTPError as Ex:
        return Ex.code, json.loads(Ex.read())


# directive: compliance-symmetry
def _Patch(Path, Body):
    Url = _BASE + Path
    Data = json.dumps(Body).encode('utf-8')
    Req = urllib.request.Request(Url, data=Data, method='PATCH',
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(Req, timeout=5) as Resp:
            return Resp.status, json.loads(Resp.read())
    except urllib.error.HTTPError as Ex:
        return Ex.code, json.loads(Ex.read())


# directive: compliance-symmetry
class TestProfileLifecycle(unittest.TestCase):

    # directive: compliance-symmetry
    @classmethod
    def setUpClass(cls):
        cls.Db = DatabaseService()
        cls.PreMigId = cls._FetchId('_PreMigrationDefault')

    # directive: compliance-symmetry
    @classmethod
    def _FetchId(cls, Name):
        Rows = cls.Db.ExecuteQuery("SELECT Id FROM Profiles WHERE ProfileName = %s", (Name,))
        return Rows[0]['id'] if Rows else None

    # directive: compliance-symmetry
    def test_patch_compliance_field_on_finalized_returns_400(self):
        self.assertIsNotNone(self.PreMigId)
        Status, Body = _Patch(f'/api/profiles/{self.PreMigId}/knobs',
                              {'Profile': {'TargetVideoKbps': 9999}})
        self.assertEqual(Status, 400, f'Expected 400; got {Status} body={Body}')
        self.assertIn('Finalized', Body.get('error', '') + Body.get('message', ''))

    # directive: compliance-symmetry
    def test_copy_draft_creates_editable_clone(self):
        self.assertIsNotNone(self.PreMigId)
        Status, Body = _Post(f'/api/profiles/{self.PreMigId}/copy-draft')
        self.assertEqual(Status, 200, f'copy-draft expected 200; got {Status} body={Body}')
        self.assertTrue(Body.get('success'))
        NewId = Body.get('new_profile_id')
        self.assertIsNotNone(NewId)
        try:
            Rows = self.Db.ExecuteQuery("SELECT Draft, StreamCodecName FROM Profiles WHERE Id = %s", (NewId,))
            self.assertEqual(len(Rows), 1)
            self.assertTrue(Rows[0]['draft'])
            self.assertEqual(Rows[0]['streamcodecname'], 'av1')
            PatchStatus, _ = _Patch(f'/api/profiles/{NewId}/knobs',
                                    {'Profile': {'TargetVideoKbps': 2000}})
            self.assertEqual(PatchStatus, 200, 'Draft profile should accept compliance edits')
        finally:
            self.Db.ExecuteNonQuery("DELETE FROM Profiles WHERE Id = %s", (NewId,))

    # directive: compliance-symmetry
    def test_finalize_already_finalized_returns_400(self):
        Status, Body = _Post(f'/api/profiles/{self.PreMigId}/finalize')
        self.assertEqual(Status, 400)
        self.assertIn('already Finalized', Body.get('error', ''))


if __name__ == '__main__':
    unittest.main()
