import json
import unittest
import urllib.request
import urllib.error


_BASE = 'http://127.0.0.1:5000'


# directive: activity-admin-and-worker-telemetry
def _Get(Path, AllowRedirects=True):
    Req = urllib.request.Request(_BASE + Path, method='GET')
    try:
        opener = urllib.request.build_opener() if AllowRedirects else urllib.request.build_opener(urllib.request.HTTPRedirectHandler() if AllowRedirects else _NoRedirect())
        with opener.open(Req, timeout=5) as Resp:
            Body = Resp.read()
            try:
                return Resp.status, json.loads(Body), dict(Resp.headers)
            except Exception:
                return Resp.status, Body.decode('utf-8', errors='replace'), dict(Resp.headers)
    except urllib.error.HTTPError as Ex:
        return Ex.code, Ex.read(), dict(Ex.headers)


# directive: activity-admin-and-worker-telemetry
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def http_error_301(self, req, fp, code, msg, headers):
        return fp
    http_error_302 = http_error_303 = http_error_307 = http_error_301


# directive: activity-admin-and-worker-telemetry
def _GetNoRedirect(Path):
    Opener = urllib.request.build_opener(_NoRedirect)
    Req = urllib.request.Request(_BASE + Path, method='GET')
    Resp = Opener.open(Req, timeout=5)
    return Resp.status, dict(Resp.headers)


# directive: activity-admin-and-worker-telemetry
class TestAdminComplianceEndpoint(unittest.TestCase):

    # directive: activity-admin-and-worker-telemetry
    def test_admin_compliance_page_renders(self):
        Status, Body, _ = _Get('/Admin/Compliance')
        self.assertEqual(Status, 200)
        self.assertIn('Compliance', Body if isinstance(Body, str) else '')

    # directive: activity-admin-and-worker-telemetry
    def test_admin_compliance_snapshot_shape(self):
        Status, Body, _ = _Get('/api/Admin/Compliance/Snapshot')
        self.assertEqual(Status, 200)
        self.assertTrue(Body.get('Success'))
        Data = Body.get('Data', {})
        for K in ('Compliance', 'Mode', 'Audio'):
            self.assertIn(K, Data, f'Data missing key: {K}')

    # directive: activity-admin-and-worker-telemetry
    def test_legacy_compliance_301_redirect(self):
        Status, Headers = _GetNoRedirect('/Compliance')
        self.assertEqual(Status, 301)
        Loc = Headers.get('Location') or Headers.get('location')
        self.assertEqual(Loc, '/Admin/Compliance')


if __name__ == '__main__':
    unittest.main()
