import json
from pathlib import Path
import re
import tempfile
from threading import Thread
import unittest
import urllib.error
import urllib.request

from finance_agent.server import LocalServer
from test_core import ROOT, demo


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(dir=ROOT / "data")
        self.server = LocalServer(0, Path(self.folder.name) / "http.sqlite")
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = self.server.origin
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.folder.cleanup()

    def request(self, path, body=None, headers=None):
        headers = dict(headers or {})
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.url + path, data=None if body is None else json.dumps(body).encode(), headers=headers)
        try:
            with self.opener.open(request, timeout=5) as response:
                return response.status, response.read(), response.headers
        except urllib.error.HTTPError as response:
            with response:
                return response.code, response.read(), response.headers

    def test_csrf_origin_host_and_path_protection(self):
        body = {"data": demo(), "version": 0, "actor": "合成测试", "reason": "HTTP验收"}
        self.assertEqual(self.request("/api/save", body)[0], 403)
        headers = {"X-FPA-CSRF": self.server.csrf, "Origin": "https://external.invalid"}
        self.assertEqual(self.request("/api/save", body, headers)[0], 403)
        self.assertEqual(self.request("/api/state", headers={"Host": "evil.invalid"})[0], 403)
        self.assertEqual(self.request("/../examples/demo.json")[0], 404)
        self.assertEqual(json.loads(self.request("/api/state")[1])["version"], 0)

    def test_real_http_save_export_conflict_and_model_disabled(self):
        status, page, response_headers = self.request("/")
        self.assertEqual(status, 200)
        token = re.search(rb'name="csrf" content="([^"]+)"', page).group(1).decode()
        self.assertIn("script-src 'self'", response_headers["Content-Security-Policy"])
        headers = {"X-FPA-CSRF": token}
        body = {"data": demo(), "version": 0, "actor": "合成测试", "reason": "HTTP验收"}
        status, saved, _ = self.request("/api/save", body, headers)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(saved)["version"], 1)
        self.assertEqual(self.request("/api/save", body, headers)[0], 409)
        self.assertEqual(self.request("/api/export")[1][:2], b"PK")
        self.assertIn(b'href="#UI-2"', self.request("/prototype")[1])
        self.assertEqual(self.request("/api/draft", {"version": 1, "model": "unused"}, headers)[0], 400)
        result = self.request("/api/evaluate", {"version": 1, "rule_id": "RULE-1", "amount": "10000.01", "currency": "CNY", "date": "2026-10-21"}, headers)
        self.assertEqual(json.loads(result[1])["result"], "财务主管复核")


if __name__ == "__main__":
    unittest.main()
