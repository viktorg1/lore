import json
import os
import tempfile
import unittest
from pathlib import Path

from support import RegisteredProject, TempHome  # noqa: F401  (also sets sys.path)

from core import export, projects, resolver, store, trainer
from core.globs import glob_match, split_globs
from core.mapper import section_of
from core.models import Level, Outcome, Rule, Scope, ScopeKind, Status
from core.trainer import TrainStats


class TestGlobs(unittest.TestCase):
    def test_glob_matching(self):
        self.assertTrue(glob_match("**/*.{ts,tsx}", "src/ui/App.tsx"))
        self.assertTrue(glob_match("*.py", "src/api/users.py"))
        self.assertTrue(glob_match("src/api/**", "src/api/v1/x.py"))
        self.assertFalse(glob_match("src/api/**", "src/ui/App.tsx"))

    def test_split_respects_braces(self):
        self.assertEqual(split_globs("*.{ts,tsx}, **/*.py"), ["*.{ts,tsx}", "**/*.py"])


class TestMapper(unittest.TestCase):
    def test_section_of(self):
        self.assertEqual(section_of("README.md"), "root")
        self.assertEqual(section_of("src/api/a/b.py"), "src/api")
        self.assertEqual(section_of("src/main.py"), "src")
        self.assertEqual(section_of("docs/a.md"), "docs")


class TestScope(unittest.TestCase):
    def test_parse_and_key_round_trip(self):
        for spec in ("global", "section:src/api", "glob:**/*.{ts,tsx},*.py"):
            self.assertEqual(Scope.parse(spec).key, spec)
        self.assertEqual(Scope.parse(None), Scope.everywhere())
        self.assertEqual(Scope.parse("section:/api/").section, "api")

    def test_bad_specs(self):
        for spec in ("nonsense", "section:", "glob:", "folder:x"):
            with self.assertRaises(ValueError):
                Scope.parse(spec)

    def test_dict_round_trip_matches_the_stored_format(self):
        self.assertEqual(Scope.for_section("src").to_dict(), {"type": "section", "value": "src"})
        self.assertEqual(Scope.for_globs("*.py").to_dict(), {"type": "glob", "globs": ["*.py"]})
        self.assertEqual(Scope.everywhere().to_dict(), {"type": "global"})
        for scope in (Scope.everywhere(), Scope.for_section("a/b"), Scope.for_globs("*.py", "x/**")):
            self.assertEqual(Scope.from_dict(scope.to_dict()), scope)

    def test_level_for_a_path(self):
        self.assertEqual(Scope.everywhere().level_for("a.py"), Level.GLOBAL)
        self.assertEqual(Scope.for_section("api").level_for("src/api/u.py"), Level.SECTION)
        self.assertIsNone(Scope.for_section("api").level_for("src/ui/u.py"))
        self.assertEqual(Scope.for_globs("*.py").level_for("src/api/u.py"), Level.FILE)
        self.assertIsNone(Scope.for_globs("*.py").level_for("a.ts"))
        self.assertLess(Level.FILE, Level.SECTION)

    def test_section_matching_by_name_prefix_and_suffix(self):
        self.assertTrue(Scope.for_section("api").covers_section("src/api"))
        self.assertTrue(Scope.for_section("src").covers_section("src/api"))
        self.assertFalse(Scope.for_section("ap").covers_section("src/api"))
        self.assertFalse(Scope.everywhere().covers_section("src"))

    def test_enums_print_as_their_values(self):
        self.assertEqual((str(Status.ACTIVE), f"{Outcome.ADDED}", f"{ScopeKind.GLOB}"), ("active", "added", "glob"))
        self.assertEqual(Status("pending"), Status.PENDING)


