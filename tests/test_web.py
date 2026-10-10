import json
import threading
import unittest
import urllib.error
import urllib.request

from support import RegisteredProject  # noqa: F401  (also sets sys.path)

from core.models import Status
from core.repository import RuleRepository
from web import server as web_server
from web.api import Api
from web.runner import MAX_OUTPUT, Runner
from web.server import MAX_BODY, make_server
from web.validation import ApiError, number_field, text_field

TOKEN = "test-token"


class TestValidation(unittest.TestCase):
    def test_text_field(self):
        self.assertEqual(text_field({"a": "  x "}, "a"), "x")
        self.assertEqual(text_field({}, "a", required=False), "")
        for body in ({}, {"a": ""}, {"a": 5}, {"a": "x\0y"}, {"a": "x" * 11}):
            with self.assertRaises(ApiError):
                text_field(body, "a", maxlen=10)

    def test_number_field(self):
        self.assertEqual(number_field({"n": "0.95"}, "n", 0.9, float, 0.5, 1.0), 0.95)
        self.assertEqual(number_field({}, "n", 5, int, 1, 10), 5)
        for body in ({"n": "abc"}, {"n": 99}, {"n": None}):
            with self.assertRaises(ApiError):
                number_field(body, "n", 5, int, 1, 10)


class TestApi(RegisteredProject):
    def setUp(self):
        super().setUp()
        self.api = Api()

    def status_of(self, call) -> int:
        with self.assertRaises(ApiError) as cm:
            call()
        return cm.exception.status

    def test_projects_and_rules_views(self):
        self.assertEqual(self.api.projects(), [{"name": "app", "root": str(self.root), "active": 1, "pending": 1}])
        data = self.api.project_rules("app")
        self.assertEqual(data["sections"], ["src", "tests"])
        self.assertEqual({r["status"] for r in data["rules"]}, {"active", "pending"})
        self.assertEqual(data["rules"][0]["evidence"], "12/12 files")
        self.assertEqual(set(data["rules"][0]), {"id", "text", "scope", "status", "source", "evidence", "created"})

    def test_actions(self):
        rid = self.pending.id
        self.assertEqual(self.api.act("app", rid, {"action": "approve"})["status"], "active")
        self.assertEqual(self.api.act("app", rid, {"action": "unapprove"})["status"], "pending")
        edited = self.api.act("app", rid, {"action": "edit", "text": "New wording here", "scope": "section:src"})
        self.assertEqual((edited["text"], edited["scope"]), ("New wording here", "section:src"))
        self.assertEqual(self.api.act("app", rid, {"action": "remove"}), {"removed": rid})
        self.assertEqual([r.id for r in self.repo.all()], [self.active.id])

    def test_action_errors(self):
        rid = self.pending.id
        for call, status in [
            (lambda: self.api.project_rules("ghost"), 404),
            (lambda: self.api.act("ghost", rid, {"action": "approve"}), 404),
            (lambda: self.api.act("app", "deadbeef", {"action": "approve"}), 404),
            (lambda: self.api.act("app", rid, {"action": "explode"}), 400),
            (lambda: self.api.act("app", rid, {"action": "edit", "text": "x"}), 400),
            (lambda: self.api.act("app", rid, {"action": "edit", "text": "ok", "scope": "bogus"}), 400),
            (lambda: self.api.act("app", rid, {"action": "edit", "text": "  ", "scope": "global"}), 400),
        ]:
            self.assertEqual(self.status_of(call), status)

    def test_add_rule(self):
        out = self.api.add_rule("app", {"text": "  Wrap SDK calls in an adapter ", "scope": "section:src"})
        self.assertEqual((out["outcome"], out["rule"]["status"], out["rule"]["source"]), ("added", "active", "ui"))
        self.assertEqual(out["rule"]["scope"], "section:src")
        self.assertEqual(self.api.add_rule("app", {"text": "Keep tests fast", "status": "pending"})["rule"]["status"], "pending")
        self.assertEqual(self.api.add_rule("app", {"text": "Keep tests fast", "status": "pending"})["outcome"], "duplicate")
        self.assertEqual(self.api.add_rule("app", {"text": "Default scope is global"})["rule"]["scope"], "global")

    def test_add_rule_validation(self):
        for body in ({}, {"text": "  "}, {"text": "ok", "scope": "bogus"}, {"text": "ok", "status": "weird"},
                     {"text": "ok", "status": ["active"]}, {"text": 5}, {"text": "x" * 2001}):
            self.assertEqual(self.status_of(lambda: self.api.add_rule("app", body)), 400, body)
        self.assertEqual(self.status_of(lambda: self.api.add_rule("ghost", {"text": "ok"})), 404)


