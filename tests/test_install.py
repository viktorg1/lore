import json
import os
import stat
import unittest

from support import TempHome, run_script  # noqa: F401  (also sets sys.path)

FAKE_CLAUDE = """#!/usr/bin/env python3
import os, sys
with open(os.environ["FAKE_CLAUDE_LOG"], "a") as log:
    log.write(" ".join(sys.argv[1:]) + "\\n")
state = os.environ["FAKE_CLAUDE_STATE"]
if sys.argv[1:3] == ["mcp", "get"]:
    if os.path.exists(state):
        print(open(state).read()); sys.exit(0)
    sys.exit(1)
if sys.argv[1:3] == ["mcp", "add"]:
    open(state, "w").write(" ".join(sys.argv[1:]))
if sys.argv[1:3] == ["mcp", "remove"] and os.path.exists(state):
    os.unlink(state)
"""

class TestInstall(TempHome):
    def setUp(self):
        super().setUp()
        self.fakehome = self.scratch / "home"
        self.fakehome.mkdir()
        self.bin = self.scratch / "bin"
        self.bin.mkdir()
        self.log = self.scratch / "claude.log"
        self.env = {"PATH": f"{self.bin}:/usr/bin:/bin", "HOME": str(self.fakehome), "LORE_HOME": str(self.home),
                    "FAKE_CLAUDE_LOG": str(self.log), "FAKE_CLAUDE_STATE": str(self.scratch / "claude.state")}

    def with_claude(self):
        path = self.bin / "claude"
        path.write_text(FAKE_CLAUDE)
        path.chmod(path.stat().st_mode | stat.S_IEXEC)

    def install(self, *args):
        return run_script("install.py", *args, env=self.env)

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_nothing_found_is_not_an_error(self):
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Claude Code: not found", r.stdout)
        self.assertIn("Copilot CLI: not found", r.stdout)

    def test_claude_is_added_once_at_user_scope(self):
        self.with_claude()
        r = self.install("--client", "claude")
        self.assertEqual(r.returncode, 0, r.stderr)
        adds = [c for c in self.calls() if c.startswith("mcp add")]
        self.assertEqual(len(adds), 1)
        self.assertIn("--scope user lore --", adds[0])
        self.assertIn("mcp_server.py", adds[0])
        again = self.install("--client", "claude")
        self.assertIn("already set up", again.stdout)
        self.assertEqual(len([c for c in self.calls() if c.startswith("mcp add")]), 1)
        self.assertFalse((self.fakehome / ".claude" / "CLAUDE.md").exists())      # the server sends its own instructions

    def test_copilot_merges_the_server_and_keeps_other_content(self):
        folder = self.fakehome / ".copilot"
        folder.mkdir()
        (folder / "mcp-config.json").write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}, "keep": 1}))
        (folder / "copilot-instructions.md").write_text("Be brief.\n")
        r = self.install("--client", "copilot")
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads((folder / "mcp-config.json").read_text())
        self.assertEqual(set(data["mcpServers"]), {"other", "lore"})
        self.assertEqual((data["keep"], data["mcpServers"]["lore"]["type"]), (1, "local"))
        doc = (folder / "copilot-instructions.md").read_text()
        self.assertTrue(doc.startswith("Be brief."))
        self.assertIn("get_rules", doc)
        self.assertEqual(doc.count("lore:begin"), 1)
        again = self.install("--client", "copilot")
        self.assertIn("already set up", again.stdout)
        self.assertEqual((folder / "copilot-instructions.md").read_text(), doc)    # idempotent

    def test_uninstall_removes_only_what_was_added(self):
        folder = self.fakehome / ".copilot"
        folder.mkdir()
        (folder / "mcp-config.json").write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}))
        (folder / "copilot-instructions.md").write_text("Be brief.\n")
        self.install("--client", "copilot")
        self.install("--client", "copilot", "--uninstall")
        self.assertEqual(set(json.loads((folder / "mcp-config.json").read_text())["mcpServers"]), {"other"})
        self.assertEqual((folder / "copilot-instructions.md").read_text(), "Be brief.\n")

    def test_uninstall_deletes_an_instruction_file_it_created(self):
        folder = self.fakehome / ".copilot"
        folder.mkdir()
        self.install("--client", "copilot")
        self.assertTrue((folder / "copilot-instructions.md").exists())
        self.install("--client", "copilot", "--uninstall")
        self.assertFalse((folder / "copilot-instructions.md").exists())

    def test_dry_run_changes_nothing(self):
        self.with_claude()
        (self.fakehome / ".copilot").mkdir()
        r = self.install("--dry-run")
        self.assertIn("would run: ", r.stdout)
        self.assertIn("would add the lore server", r.stdout)
        self.assertEqual([c for c in self.calls() if c.startswith("mcp add")], [])
        self.assertEqual(list((self.fakehome / ".copilot").iterdir()), [])

    def test_an_invalid_copilot_config_is_not_overwritten(self):
        folder = self.fakehome / ".copilot"
        folder.mkdir()
        (folder / "mcp-config.json").write_text("{not json")
        r = self.install("--client", "copilot")
        self.assertEqual(r.returncode, 2)
        self.assertEqual((folder / "mcp-config.json").read_text(), "{not json")

    def test_approval_mode_is_saved(self):
        os.environ["LORE_HOME"] = str(self.home)
        self.install("--approval", "manual")
        self.assertEqual(json.loads((self.home / "config.json").read_text())["approval"], "manual")

if __name__ == "__main__":
    unittest.main()