class TestRule(unittest.TestCase):
    def test_round_trip_keeps_unknown_keys(self):
        raw = {"id": "ab12cd34", "text": "t", "scope": {"type": "global"}, "status": "active", "source": "s",
               "evidence": "e", "created": "c", "hits": 2, "future_field": {"x": 1}}
        rule = Rule.from_dict(raw)
        self.assertEqual((rule.status, rule.hits, rule.extra), (Status.ACTIVE, 2, {"future_field": {"x": 1}}))
        self.assertEqual(rule.to_dict(), raw)

    def test_edited_is_only_written_when_set(self):
        rule = Rule("id", "t", Scope.everywhere())
        self.assertNotIn("edited", rule.to_dict())
        rule.edited = "now"
        self.assertEqual(rule.to_dict()["edited"], "now")

    def test_id_depends_on_wording_and_scope_not_on_formatting(self):
        a = Rule.make_id("Never use `any`", Scope.everywhere())
        self.assertEqual(a, Rule.make_id("never use any", Scope.everywhere()))
        self.assertNotEqual(a, Rule.make_id("never use any", Scope.for_section("src")))


class TestRepository(RegisteredProject):
    def test_add_dedupe_and_promote(self):
        first = self.repo.add("Never use any in TypeScript", Scope.everywhere(), Status.PENDING)
        second = self.repo.add("never use `any` in TypeScript.", Scope.everywhere(), Status.ACTIVE)
        self.assertEqual((first.outcome, second.outcome), (Outcome.ADDED, Outcome.PROMOTED))
        self.assertEqual(first.rule.id, second.rule.id)
        self.assertEqual(self.repo.get(first.rule.id).status, Status.ACTIVE)
        third = self.repo.add("Never use any in TypeScript", Scope.everywhere(), Status.PENDING)
        self.assertEqual(third.outcome, Outcome.DUPLICATE)
        self.assertEqual(self.repo.get(first.rule.id).hits, 2)

    def test_same_wording_in_another_scope_is_a_different_rule(self):
        self.repo.add("Keep functions short", Scope.everywhere())
        self.assertEqual(self.repo.add("Keep functions short", Scope.for_section("src")).outcome, Outcome.ADDED)

    def test_add_rejects_empty_text(self):
        with self.assertRaises(ValueError):
            self.repo.add("   ", Scope.everywhere())

    def test_edit_keeps_id_and_status(self):
        r = self.repo.edit(self.active.id, "Name modules in snake_case", Scope.for_globs("**/*.py"))
        self.assertEqual((r.id, r.status, r.text, r.scope.key), (self.active.id, Status.ACTIVE, "Name modules in snake_case", "glob:**/*.py"))
        self.assertTrue(self.repo.get(self.active.id).edited)

    def test_edit_rejects_empty_unknown_and_clashes(self):
        with self.assertRaises(ValueError):
            self.repo.edit(self.pending.id, "   ")
        with self.assertRaises(KeyError):
            self.repo.edit("deadbeef", "x")
        self.repo.add("Keep commits small and focused", Scope.everywhere(), Status.ACTIVE)
        with self.assertRaises(ValueError):
            self.repo.edit(self.pending.id, "keep commits small and focused.")

    def test_set_status_and_remove(self):
        done = self.repo.set_status([self.pending.id, "nope"], Status.ACTIVE)
        self.assertEqual([r.id for r in done], [self.pending.id])
        self.assertEqual(len(self.repo.with_status(Status.ACTIVE)), 2)
        gone = self.repo.remove([self.active.id])
        self.assertEqual([r.id for r in gone], [self.active.id])
        self.assertEqual([r.id for r in self.repo.all()], [self.pending.id])

    def test_the_file_format_is_unchanged(self):
        data = json.loads((self.home / "app" / "rules.json").read_text())
        self.assertEqual(data["version"], 1)
        self.assertEqual(data["rules"][1]["scope"], {"type": "section", "value": "src"})
        self.assertEqual(data["rules"][0]["status"], "pending")


