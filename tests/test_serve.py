import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import rules  # noqa: E402
import serve  # noqa: E402
import store  # noqa: E402

TOKEN = "test-token"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.environ["LORE_HOME"] = str(Path(self.tmp.name) / "mem")
        self.addCleanup(os.environ.pop, "LORE_HOME", None)
        root = Path(self.tmp.name) / "app"
        (root / "src").mkdir(parents=True)
        store.save_json(store.project_dir("app") / "project.json", {"name": "app", "root": str(root)})
        store.save_json(store.project_dir("app") / "map.json", {"sections": {"src": {"path": "src"}, "tests": {"path": "tests"}}})
        self.r1, _ = rules.add_rule("app", "Validate input at the boundary", {"type": "global"}, "pending", "discover", "12/12 files")
        self.r2, _ = rules.add_rule("app", "Name files in snake_case", {"type": "section", "value": "src"}, "active", "manual")


class TestEditRule(Base):
    def test_edit_text_and_scope_keeps_id_and_status(self):
        r = rules.edit_rule("app", self.r2["id"], "Name modules in snake_case", rules.parse_scope("glob:**/*.py"))
        self.assertEqual((r["id"], r["status"], r["text"]), (self.r2["id"], "active", "Name modules in snake_case"))
        self.assertEqual(rules.scope_key(r["scope"]), "glob:**/*.py")

    def test_edit_rejects_empty_unknown_and_duplicates(self):
        with self.assertRaises(ValueError):
            rules.edit_rule("app", self.r1["id"], "   ")
        with self.assertRaises(KeyError):
            rules.edit_rule("app", "deadbeef", "x")
        rules.add_rule("app", "Keep commits small and focused", {"type": "global"}, "active")
        with self.assertRaises(ValueError):
            rules.edit_rule("app", self.r1["id"], "keep commits small and focused.")

    def test_cli_edit(self):
        env = {**os.environ}
        run = lambda *a: subprocess.run([sys.executable, str(ROOT / "review.py"), "--name", "app", *a], capture_output=True, text=True, env=env)
        out = run("edit", self.r1["id"], "--text", "Validate all input at the boundary")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(rules.load("app")[0]["text"], "Validate all input at the boundary")
        self.assertEqual(run("edit", self.r1["id"]).returncode, 2)
        self.assertEqual(run("edit", "deadbeef", "--text", "x").returncode, 2)
        self.assertEqual(run("edit", self.r1["id"], "--scope", "nonsense").returncode, 2)


class TestApi(Base):
    def test_projects_and_rules_views(self):
        api = serve.Api()
        self.assertEqual(api.projects(), [{"name": "app", "root": str(Path(self.tmp.name) / "app"), "active": 1, "pending": 1}])
        data = api.project_rules("app")
        self.assertEqual(data["sections"], ["src", "tests"])
        self.assertEqual({r["status"] for r in data["rules"]}, {"active", "pending"})
        self.assertEqual(data["rules"][0]["evidence"], "12/12 files")

    def test_actions(self):
        api, rid = serve.Api(), self.r1["id"]
        self.assertEqual(api.act("app", rid, {"action": "approve"})["status"], "active")
        self.assertEqual(api.act("app", rid, {"action": "unapprove"})["status"], "pending")
        edited = api.act("app", rid, {"action": "edit", "text": "New wording here", "scope": "section:src"})
        self.assertEqual((edited["text"], edited["scope"]), ("New wording here", "section:src"))
        self.assertEqual(api.act("app", rid, {"action": "remove"}), {"removed": rid})
        self.assertEqual([r["id"] for r in rules.load("app")], [self.r2["id"]])

    def test_errors(self):
        api = serve.Api()
        for call, status in [
            (lambda: api.project_rules("ghost"), 404),
            (lambda: api.act("app", "deadbeef", {"action": "approve"}), 404),
            (lambda: api.act("app", self.r1["id"], {"action": "explode"}), 400),
            (lambda: api.act("app", self.r1["id"], {"action": "edit", "text": "x"}), 400),
            (lambda: api.act("app", self.r1["id"], {"action": "edit", "text": "ok", "scope": "bogus"}), 400),
            (lambda: api.act("app", self.r1["id"], {"action": "edit", "text": "  ", "scope": "global"}), 400),
        ]:
            with self.assertRaises(serve.ApiError) as cm:
                call()
            self.assertEqual(cm.exception.status, status)


