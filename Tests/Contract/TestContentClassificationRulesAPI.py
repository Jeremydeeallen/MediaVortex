# directive: tv-tier1-classifier-pin
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from flask import Flask

from Core.Database.DatabaseService import DatabaseService
from Features.ContentClassifier.ContentClassificationRulesController import ContentClassificationRulesBlueprint


_TEST_RULE_NAME = '_test-classification-rule-api'


class TestContentClassificationRulesAPI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.App = Flask(__name__)
        cls.App.register_blueprint(ContentClassificationRulesBlueprint)
        cls.Client = cls.App.test_client()
        cls.Db = DatabaseService()

    def setUp(self):
        self.Db.ExecuteNonQuery("DELETE FROM ContentClassificationRules WHERE RuleName = %s", (_TEST_RULE_NAME,))

    def tearDown(self):
        self.Db.ExecuteNonQuery("DELETE FROM ContentClassificationRules WHERE RuleName = %s", (_TEST_RULE_NAME,))

    def _NewPriority(self) -> int:
        Rows = self.Db.ExecuteQuery("SELECT COALESCE(MAX(Priority), 0) AS MaxP FROM ContentClassificationRules")
        return int(Rows[0]['MaxP']) + 100

    def test_list_returns_success(self):
        Resp = self.Client.get('/api/ContentClassification/Rules')
        self.assertEqual(Resp.status_code, 200)
        Body = Resp.get_json()
        self.assertTrue(Body['Success'])
        self.assertIsInstance(Body['Data'], list)

    def test_create_update_delete_roundtrip(self):
        Priority = self._NewPriority()
        Payload = {
            'Priority': Priority,
            'RuleName': _TEST_RULE_NAME,
            'IsActive': True,
            'AssignProfileName': 'AV1 Tier 1 Efficient',
            'FolderPathPattern': 'T:\\_test-only%',
            'Description': 'contract test row',
        }
        CreateResp = self.Client.post('/api/ContentClassification/Rules', json=Payload)
        self.assertEqual(CreateResp.status_code, 201, CreateResp.get_data(as_text=True))
        RuleId = CreateResp.get_json()['Data']['Id']

        UpdateResp = self.Client.put(f'/api/ContentClassification/Rules/{RuleId}', json={'IsActive': False, 'Description': 'updated'})
        self.assertEqual(UpdateResp.status_code, 200, UpdateResp.get_data(as_text=True))

        Row = self.Db.ExecuteQuery("SELECT IsActive, Description FROM ContentClassificationRules WHERE Id = %s", (RuleId,))[0]
        self.assertFalse(bool(Row['IsActive']))
        self.assertEqual(Row['Description'], 'updated')

        DeleteResp = self.Client.delete(f'/api/ContentClassification/Rules/{RuleId}')
        self.assertEqual(DeleteResp.status_code, 200)
        Rows = self.Db.ExecuteQuery("SELECT Id FROM ContentClassificationRules WHERE Id = %s", (RuleId,))
        self.assertEqual(Rows, [])

    def test_create_duplicate_priority_returns_409(self):
        Priority = self._NewPriority()
        First = {'Priority': Priority, 'RuleName': _TEST_RULE_NAME, 'AssignProfileName': 'AV1 Tier 1 Efficient'}
        R1 = self.Client.post('/api/ContentClassification/Rules', json=First)
        self.assertEqual(R1.status_code, 201)
        Second = {'Priority': Priority, 'RuleName': _TEST_RULE_NAME + '_dup', 'AssignProfileName': 'AV1 Tier 2 Good'}
        R2 = self.Client.post('/api/ContentClassification/Rules', json=Second)
        self.assertEqual(R2.status_code, 409)


if __name__ == '__main__':
    unittest.main()
