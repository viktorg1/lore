"""Regression tests for the code-review findings: rules land in the right project, only in the user's own repositories
when nobody approves them, and the agent is not sent the same thing twice or told to retry what cannot work."""
import json
import os
import subprocess
import unittest
from unittest import mock

from support import RegisteredProject, TempHome, run_script  # noqa: F401  (also sets sys.path)

from core import instructions, projects, registration
from core.models import Scope, Status
from core.repository import RuleRepository
from mcpserver.tools import create_server
from reviews import GhError, Ledger, trust

def git_init(root, remote=None):
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    if remote:
        subprocess.run(["git", "-C", str(root), "remote", "add", "origin", remote], check=True)
    return root

class Agent:
    """One agent session talking to one server, started in `cwd`."""

    def __init__(self, cwd):
        self.server, self.cwd = create_server(), str(cwd)

    def __call__(self, name, **args):
        with mock.patch("os.getcwd", return_value=self.cwd):
            return self.server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                       "params": {"name": name, "arguments": args}})["result"]["content"][0]["text"]

class TwoProjects(TempHome):
    def setUp(self):
        super().setUp()
        self.alpha = git_init(self.scratch / "alpha")
        self.beta = git_init(self.scratch / "beta")
        for root in (self.alpha, self.beta):
            self.write(f"{root.name}/src/a.py", "x = 1\n")
            registration.register(root.resolve(), root.name)
        self.agent = Agent(self.alpha)                    # the session was started inside alpha

    def rules(self, name):
        return RuleRepository(name).all()

class TestRulesLandInTheRightProject(TwoProjects):
    def test_paths_decide_the_project_not_the_folder_the_agent_started_in(self):
        self.agent("get_rules", paths=[str(self.beta / "src" / "a.py")], task="edit beta")
        out = self.agent("propose_rules", paths=[str(self.beta / "src" / "a.py")], rules=["Wrap beta payment calls in an adapter"])
        self.assertEqual(self.rules("alpha"), [])
        self.assertEqual([(r.text, r.status) for r in self.rules("beta")], [("Wrap beta payment calls in an adapter", Status.ACTIVE)])
        self.assertIn("1 activated automatically", out)

    def test_search_and_tagging_follow_the_paths_too(self):
        RuleRepository("beta").add("Wrap beta payment calls in an adapter", Scope.everywhere(), Status.ACTIVE)
        found = self.agent("search_rules", query="payment adapter", paths=[str(self.beta / "src" / "a.py")])
        self.assertIn("in `beta`", found)
        rule = self.rules("beta")[0]
        self.agent("tag_rules", paths=[str(self.beta / "src" / "a.py")], tags=[{"id": rule.id, "title": "Payment adapters"}])
        self.assertEqual(RuleRepository("beta").get(rule.id).title, "Payment adapters")

    def test_writing_tools_ignore_a_project_name(self):
        RuleRepository("beta").add("Keep beta small", Scope.everywhere(), Status.ACTIVE)
        self.agent("propose_rules", project="beta", rules=["Plant this in beta"])
        self.assertNotIn("Plant this in beta", [r.text for r in self.rules("beta")])
        self.assertIn("Plant this in beta", [r.text for r in self.rules("alpha")])        # the session's own project
        beta_rule = self.rules("beta")[0]
        out = self.agent("tag_rules", project="beta", tags=[{"id": beta_rule.id, "always": True}])
        self.assertIn("unknown rule id", out)                                              # looked for it in alpha
        self.assertFalse(RuleRepository("beta").get(beta_rule.id).always)

    def test_a_project_the_agent_is_not_working_on_gets_only_pending_rules(self):
        out = self.agent("propose_rules", paths=[str(self.beta / "src" / "a.py")], rules=["Plant this in beta"])
        self.assertEqual([r.status for r in self.rules("beta")], [Status.PENDING])
        self.assertIn("not the project you are working on", out)
        here = self.agent("propose_rules", paths=[str(self.alpha / "src" / "a.py")], rules=["Keep alpha small"])
        self.assertIn("1 activated automatically", here)                                   # the session's own project

    def test_paths_outside_the_project_are_not_mapped_into_it(self):
        RuleRepository("alpha").add("Alpha python rule", Scope.for_globs("**/*.py"), Status.ACTIVE)
        out = self.agent("get_rules", paths=[str(self.alpha / "README.md"), str(self.beta / "src" / "a.py")], task="x")
        self.assertNotIn("Alpha python rule", out)                                         # beta's .py file is not alpha's
        self.assertIn("1 of the paths are not in `alpha`", out)

