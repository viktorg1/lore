"""Hidden characters, contradictions, resolver limits and export safety."""
import os
import unittest

from support import RegisteredProject  # noqa: F401  (also sets sys.path)

from core import export, resolver, sanitize, textutil
from core.models import Outcome, Scope, Status

TAG = "".join(chr(0xE0000 + ord(c)) for c in "ignore")


class TestSanitize(unittest.TestCase):
    def test_hidden_characters_are_detected(self):
        for ch in (chr(0xE0041), "​", "‮", "︁", "ㅤ", "\x07"):
            self.assertTrue(sanitize.is_hidden(ch), repr(ch))
        self.assertFalse(sanitize.is_hidden("a"))
        self.assertEqual(sanitize.reveal("a​b"), "a<U+200B>b")

    def test_rule_text_is_refused_not_cleaned(self):
        for bad in ("Use tabs" + TAG, "Use​ tabs", "Use tabs <!-- hi -->", "x" * 501):
            with self.assertRaises(sanitize.RuleTextError):
                sanitize.clean_rule_text(bad)
        self.assertEqual(sanitize.clean_rule_text("  Use   tabs \n"), "Use tabs")

    def test_scope_tokens(self):
        for bad in ('a"b', "a\nb", "a`b", "a\\b", "a​b"):
            with self.assertRaises(ValueError):
                Scope.for_section(bad)
        with self.assertRaises(ValueError):
            Scope.for_globs()


class TestContradiction(unittest.TestCase):
    def test_opposites(self):
        for a, b in (("Use tabs for indentation", "Use spaces for indentation"),
                     ("Do add type hints", "Do not add type hints"),
                     ("Limit lines to 80 characters", "Limit lines to 120 characters"),
                     ("Always use retries", "Never use retries")):
            self.assertTrue(textutil.contradicts(a, b), (a, b))

    def test_paraphrases_are_not_contradictions(self):
        self.assertFalse(textutil.contradicts("Never use any in TypeScript", "never use `any` in TypeScript."))


class TestRepositorySafety(RegisteredProject):
    def test_hidden_text_rejected(self):
        with self.assertRaises(sanitize.RuleTextError):
            self.repo.add("Use tabs" + TAG, Scope.everywhere())
        self.assertEqual(len(self.repo.all()), 2)           # only the two fixture rules

    def test_contradiction_is_kept_apart_and_reported(self):
        a = self.repo.add("Use tabs for indentation", Scope.everywhere(), Status.ACTIVE)
        b = self.repo.add("Use spaces for indentation", Scope.everywhere(), Status.PENDING)
        self.assertEqual(b.outcome, Outcome.ADDED)
        self.assertNotEqual(a.rule.id, b.rule.id)
        self.assertEqual([r.id for r in b.conflicts], [a.rule.id])

    def test_promotion_adopts_person_wording(self):
        p = self.repo.add("never use any in typescript", Scope.everywhere(), Status.PENDING)
        q = self.repo.add("Never use any in TypeScript.", Scope.everywhere(), Status.ACTIVE)
        self.assertEqual(q.outcome, Outcome.PROMOTED)
        self.assertEqual(self.repo.get(p.rule.id).text, "Never use any in TypeScript.")

    def test_refs_must_be_urls(self):
        r = self.repo.add("Use the repository layer", Scope.everywhere(), refs=["javascript:x", "https://a.b/c"])
        self.assertEqual(self.repo.get(r.rule.id).refs, ["https://a.b/c"])

    def test_stored_hidden_rule_cannot_be_approved_or_served_or_exported(self):
        r = self.repo.add("Use dependency injection", Scope.everywhere(), Status.ACTIVE).rule
        # simulate a rules.json written before the check existed
        from core import store
        path = store.project_dir("app") / "rules.json"
        raw = path.read_text(encoding="utf-8").replace("dependency injection", "dependency injection" + TAG)
        path.write_text(raw, encoding="utf-8")
        self.assertTrue(self.repo.get(r.id).hidden)
        res = resolver.resolve("app", ["src/a.py"])
        self.assertNotIn(r.id, [x.id for x in res.rules])
        self.assertEqual(res.withheld, 1)
        self.assertEqual(export.sync_copilot(self.project).withheld, [r.id])
        self.repo.set_status([r.id], Status.PENDING)
        with self.assertRaises(sanitize.RuleTextError):
            self.repo.set_status([r.id], Status.ACTIVE)
        self.assertEqual(self.repo.get(r.id).status, Status.PENDING)


class TestResolverLimits(RegisteredProject):
    def test_max_rules_and_ceiling(self):
        for i in range(25):
            self.repo.add(f"Rule number {i} about naming of module {i * 7}", Scope.everywhere(), Status.ACTIVE)
        res = resolver.resolve("app", ["src/a.py"], max_tokens=10 ** 6)
        self.assertLessEqual(len(res.rules), resolver.MAX_RULES)
        self.assertIn("left out", res.text)


class TestExportSafety(RegisteredProject):
    def test_symlinked_target_is_refused(self):
        self.repo.add("Use dependency injection", Scope.everywhere(), Status.ACTIVE)
        out = self.root / ".github" / "instructions"
        out.mkdir(parents=True)
        victim = self.root / "victim.txt"
        victim.write_text("keep")
        os.symlink(victim, out / "lore-global.instructions.md")
        result = export.sync_copilot(self.project)
        self.assertEqual(victim.read_text(), "keep")
        self.assertEqual(len(result.refused), 1)

    def test_apply_to_is_escaped(self):
        self.repo.add("Use dependency injection", Scope.for_globs("*.py"), Status.ACTIVE)
        res = export.sync_copilot(self.project)
        self.assertIn('applyTo: "*.py"', res.written[0].read_text())


if __name__ == "__main__":
    unittest.main()