class TestAddRule(Base):
    def test_add_rule(self):
        api = serve.Api()
        out = api.add_rule("app", {"text": "  Wrap SDK calls in an adapter ", "scope": "section:src"})
        self.assertEqual((out["outcome"], out["rule"]["status"], out["rule"]["source"]), ("added", "active", "ui"))
        self.assertEqual(out["rule"]["scope"], "section:src")
        self.assertEqual(api.add_rule("app", {"text": "Keep tests fast", "status": "pending"})["rule"]["status"], "pending")
        self.assertEqual(api.add_rule("app", {"text": "Keep tests fast", "status": "pending"})["outcome"], "duplicate")
        self.assertEqual(api.add_rule("app", {"text": "Default scope is global"})["rule"]["scope"], "global")

    def test_add_rule_validation(self):
        api = serve.Api()
        for body in ({}, {"text": "  "}, {"text": "ok", "scope": "bogus"}, {"text": "ok", "status": "weird"}, {"text": 5}, {"text": "x" * 2001}):
            with self.assertRaises(serve.ApiError) as cm:
                api.add_rule("app", body)
            self.assertEqual(cm.exception.status, 400, body)
        with self.assertRaises(serve.ApiError) as cm:
            api.add_rule("ghost", {"text": "ok"})
        self.assertEqual(cm.exception.status, 404)


class TestScripts(Base):
    """The Tools tab: every script runs for real, as a subprocess."""

    def setUp(self):
        super().setUp()
        self.api = serve.Api()
        self.root = Path(self.tmp.name) / "app"
        (self.root / "src" / "api").mkdir(parents=True, exist_ok=True)
        body = "def f(a: int) -> int:\n    if a:\n        return a\n    for x in range(3):\n        a += x\n    return a\n"
        for i in range(10):
            (self.root / "src" / "api" / f"m{i}.py").write_text(body)

    def tool(self, tool, **params):
        return self.api.run_tool("app", {"tool": tool, "params": params})

    def bad(self, tool, **params):
        with self.assertRaises(serve.ApiError) as cm:
            self.tool(tool, **params)
        self.assertEqual(cm.exception.status, 400, (tool, params))

    def test_register_runs_memorize(self):
        proj = Path(self.tmp.name) / "fresh"
        (proj / "src").mkdir(parents=True)
        (proj / "src" / "a.py").write_text("x = 1\n")
        (proj / "AGENTS.md").write_text("- Always write tests first\n")
        res = self.api.register({"path": str(proj), "name": "fresh"})
        self.assertTrue(res["ok"], res["output"])
        self.assertEqual((res["name"], res["command"].split()[:2]), ("fresh", ["python3", "memorize.py"]))
        self.assertEqual([r["text"] for r in rules.load("fresh")], ["Always write tests first"])
        again = self.api.register({"path": str(proj), "name": "fresh2", "noImport": True})
        self.assertTrue(again["ok"], again["output"])
        self.assertEqual(rules.load("fresh2"), [])

    def test_register_failures(self):
        res = self.api.register({"path": "/definitely/not/here"})
        self.assertFalse(res["ok"])
        self.assertIn("not a directory", res["output"])
        for body in ({}, {"path": ""}, {"path": 5}, {"path": "/tmp", "name": "../x"}, {"path": "a\0b"}):
            with self.assertRaises(serve.ApiError) as cm:
                self.api.register(body)
            self.assertEqual(cm.exception.status, 400, body)

    def test_remap_discover_train_resolve_sync_and_mcp(self):
        self.assertTrue(self.tool("remap")["ok"])
        prev = self.tool("discover", mode="preview")
        self.assertTrue(prev["ok"], prev["output"])
        self.assertIn("candidate rule", prev["output"])
        before = len(rules.load("app"))
        saved = self.tool("discover", mode="save")
        self.assertTrue(saved["ok"])
        self.assertGreater(len(rules.load("app")), before)
        self.assertTrue(all(r["status"] == "pending" for r in rules.load("app") if r["source"] == "discover"))

        docs = Path(self.tmp.name) / "standards.md"
        docs.write_text("- Prefer small pure functions everywhere\n- Never swallow exceptions silently\n")
        dry = self.tool("train", path=str(docs), dryRun=True)
        self.assertTrue(dry["ok"])
        self.assertIn("Prefer small pure functions", dry["output"])
        self.assertNotIn("Prefer small pure functions everywhere", [r["text"] for r in rules.load("app")])
        self.assertTrue(self.tool("train", path=str(docs), scope="section:src/api", pending=True)["ok"])
        trained = [r for r in rules.load("app") if r["text"].startswith("Prefer small pure")][0]
        self.assertEqual((trained["status"], rules.scope_key(trained["scope"])), ("pending", "section:src/api"))

        rules.set_status("app", [trained["id"]], "active")
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
        with self.assertRaises(serve.ApiError):
            self.api.run_tool("app", {"tool": "sync", "params": "x"})
        with self.assertRaises(serve.ApiError) as cm:
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

    def test_runner_timeout_and_truncation(self):
        runner = serve.Runner()
        slow = runner.run(["-c", "import time; time.sleep(5)"], timeout=1)
        self.assertEqual((slow["ok"], slow["code"]), (False, -1))
        self.assertIn("timed out", slow["output"])
        big = runner.run(["-c", f"print('x' * {serve.MAX_OUTPUT * 2})"])
        self.assertTrue(big["ok"])
        self.assertLessEqual(len(big["output"]), serve.MAX_OUTPUT + 40)
        self.assertIn("truncated", big["output"])
        failed = runner.run(["-c", "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)"])
        self.assertEqual((failed["ok"], failed["code"]), (False, 3))
        self.assertIn("out", failed["output"]); self.assertIn("err", failed["output"])