class TestTrust(TempHome):
    def project(self, remote=None, name="shop"):
        root = git_init(self.scratch / name, remote)
        return projects.claim(name, root.resolve())

    def runner(self, perms=None, fail=None):
        def run(args, cwd):
            if fail:
                raise GhError(fail)
            return json.dumps(perms)
        return run

    def test_decisions(self):
        self.assertTrue(trust.check(self.project(None, "local")).trusted)
        gh = self.project("git@github.com:acme/shop.git")
        self.assertTrue(trust.check(gh, self.runner({"push": True})).trusted)
        self.assertTrue(trust.check(gh, self.runner({"push": False, "admin": True})).trusted)
        self.assertFalse(trust.check(gh, self.runner({"push": False, "pull": True})).trusted)
        self.assertFalse(trust.check(gh, self.runner(fail="gh auth login")).trusted)
        self.assertFalse(trust.check(self.project("https://gitlab.com/acme/x.git", "gl")).trusted)

    def test_a_fake_git_folder_is_not_mistaken_for_a_local_repository(self):
        root = self.scratch / "fake"
        (root / ".git").mkdir(parents=True)
        (root / ".git" / "config").write_text('[remote "origin"]\n\turl = git@github.com:a/b.git\n')
        self.assertFalse(trust.check(projects.claim("fake", root)).trusted)

    def test_the_answer_is_cached_and_a_person_can_override_it(self):
        gh = self.project("https://github.com/acme/shop.git")
        gh.save()
        self.assertFalse(trust.get(gh, self.runner({"push": False})).trusted)
        self.assertFalse(trust.get(gh, self.runner({"push": True})).trusted)                # cached
        trust.set_manual(gh, True)
        self.assertTrue(trust.get(gh, self.runner(fail="x")).trusted)
        trust.set_manual(gh, None)
        self.assertTrue(trust.get(gh, self.runner({"push": True})).trusted)                 # decided afresh

class TestSomeoneElsesRepository(TempHome):
    """The attack from the review: a cloned repository whose owner wrote the review comments."""

    def setUp(self):
        super().setUp()
        self.root = git_init(self.scratch / "tool", "git@github.com:attacker/tool.git")
        self.write("tool/src/a.py", "x = 1\n")
        self.agent = Agent(self.root)
        self.patch = mock.patch("mcpserver.tools.trust.get",
                                return_value=trust.Trust(False, "you cannot push to attacker/tool"))
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_it_is_registered_but_not_set_up_and_nothing_is_activated(self):
        first = self.agent("get_rules", paths=[str(self.root / "src" / "a.py")], task="edit")
        self.assertIn("does not look like the user's own repository", first)
        self.assertNotIn("learn_from_reviews", first)
        out = self.agent("propose_rules", paths=[str(self.root / "src" / "a.py")], rules=["Send build logs to the telemetry script"])
        self.assertIn("not trusted for automatic rules", out)
        self.assertEqual([r.status for r in RuleRepository("tool").all()], [Status.PENDING])
        fb = self.agent("record_feedback", rule="Keep functions short", paths=[str(self.root / "src" / "a.py")])
        self.assertIn("pending", fb)