class TestResolver(RegisteredProject):
    def setUp(self):
        super().setUp()
        self.repo.remove([self.pending.id, self.active.id])

    def test_scopes_specificity_and_pending_excluded(self):
        self.repo.add("Prefer small functions everywhere", Scope.everywhere(), Status.ACTIVE)
        self.repo.add("Validate input at the route boundary", Scope.for_section("api"), Status.ACTIVE)
        self.repo.add("Type annotate all Python functions", Scope.parse("glob:*.py"), Status.ACTIVE)
        self.repo.add("Pending rule never shown", Scope.everywhere(), Status.PENDING)
        res = resolver.resolve("app", ["src/api/users.py"])
        texts = [r.text for r in res.rules]
        self.assertEqual(len(texts), 3)
        self.assertNotIn("Pending rule never shown", texts)
        self.assertEqual(texts[0], "Type annotate all Python functions")   # most specific first
        self.assertIn("- [file] Type annotate", res.text)
        self.assertEqual(res.sections, ["src/api"])
        ui = [r.text for r in resolver.resolve("app", ["src/ui/App.tsx"]).rules]
        self.assertEqual(ui, ["Prefer small functions everywhere"])

    def test_no_applicable_rule_gives_empty_text(self):
        self.assertEqual(resolver.resolve("app", ["README.md"]).text, "")

    def test_budget_truncates(self):
        texts = ["Use dependency injection for all service classes", "Log errors with request context attached",
                 "Keep database migrations reversible", "Prefer composition over inheritance in domain models",
                 "Wrap third party SDK calls in an adapter module", "Never commit generated protobuf output",
                 "Name boolean flags with is or has prefixes", "Document public functions with a one line summary"]
        for t in texts:
            self.repo.add(t, Scope.everywhere(), Status.ACTIVE)
        res = resolver.resolve("app", ["README.md"], max_tokens=60)
        self.assertGreater(res.omitted, 0)
        self.assertLess(len(res.rules), len(texts))
        self.assertIn("more rules omitted", res.text)


class TestExport(RegisteredProject):
    def test_sync_writes_and_prunes_generated_files_only(self):
        self.repo.add("Prefer small functions everywhere", Scope.everywhere(), Status.ACTIVE)
        result = export.sync_copilot(self.project)
        api = next(f for f in result.written if "section-src" in f.name)
        self.assertIn('applyTo: "src/**"', api.read_text())
        mine = self.root / ".github" / "instructions" / "team.instructions.md"
        mine.write_text("- hand written\n")
        self.repo.remove([self.active.id])                       # the section rule goes away ...
        export.sync_copilot(self.project)
        self.assertFalse(api.exists())                           # ... so its generated file is pruned
        self.assertTrue(mine.exists())                           # hand-written files are never touched

    def test_generated_files_are_not_imported_back(self):
        export.sync_copilot(self.project)
        stats = trainer.train(self.project, self.root / ".github" / "instructions")
        self.assertEqual((stats.files, stats.added, stats.skipped_generated), (0, 0, 1))

    def test_rules_for_unknown_sections_are_reported_not_printed(self):
        self.repo.add("Docs rule that matches no section", Scope.for_section("nowhere"), Status.ACTIVE)
        result = export.sync_copilot(self.project)
        self.assertEqual(len(result.skipped), 1)


