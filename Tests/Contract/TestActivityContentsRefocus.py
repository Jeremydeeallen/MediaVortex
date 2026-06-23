import unittest
from pathlib import Path


_REPO = Path(__file__).resolve().parents[2]


# directive: activity-admin-and-worker-telemetry
class TestActivityContentsRefocus(unittest.TestCase):

    # directive: activity-admin-and-worker-telemetry
    def test_no_worker_widget_markup(self):
        Source = (_REPO / 'Templates' / 'Activity.html').read_text(encoding='utf-8')
        Forbidden = ['WorkersMount', 'VersionMismatchBanner', 'WorkerSettingsModal',
                     'WorkerStatusMap', 'SetAllWorkersStatus', 'GetWorkerStatusBadge',
                     'ShowDisabledToggle', 'OpenWorkerSettings']
        for Token in Forbidden:
            self.assertNotIn(Token, Source, f"Activity.html still contains worker widget token: {Token}")

    # directive: activity-admin-and-worker-telemetry
    def test_no_compliance_widget_markup(self):
        Source = (_REPO / 'Templates' / 'Activity.html').read_text(encoding='utf-8')
        Forbidden = ['ComplianceContainer', 'AudioVerticalHealthBody', 'AudioConsistencyBody',
                     'AudioNormAdmitted', 'LoudnessMeasured', 'ComplianceTotal']
        for Token in Forbidden:
            self.assertNotIn(Token, Source, f"Activity.html still contains compliance widget token: {Token}")

    # directive: activity-admin-and-worker-telemetry
    def test_activity_template_is_focused(self):
        Source = (_REPO / 'Templates' / 'Activity.html').read_text(encoding='utf-8')
        self.assertLess(len(Source.splitlines()), 200,
                        "Activity.html should be a focused template (<200 lines) after refocus")
        self.assertIn('ActiveJobsBody', Source, 'Active jobs body must remain')
        self.assertIn('ActiveScansBody', Source, 'Active scans body must remain')


if __name__ == '__main__':
    unittest.main()