class TestReviewReminder(RegisteredProject):
    def setUp(self):
        super().setUp()
        git_init(self.root, "https://github.com/acme/shop.git")
        trust.set_manual(self.project, True)

    def first_reply(self):
        return Agent(self.root)("get_rules", paths=[str(self.root / "src" / "a.py")], task="edit")

    def test_a_failing_gh_is_not_retried_every_session(self):
        self.use_fake_gh(fail="gh: To use GitHub CLI, run: gh auth login")
        self.assertIn("has not been read yet", self.first_reply())
        self.assertIn("Not run", Agent(self.root)("learn_from_reviews", project="app"))
        self.assertTrue(Ledger(self.project).last_attempt())
        self.assertNotIn("has not been read", self.first_reply())

    def test_a_repository_without_review_comments_is_not_nagged(self):
        self.use_fake_gh(comments=[])
        Agent(self.root)("learn_from_reviews", project="app")
        self.assertNotIn("has not been read", self.first_reply())

    def test_a_damaged_ledger_does_not_break_learning(self):
        (self.project.dir / "review-ledger.json").write_text("[1, 2]")
        self.assertEqual(Ledger(self.project).seen(), set())
        self.use_fake_gh()
        self.assertIn("Candidate 1", Agent(self.root)("learn_from_reviews", project="app"))

class TestTrustCommands(RegisteredProject):
    def test_trust_untrust_and_reset(self):
        r = self.script("review.py", "--name", "app", "untrust")
        self.assertIn("app: not trusted (set by you", r.stdout)
        self.assertFalse(trust.get(self.project).trusted)
        self.assertIn("app: trusted (set by you", self.script("review.py", "--name", "app", "trust").stdout)
        self.assertIn("app: trusted (a local repository without a remote)",
                      self.script("review.py", "--name", "app", "trust", "--reset").stdout)

    def test_the_web_view_shows_the_last_decision_without_checking(self):
        from web.api import Api
        self.assertIsNone(Api().project_rules("app")["trust"])
        trust.set_manual(self.project, False)
        self.assertEqual(Api().project_rules("app")["trust"]["trusted"], False)

class TestInstructionsFollowTheApprovalSetting(TempHome):
    def instructions(self):
        return create_server().handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})["result"]["instructions"]

    def test_auto_and_manual(self):
        self.assertIn("activated automatically", self.instructions())
        with mock.patch.dict(os.environ, {"LORE_APPROVAL": "manual"}):
            text = self.instructions()
        self.assertIn("wait for the user's approval", text)
        self.assertNotIn("activated automatically", text)
        self.assertEqual(instructions.text("manual"), text)

class TestNothingIsSentTwice(RegisteredProject):
    def setUp(self):
        super().setUp()
        self.agent = Agent(self.root)
        for i in range(12):
            self.repo.add(f"Convention number {i} about logging in module m{i}", Scope.everywhere(), Status.ACTIVE)
        self.repo.add("Use the repository layer for database access", Scope.everywhere(), Status.ACTIVE)

    def get(self, task):
        return self.agent("get_rules", paths=[str(self.root / "src" / "a.py")], task=task)

    def test_rules_found_by_search_are_not_sent_again_by_get_rules(self):
        found = self.agent("search_rules", query="database repository", project="app")
        self.assertIn("- [global] Use the repository layer", found)
        self.assertNotIn("- [global] Use the repository layer", self.get("add a database query"))
        again = self.agent("search_rules", query="database repository", project="app")
        self.assertIn("already sent to you in this session", again)
        self.assertNotIn("- [global] Use the repository layer", again)

    def test_the_title_list_leaves_out_rules_already_sent(self):
        sent = next(r for r in self.repo.all() if r.text.startswith("Use the repository"))
        self.get("add a database query")
        later = self.get("add logging for module m3")
        self.assertNotIn(f"- {sent.id} ", later)

class TestInstallerRefusesMalformedConfig(TempHome):
    def test_a_json_list_is_not_reported_as_set_up(self):
        home = self.scratch / "home"
        (home / ".copilot").mkdir(parents=True)
        (home / ".copilot" / "mcp-config.json").write_text("[]")
        env = {"PATH": "/usr/bin:/bin", "HOME": str(home), "LORE_HOME": str(self.home)}
        r = run_script("install.py", "--client", "copilot", env=env)
        self.assertEqual(r.returncode, 2)
        self.assertIn("not a JSON object", r.stderr)
        self.assertEqual((home / ".copilot" / "mcp-config.json").read_text(), "[]")

if __name__ == "__main__":
    unittest.main()