class TestScripts(RegisteredProject):
    """The Tools tab: every script runs for real, as a subprocess."""

    def setUp(self):
        super().setUp()
        self.api = Api()
        body = "def f(a: int) -> int:\n    if a:\n        return a\n    for x in range(3):\n        a += x\n    return a\n"
        for i in range(10):
            self.write(f"app/src/api/m{i}.py", body)

    def tool(self, tool, **params):
        return self.api.run_tool("app", {"tool": tool, "params": params})

    def bad(self, tool, **params):
        with self.assertRaises(ApiError) as cm:
            self.tool(tool, **params)
        self.assertEqual(cm.exception.status, 400, (tool, params))

    def test_register_runs_memorize(self):
        self.write("fresh/src/a.py", "x = 1\n")
        self.write("fresh/AGENTS.md", "- Always write tests first\n")
        res = self.api.register({"path": str(self.scratch / "fresh"), "name": "fresh"})
        self.assertTrue(res["ok"], res["output"])
        self.assertEqual((res["name"], res["command"].split()[:2]), ("fresh", ["python3", "memorize.py"]))
        self.assertEqual([r.text for r in RuleRepository("fresh").all()], ["Always write tests first"])
        again = self.api.register({"path": str(self.scratch / "fresh"), "name": "fresh2", "noImport": True})
        self.assertTrue(again["ok"], again["output"])
        self.assertEqual(RuleRepository("fresh2").all(), [])

    def test_register_failures(self):
        res = self.api.register({"path": "/definitely/not/here"})
        self.assertFalse(res["ok"])
        self.assertIn("not a directory", res["output"])
        for body in ({}, {"path": ""}, {"path": 5}, {"path": "/tmp", "name": "../x"}, {"path": "a\0b"}):
            with self.assertRaises(ApiError) as cm:
                self.api.register(body)
            self.assertEqual(cm.exception.status, 400, body)

    def test_every_script_runs(self):
        self.assertTrue(self.tool("remap")["ok"])
        prev = self.tool("discover", mode="preview")
        self.assertTrue(prev["ok"], prev["output"])
        self.assertIn("candidate rule", prev["output"])
        before = len(self.repo.all())
        self.assertTrue(self.tool("discover", mode="save")["ok"])
        self.assertGreater(len(self.repo.all()), before)
        self.assertTrue(all(r.status is Status.PENDING for r in self.repo.all() if r.source == "discover"))

        docs = self.write("standards.md", "- Prefer small pure functions everywhere\n- Never swallow exceptions silently\n")
        dry = self.tool("train", path=str(docs), dryRun=True)
        self.assertTrue(dry["ok"])
        self.assertIn("Prefer small pure functions", dry["output"])
        self.assertFalse([r for r in self.repo.all() if r.text.startswith("Prefer small pure")])
        self.assertTrue(self.tool("train", path=str(docs), scope="section:src/api", pending=True)["ok"])
        trained = [r for r in self.repo.all() if r.text.startswith("Prefer small pure")][0]
        self.assertEqual((trained.status, trained.scope.key), (Status.PENDING, "section:src/api"))

        self.repo.set_status([trained.id], Status.ACTIVE)
        shown = self.tool("resolve", paths=["src/api/m1.py"])
        self.assertTrue(shown["ok"])
        self.assertIn("Prefer small pure functions", shown["output"])

        synced = self.tool("sync")
        self.assertTrue(synced["ok"], synced["output"])
        self.assertTrue(list((self.root / ".github" / "instructions").glob("lore-*.instructions.md")))

        mcp = self.tool("mcp-check")
        self.assertTrue(mcp["ok"], mcp["output"])
        self.assertIn("get_rules", mcp["output"])

    def test_tool_validation(self):
        self.bad("nope")
        self.bad("train")                                    # path required
        self.bad("train", path="x", scope="bogus")
        self.bad("discover", mode="explode")
        self.bad("discover", minRatio="abc")
        self.bad("discover", minRatio=0.1)
        self.bad("discover", minFiles=0)
        self.bad("resolve", paths=[])
        self.bad("resolve", paths="src/a.py")
        self.bad("resolve", paths=["--max-tokens=1"])
        self.bad("resolve", paths=["x"] * 21)
        with self.assertRaises(ApiError):
            self.api.run_tool("app", {"tool": "sync", "params": "x"})
        with self.assertRaises(ApiError) as cm:
            self.api.run_tool("ghost", {"tool": "sync"})
        self.assertEqual(cm.exception.status, 404)

    def test_values_cannot_be_read_as_flags(self):
        res = self.tool("train", path="--help")
        self.assertFalse(res["ok"])
        self.assertIn("does not exist", res["output"])
        self.assertNotIn("usage:", res["output"])
        res = self.api.register({"path": "--help"})
        self.assertFalse(res["ok"])
        self.assertNotIn("usage:", res["output"])

    def test_runner_timeout_truncation_and_failure(self):
        runner = Runner()
        slow = runner.run(["-c", "import time; time.sleep(5)"], timeout=1)
        self.assertEqual((slow["ok"], slow["code"]), (False, -1))
        self.assertIn("timed out", slow["output"])
        big = runner.run(["-c", f"print('x' * {MAX_OUTPUT * 2})"])
        self.assertTrue(big["ok"])
        self.assertLessEqual(len(big["output"]), MAX_OUTPUT + 40)
        self.assertIn("truncated", big["output"])
        failed = runner.run(["-c", "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)"])
        self.assertEqual((failed["ok"], failed["code"]), (False, 3))
        self.assertIn("out", failed["output"])
        self.assertIn("err", failed["output"])


