import json
import unittest

from support import TempHome  # noqa: F401  (also sets sys.path)

from core import projects
from core.models import Scope, Status
from core.repository import RuleRepository


class CliCase(TempHome):
    """A scratch project folder 'demoproj' with a little code, not yet registered."""

    def setUp(self):
        super().setUp()
        for rel in ("src/api/users.py", "src/ui/App.tsx", "README.md", "node_modules/x/y.js"):
            self.write(f"demoproj/{rel}")
        self.proj = self.scratch / "demoproj"

    def register(self):
        self.assertEqual(self.script("memorize.py", "--path", self.proj).returncode, 0)
        return RuleRepository("demoproj")


class TestMemorize(CliCase):
    def test_default_name_and_map(self):
        r = self.script("memorize.py", "--path", self.proj)
        self.assertEqual(r.returncode, 0, r.stderr)
        amap = json.loads((self.home / "demoproj" / "map.json").read_text())
        self.assertEqual(set(amap["sections"]), {"root", "src/api", "src/ui"})  # node_modules ignored
        self.assertEqual(amap["sections"]["src/api"]["languages"], {"python": 1})
        self.assertEqual(projects.get("demoproj").root, self.proj.resolve())

    def test_explicit_name_and_bad_input(self):
        self.assertEqual(self.script("memorize.py", "--path", self.proj, "--name", "other").returncode, 0)
        self.assertTrue((self.home / "other" / "project.json").exists())
        for args in (["--path", self.proj, "--name", "../evil"], ["--path", self.proj / "nope"], []):
            self.assertNotEqual(self.script("memorize.py", *args).returncode, 0, args)

    def test_name_collision_with_another_folder(self):
        self.register()
        other = self.scratch / "elsewhere"
        other.mkdir()
        r = self.script("memorize.py", "--path", other, "--name", "demoproj")
        self.assertEqual(r.returncode, 2)
        self.assertIn("already belongs to", r.stderr)

    def test_imports_existing_instruction_files_once(self):
        (self.proj / ".github").mkdir()
        (self.proj / ".github" / "copilot-instructions.md").write_text("- Always use type hints in Python code\n")
        self.register()
        repo = self.register()
        self.assertEqual([r.text for r in repo.all()], ["Always use type hints in Python code"])

    def test_no_import_flag(self):
        (self.proj / "AGENTS.md").write_text("- Always write tests first\n")
        self.script("memorize.py", "--path", self.proj, "--no-import")
        self.assertEqual(RuleRepository("demoproj").all(), [])


class TestTrain(CliCase):
    def test_folder_is_idempotent_and_unknown_project_fails(self):
        repo = self.register()
        self.write("docs/a.md", "# Standards\n- Write tests for every bug fix\n- Log errors with context\n")
        self.write("docs/b.txt", "Always handle errors explicitly instead of swallowing them.\n")
        docs = self.scratch / "docs"
        r = self.script("train.py", "--name", "demoproj", "--from", docs)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(repo.all()), 3)
        self.script("train.py", "--name", "demoproj", "--from", docs)
        self.assertEqual(len(repo.all()), 3)
        self.assertEqual(self.script("train.py", "--name", "ghost", "--from", docs).returncode, 2)
        self.assertEqual(self.script("train.py", "--name", "demoproj", "--from", self.scratch / "nope").returncode, 2)
        self.assertEqual(self.script("train.py", "--name", "demoproj", "--from", docs, "--scope", "bogus").returncode, 2)

    def test_dry_run_stores_nothing_and_pending_flag(self):
        repo = self.register()
        doc = self.write("one.md", "- Prefer small pure functions\n")
        out = self.script("train.py", "--name", "demoproj", "--from", doc, "--dry-run")
        self.assertIn("[global] Prefer small pure functions", out.stdout)
        self.assertEqual(repo.all(), [])
        self.script("train.py", "--name", "demoproj", "--from", doc, "--pending", "--scope", "section:src")
        self.assertEqual([(r.status, r.scope.key) for r in repo.all()], [(Status.PENDING, "section:src")])


