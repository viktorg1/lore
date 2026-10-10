import json
import os
import unittest
from unittest import mock

from support import RegisteredProject, run_script  # noqa: F401

from core.models import Scope, Status
from mcpserver.protocol import McpServer, Tool
from mcpserver.tools import create_server, locate


class TestProtocol(unittest.TestCase):
    def server(self):
        return McpServer("demo", "9.9", [Tool("echo", "Echo", {"type": "object"}, lambda a: a["text"]),
                                         Tool("boom", "Fails", {"type": "object"}, lambda a: 1 / 0)])

    def test_initialize_echoes_the_clients_protocol_version(self):
        reply = self.server().handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}})
        self.assertEqual(reply["result"]["protocolVersion"], "2025-03-26")
        self.assertEqual(reply["result"]["serverInfo"], {"name": "demo", "version": "9.9"})
        default = self.server().handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        self.assertEqual(default["result"]["protocolVersion"], "2024-11-05")

    def test_listing_and_calls(self):
        s = self.server()
        names = [t["name"] for t in s.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]]
        self.assertEqual(names, ["echo", "boom"])
        ok = s.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "echo", "arguments": {"text": "hi"}}})
        self.assertEqual(ok["result"], {"content": [{"type": "text", "text": "hi"}], "isError": False})

    def test_tool_failures_are_results_and_protocol_errors_are_errors(self):
        s = self.server()
        with mock.patch("mcpserver.protocol.log"):           # the failure is logged to stderr on purpose
            boom = s.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "boom"}})
        self.assertTrue(boom["result"]["isError"])
        self.assertEqual(s.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "nope"}})["error"]["code"], -32602)
        self.assertEqual(s.handle({"jsonrpc": "2.0", "id": 5, "method": "nope"})["error"]["code"], -32601)
        self.assertEqual(s.handle({"jsonrpc": "2.0", "id": 6, "method": "ping"})["result"], {})
        self.assertIsNone(s.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))


class TestLoreTools(RegisteredProject):
    def call(self, name, **args):
        return create_server().handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}})["result"]["content"][0]["text"]

    def test_get_rules_for_a_registered_path(self):
        text = self.call("get_rules", paths=[str(self.root / "src" / "users.py")])
        self.assertIn("Name files in snake_case", text)
        self.assertNotIn("Validate input at the boundary", text)         # still pending
        self.assertIn("No lore project", self.call("get_rules", paths=["/elsewhere/x.py"]))

    def test_get_rules_when_nothing_applies(self):
        self.repo.remove([self.active.id])
        self.assertIn("No rules apply", self.call("get_rules", paths=[str(self.root / "src" / "a.py")]))

    def test_record_feedback_defaults_to_the_files_section_as_pending(self):
        f = str(self.root / "src" / "users.py")
        self.assertIn("Saved as pending rule", self.call("record_feedback", rule="Return typed errors from handlers", paths=[f], evidence="reviewer said so"))
        saved = [r for r in self.repo.all() if r.text.startswith("Return typed")][0]
        self.assertEqual((saved.status, saved.scope, saved.source, saved.evidence), (Status.PENDING, Scope.for_section("src"), "feedback", "reviewer said so"))
        self.assertIn("Already known", self.call("record_feedback", rule="Return typed errors from handlers", paths=[f]))

    def test_record_feedback_for_a_root_file_is_global_and_explicit_scope_wins(self):
        self.call("record_feedback", rule="Keep the README short and current", paths=[str(self.root / "README.md")])
        self.call("record_feedback", rule="Use snake_case test names", paths=[str(self.root / "README.md")], scope="glob:tests/**")
        by_text = {r.text: r.scope.key for r in self.repo.all()}
        self.assertEqual(by_text["Keep the README short and current"], "global")
        self.assertEqual(by_text["Use snake_case test names"], "glob:tests/**")

    def test_record_feedback_errors_are_messages(self):
        self.assertIn("Not saved", self.call("record_feedback", rule="x", paths=["/elsewhere/a.py"]))
        self.assertIn("Not saved", self.call("record_feedback", rule="x", paths=[str(self.root / "src" / "a.py")], scope="bogus"))
        self.assertIn("Not saved", self.call("record_feedback", paths=[str(self.root / "src" / "a.py")]))   # no rule text

    def test_locate_relative_paths_by_cwd(self):
        old = os.getcwd()
        self.addCleanup(os.chdir, old)
        os.chdir(self.root)
        project, rels = locate(["src/x.py", "./README.md"])
        self.assertEqual((project.name, rels), ("app", ["src/x.py", "README.md"]))


class TestOverStdio(RegisteredProject):
    def test_whole_session_through_the_real_script(self):
        f = str(self.root / "src" / "users.py")
        msgs = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "get_rules", "arguments": {"paths": [f]}}},
            {"jsonrpc": "2.0", "id": 4, "method": "nope"},
        ]
        r = run_script("mcp_server.py", stdin="\n".join(json.dumps(m) for m in msgs) + "\nnot json\n", env=self.env, cwd="/")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = [json.loads(l) for l in r.stdout.splitlines()]
        self.assertEqual([o.get("id") for o in out], [1, 2, 3, 4, None])        # the notification gets no reply
        self.assertEqual({t["name"] for t in out[1]["result"]["tools"]}, {"get_rules", "record_feedback"})
        self.assertIn("Name files in snake_case", out[2]["result"]["content"][0]["text"])
        self.assertEqual(out[4]["error"]["code"], -32700)


if __name__ == "__main__":
    unittest.main()