class TestHttp(RegisteredProject):
    def setUp(self):
        super().setUp()
        self.srv = make_server(0, TOKEN)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def call(self, method, path, body=None, token=TOKEN, host=None, origin=None, ctype="application/json"):
        headers = {"Host": host or f"127.0.0.1:{self.port}"}
        if token is not None:
            headers["X-Lore-Token"] = token
        if origin:
            headers["Origin"] = origin
        data = None
        if body is not None:
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            headers["Content-Type"] = ctype
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req) as res:
                return res.status, res.read(), dict(res.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    def test_page_is_served_with_security_headers(self):
        status, body, hdr = self.call("GET", "/", token=None)
        self.assertEqual(status, 200)
        self.assertIn(b"<title>lore</title>", body)
        self.assertIn("frame-ancestors 'none'", hdr["Content-Security-Policy"])
        self.assertEqual(hdr["X-Content-Type-Options"], "nosniff")
        self.assertNotIn(TOKEN.encode(), body)

    def test_page_is_read_fresh_on_every_request(self):
        page = self.scratch / "page.html"
        page.write_text("<title>one</title>")
        original, web_server.UI_FILE = web_server.UI_FILE, page
        self.addCleanup(setattr, web_server, "UI_FILE", original)
        self.assertIn(b"one", self.call("GET", "/", token=None)[1])
        page.write_text("<title>two</title>")
        status, body, hdr = self.call("GET", "/", token=None)
        self.assertIn(b"two", body)
        self.assertEqual(hdr["Cache-Control"], "no-store")
        page.unlink()
        self.assertEqual(self.call("GET", "/", token=None)[0], 500)

    def test_api_needs_the_token(self):
        for tok in (None, "", "wrong"):
            self.assertEqual(self.call("GET", "/api/projects", token=tok)[0], 401)
        status, body, _ = self.call("GET", "/api/projects")
        self.assertEqual((status, json.loads(body)[0]["name"]), (200, "app"))

    def test_rebinding_and_cross_origin_requests_are_refused(self):
        self.assertEqual(self.call("GET", "/api/projects", host="evil.example:80")[0], 403)
        self.assertEqual(self.call("GET", "/", token=None, host="evil.example")[0], 403)
        self.assertEqual(self.call("GET", "/api/projects", origin="http://evil.example")[0], 403)
        self.assertEqual(self.call("GET", "/api/projects", host=f"localhost:{self.port}")[0], 200)
        status, _, _ = self.call("POST", f"/api/projects/app/rules/{self.pending.id}", {"action": "remove"}, origin="http://evil.example")
        self.assertEqual(status, 403)
        self.assertEqual(len(self.repo.all()), 2)

    def test_post_flow_and_validation(self):
        rid = self.pending.id
        path = f"/api/projects/app/rules/{rid}"
        status, body, _ = self.call("POST", path, {"action": "approve"})
        self.assertEqual((status, json.loads(body)["status"]), (200, "active"))
        self.assertEqual(self.call("POST", path, {"action": "approve"}, ctype="text/plain")[0], 415)
        self.assertEqual(self.call("POST", path, b"not json")[0], 400)
        self.assertEqual(self.call("POST", path, b"[1,2]")[0], 400)
        self.assertEqual(self.call("POST", path, b"x" * (MAX_BODY + 1))[0], 413)
        self.assertEqual(self.call("POST", path, {"action": "approve"}, token="bad")[0], 401)
        self.assertEqual(self.call("POST", "/api/projects/app/rules/zzzzzzzz", {"action": "approve"})[0], 404)
        self.assertEqual(self.call("POST", "/api/projects/..%2Fetc/rules/" + rid, {"action": "approve"})[0], 404)
        self.assertEqual(self.call("GET", "/api/projects/ghost/rules")[0], 404)
        self.assertEqual(self.call("GET", "/nope", token=None)[0], 404)

    def test_new_routes_over_http(self):
        status, body, _ = self.call("POST", "/api/projects/app/rules", {"text": "Keep tests fast", "scope": "global"})
        self.assertEqual((status, json.loads(body)["outcome"]), (200, "added"))
        self.assertEqual(self.call("POST", "/api/projects/app/rules", {"text": ""})[0], 400)
        status, body, _ = self.call("POST", "/api/projects/app/run", {"tool": "mcp-check"})
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["ok"])
        status, body, _ = self.call("POST", "/api/projects", {"path": "/definitely/not/here"})
        self.assertEqual((status, json.loads(body)["ok"]), (200, False))
        for path, payload in (("/api/projects", {"path": "/tmp"}), ("/api/projects/app/rules", {"text": "x"}), ("/api/projects/app/run", {"tool": "sync"})):
            self.assertEqual(self.call("POST", path, payload, token=None)[0], 401, path)
            self.assertEqual(self.call("POST", path, payload, origin="http://evil.example")[0], 403, path)
            self.assertEqual(self.call("POST", path, payload, host="evil.example")[0], 403, path)
            self.assertEqual(self.call("POST", path, payload, ctype="text/plain")[0], 415, path)
        self.assertEqual(self.call("GET", "/api/projects/app/run")[0], 404)

    def test_binds_to_loopback_only(self):
        self.assertEqual(self.srv.server_address[0], "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