class TestReview(CliCase):
    def setUp(self):
        super().setUp()
        self.repo = self.register()
        self.a = self.repo.add("Validate all input at the boundary", Scope.everywhere(), Status.PENDING).rule
        self.b = self.repo.add("Wrap SDK calls in an adapter", Scope.for_section("src/api"), Status.ACTIVE).rule

    def review(self, *args):
        return self.script("review.py", "--name", "demoproj", *args)

    def test_list_filters_by_status(self):
        out = self.review("list", "--status", "pending").stdout
        self.assertIn(self.a.id, out)
        self.assertNotIn(self.b.id, out)
        self.assertIn("-- 1 rule(s)", out)

    def test_add_approve_reject(self):
        self.assertIn("added:", self.review("add", "Keep tests fast", "--scope", "glob:tests/**", "--pending").stdout)
        self.assertEqual(self.review("add", "x", "--scope", "bogus").returncode, 2)
        self.assertIn("approved 2 rule(s)", self.review("approve", "--all").stdout)
        self.assertEqual(len(self.repo.with_status(Status.PENDING)), 0)
        self.assertIn("rejected 1 rule(s)", self.review("reject", self.a.id).stdout)
        self.assertIsNone(self.repo.get(self.a.id))
        self.assertIn("not found", self.review("reject", "deadbeef").stderr)

    def test_edit(self):
        out = self.review("edit", self.a.id, "--text", "Validate input at every boundary")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.repo.get(self.a.id).text, "Validate input at every boundary")
        self.assertEqual(self.review("edit", self.a.id).returncode, 2)                          # nothing to change
        self.assertEqual(self.review("edit", "deadbeef", "--text", "x").returncode, 2)          # unknown id
        self.assertEqual(self.review("edit", self.a.id, "--scope", "nonsense").returncode, 2)   # bad scope

    def test_resolve_accepts_absolute_and_relative_paths(self):
        for path in ("src/api/users.py", str(self.proj / "src/api/users.py")):
            out = self.review("resolve", path).stdout
            self.assertIn("[section] Wrap SDK calls in an adapter", out)
        self.assertEqual(self.review("resolve", "README.md").stdout.strip(), "(no rules apply)")

    def test_sync_writes_files_and_unknown_project_fails(self):
        out = self.review("sync")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue(list((self.proj / ".github" / "instructions").glob("lore-*.instructions.md")))
        self.assertEqual(self.script("review.py", "--name", "ghost", "list").returncode, 2)
        self.assertEqual(self.script("review.py", "--name", "../x", "list").returncode, 2)


class TestDiscoverCli(CliCase):
    def test_preview_saves_nothing_then_saves_pending_idempotently(self):
        repo = self.register()
        (self.proj / "composer.json").write_text(json.dumps({"require": {"laravel/framework": "^11"}}))
        r = self.script("discover.py", "--name", "demoproj")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(repo.all(), [])
        self.script("discover.py", "--name", "demoproj", "--save")
        saved = repo.all()
        self.assertTrue(saved and all(x.status is Status.PENDING and x.source == "discover" for x in saved))
        self.script("discover.py", "--name", "demoproj", "--save")
        self.assertEqual(len(repo.all()), len(saved))

    def test_activate_and_missing_root(self):
        repo = self.register()
        (self.proj / "composer.json").write_text(json.dumps({"require": {"laravel/framework": "^11"}}))
        self.script("discover.py", "--name", "demoproj", "--save", "--activate")
        self.assertTrue(all(r.status is Status.ACTIVE for r in repo.all()))
        import shutil
        shutil.rmtree(self.proj)
        r = self.script("discover.py", "--name", "demoproj")
        self.assertEqual(r.returncode, 2)
        self.assertIn("no longer exists", r.stderr)


if __name__ == "__main__":
    unittest.main()
