import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from ljh_research.public import dispatch
from ljh_research_panel.__main__ import server_for


class PanelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ljh-panel-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        dispatch({"protocol_version": 1, "project_root": str(self.root), "method": "setup.create", "params": {}}, human=True, evidence="Synthetic test setup")
        self.server = server_for(self.root)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.shutdown)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.token = json.load(urlopen(self.url + "/api/bootstrap"))["csrf_token"]

    def shutdown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def post(self, body, token=None, origin=None):
        headers = {"Content-Type": "application/json"}
        if token is not None:
            headers["X-LJH-Token"] = token
        if origin:
            headers["Origin"] = origin
        request = Request(self.url + "/api/operation", data=json.dumps(body).encode(), headers=headers, method="POST")
        try:
            with urlopen(request) as response:
                return response.status, json.load(response)
        except HTTPError as exc:
            return exc.code, json.load(exc)

    def test_rejects_non_object_and_cross_origin_requests(self):
        status, body = self.post([], self.token)
        self.assertEqual(status, 400)
        self.assertFalse(body["ok"])
        request = {"protocol_version": 1, "method": "task.list", "params": {}}
        self.assertEqual(self.post(request)[0], 403)
        self.assertEqual(self.post(request, self.token, "https://outside.example")[0], 403)

    def test_adapter_binds_project_and_does_not_accept_other_root(self):
        status, body = self.post({"protocol_version": 1, "method": "workspace.get", "params": {}, "project_root": "../another-project"}, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["result"]["project_root"], str(self.root))


if __name__ == "__main__":
    unittest.main()