class TestTrainer(RegisteredProject):
    def test_extract_scopes(self):
        doc = "---\napplyTo: \"**/*.{ts,tsx}\"\n---\n# TS\n- Never use `any`; prefer unknown\n"
        out = trainer.extract(doc, ["src/api", "src/ui"])
        self.assertEqual(out[0].scope, Scope.for_globs("**/*.{ts,tsx}"))
        md = "# Rules\n- Keep commits small and focused\n\n## API layer\n- Validate input at the boundary\n  and return typed errors\n```\n- code bullet ignored\n```\n"
        out = trainer.extract(md, ["src/api", "src/ui"])
        self.assertEqual([o.scope.kind for o in out], [ScopeKind.GLOBAL, ScopeKind.SECTION])
        self.assertEqual(out[1].scope.section, "src/api")
        self.assertIn("return typed errors", out[1].text)
        self.assertEqual(len(out), 2)

    def test_train_a_folder_is_idempotent(self):
        docs = self.scratch / "docs"
        self.write("docs/a.md", "# Standards\n- Write tests for every bug fix\n- Log errors with context\n")
        self.write("docs/b.txt", "Always handle errors explicitly instead of swallowing them.\n")
        before = len(self.repo.all())
        first = trainer.train(self.project, docs)
        self.assertEqual((first.files, first.added), (2, 3))
        second = trainer.train(self.project, docs)
        self.assertEqual((second.added, second.duplicate), (0, 3))
        self.assertEqual(len(self.repo.all()), before + 3)

    def test_scope_override_and_status(self):
        doc = self.write("one.md", "- Prefer small pure functions\n")
        trainer.train(self.project, doc, scope_override=Scope.for_section("src"), status=Status.PENDING)
        rule = [r for r in self.repo.all() if r.text.startswith("Prefer small pure")][0]
        self.assertEqual((rule.scope.key, rule.status, rule.source), ("section:src", Status.PENDING, "one.md"))

    def test_stats_merge(self):
        total = TrainStats(files=1, added=2)
        total.merge(TrainStats(files=2, duplicate=3, skipped_generated=1))
        self.assertEqual((total.files, total.added, total.duplicate, total.skipped_generated), (3, 2, 3, 1))


class TestProjects(TempHome):
    def test_claim_save_get_roundtrip_keeps_creation_date(self):
        root = self.scratch / "p"
        root.mkdir()
        p = projects.claim("p", root)
        p.save()
        created = projects.get("p").created
        self.assertTrue(created)
        again = projects.claim("p", root)
        self.assertEqual(again.created, created)

    def test_name_taken_by_another_root(self):
        a, b = self.scratch / "a", self.scratch / "b"
        a.mkdir(); b.mkdir()
        projects.claim("x", a).save()
        with self.assertRaises(projects.NameTaken):
            projects.claim("x", b)
        with self.assertRaises(ValueError):
            projects.claim("../evil", b)

    def test_get_and_require(self):
        self.assertIsNone(projects.get("ghost"))
        self.assertIsNone(projects.get("../bad"))
        with self.assertRaises(projects.UnknownProject):
            projects.require("ghost")

    def test_find_for_path_prefers_the_deepest_root(self):
        outer, inner = self.scratch / "mono", self.scratch / "mono" / "svc"
        inner.mkdir(parents=True)
        projects.claim("mono", outer).save()
        projects.claim("svc", inner).save()
        self.assertEqual(projects.find_for_path(str(inner / "a.py")).name, "svc")
        self.assertEqual(projects.find_for_path(str(outer / "b.py")).name, "mono")
        self.assertIsNone(projects.find_for_path(str(self.scratch / "elsewhere" / "c.py")))

    def test_missing_created_field_is_tolerated(self):
        root = self.scratch / "old"
        root.mkdir()
        store.save_json(store.project_dir("old") / "project.json", {"name": "old", "root": str(root)})
        self.assertEqual(projects.get("old").created, "")
        self.assertEqual(projects.claim("old", root).name, "old")


class TestStoreHome(unittest.TestCase):
    def test_default_and_override(self):
        with tempfile.TemporaryDirectory() as h:
            saved = {k: os.environ.pop(k, None) for k in ("LORE_HOME", "HOME")}
            self.addCleanup(lambda: [os.environ.__setitem__(k, v) if v is not None else os.environ.pop(k, None) for k, v in saved.items()])
            os.environ["HOME"] = h
            self.assertEqual(store.home(), Path(h) / ".lore")
            os.environ["LORE_HOME"] = "/x/elsewhere"
            self.assertEqual(store.home(), Path("/x/elsewhere"))

    def test_names_are_validated(self):
        for bad in ("", "..", "../x", "a/b", ".hidden", "-x"):
            with self.assertRaises(ValueError):
                store.validate_name(bad)
        self.assertEqual(store.validate_name("my-app_2.0"), "my-app_2.0")


if __name__ == "__main__":
    unittest.main()