class TestHttp(Base):
    def setUp(self):
        super().setUp()
        self.srv = serve.make_server(0, TOKEN)
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
        rid = self.r1["id"]
        status, _, _ = self.call("POST", f"/api/projects/app/rules/{rid}", {"action": "remove"}, origin="http://evil.example")
        self.assertEqual(status, 403)
        self.assertEqual(len(rules.load("app")), 2)

    def test_post_flow_and_validation(self):
        rid, path = self.r1["id"], f"/api/projects/app/rules/{self.r1['id']}"
        status, body, _ = self.call("POST", path, {"action": "approve"})
        self.assertEqual((status, json.loads(body)["status"]), (200, "active"))
        self.assertEqual(self.call("POST", path, {"action": "approve"}, ctype="text/plain")[0], 415)
        self.assertEqual(self.call("POST", path, b"not json")[0], 400)
        self.assertEqual(self.call("POST", path, b"[1,2]")[0], 400)
        self.assertEqual(self.call("POST", path, b"x" * (serve.MAX_BODY + 1))[0], 413)
        self.assertEqual(self.call("POST", path, {"action": "approve"}, token="bad")[0], 401)
        self.assertEqual(self.call("POST", "/api/projects/app/rules/zzzzzzzz", {"action": "approve"})[0], 404)
        self.assertEqual(self.call("POST", "/api/projects/..%2Fetc/rules/" + rid, {"action": "approve"})[0], 404)
        self.assertEqual(self.call("GET", "/api/projects/ghost/rules")[0], 404)
        self.assertEqual(self.call("GET", "/nope", token=None)[0], 404)

    def test_page_is_read_fresh_on_every_request(self):
        page = Path(self.tmp.name) / "page.html"
        page.write_text("<title>one</title>")
        original, serve.UI_FILE = serve.UI_FILE, page
        self.addCleanup(setattr, serve, "UI_FILE", original)
        self.assertIn(b"one", self.call("GET", "/", token=None)[1])
        page.write_text("<title>two</title>")
        status, body, hdr = self.call("GET", "/", token=None)
        self.assertIn(b"two", body)
        self.assertEqual(hdr["Cache-Control"], "no-store")
        page.unlink()
        self.assertEqual(self.call("GET", "/", token=None)[0], 500)

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
