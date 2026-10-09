import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import discovery, ecosystems, rules, store, trainer  # noqa: E402
from mapper import section_of  # noqa: E402


def run(*args, stdin=None, env=None):
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True,
                          input=stdin, env=env, cwd=ROOT)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = Path(self.tmp.name)
        self.mem = t / "mem"
        self.proj = t / "demoproj"
        for f in ["src/api/users.py", "src/ui/App.tsx", "README.md", "node_modules/x/y.js"]:
            p = self.proj / f
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("x")
        self.env = {**os.environ, "LORE_HOME": str(self.mem)}
        os.environ["LORE_HOME"] = str(self.mem)
        self.addCleanup(os.environ.pop, "LORE_HOME", None)


class TestMemorize(Base):
    def test_default_name_and_map(self):
        r = run("memorize.py", "--path", self.proj, env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        amap = json.loads((self.mem / "demoproj" / "map.json").read_text())
        self.assertEqual(set(amap["sections"]), {"root", "src/api", "src/ui"})  # node_modules ignored
        self.assertEqual(amap["sections"]["src/api"]["languages"], {"python": 1})

    def test_explicit_name_and_rejects_bad_input(self):
        self.assertEqual(run("memorize.py", "--path", self.proj, "--name", "other", env=self.env).returncode, 0)
        self.assertTrue((self.mem / "other" / "project.json").exists())
        self.assertNotEqual(run("memorize.py", "--path", self.proj, "--name", "../evil", env=self.env).returncode, 0)
        self.assertNotEqual(run("memorize.py", "--path", self.proj / "nope", env=self.env).returncode, 0)
        self.assertNotEqual(run("memorize.py", env=self.env).returncode, 0)  # --path required

    def test_name_collision_with_other_root(self):
        run("memorize.py", "--path", self.proj, env=self.env)
        other = Path(self.tmp.name) / "elsewhere"
        other.mkdir()
        r = run("memorize.py", "--path", other, "--name", "demoproj", env=self.env)
        self.assertEqual(r.returncode, 2)

    def test_imports_existing_instruction_files_once(self):
        gh = self.proj / ".github"
        gh.mkdir()
        (gh / "copilot-instructions.md").write_text("- Always use type hints in Python code\n")
        run("memorize.py", "--path", self.proj, env=self.env)
        run("memorize.py", "--path", self.proj, env=self.env)
        self.assertEqual(len(rules.load("demoproj")), 1)


class TestRules(Base):
    def setUp(self):
        super().setUp()
        run("memorize.py", "--path", self.proj, env=self.env)

    def test_glob_matching(self):
        self.assertTrue(rules.glob_match("**/*.{ts,tsx}", "src/ui/App.tsx"))
        self.assertTrue(rules.glob_match("*.py", "src/api/users.py"))
        self.assertTrue(rules.glob_match("src/api/**", "src/api/v1/x.py"))
        self.assertFalse(rules.glob_match("src/api/**", "src/ui/App.tsx"))
        self.assertEqual(rules.split_globs("*.{ts,tsx}, **/*.py"), ["*.{ts,tsx}", "**/*.py"])

    def test_section_of(self):
        self.assertEqual(section_of("README.md"), "root")
        self.assertEqual(section_of("src/api/a/b.py"), "src/api")
        self.assertEqual(section_of("src/main.py"), "src")
        self.assertEqual(section_of("docs/a.md"), "docs")

    def test_resolve_scopes_and_pending_excluded(self):
        n = "demoproj"
        rules.add_rule(n, "Prefer small functions everywhere", {"type": "global"}, "active")
        rules.add_rule(n, "Validate input at the route boundary", {"type": "section", "value": "api"}, "active")
        rules.add_rule(n, "Type annotate all Python functions", rules.parse_scope("glob:*.py"), "active")
        rules.add_rule(n, "Pending rule never shown", {"type": "global"}, "pending")
        res = rules.resolve(n, ["src/api/users.py"])
        texts = [r["text"] for r in res["rules"]]
        self.assertEqual(len(texts), 3)
        self.assertNotIn("Pending rule never shown", texts)
        self.assertEqual(texts[0], "Type annotate all Python functions")  # most specific first
        ui = [r["text"] for r in rules.resolve(n, ["src/ui/App.tsx"])["rules"]]
        self.assertEqual(ui, ["Prefer small functions everywhere"])

    def test_budget_truncates(self):
        n = "demoproj"
        texts = ["Use dependency injection for all service classes", "Log errors with request context attached",
                 "Keep database migrations reversible", "Prefer composition over inheritance in domain models",
                 "Wrap third party SDK calls in an adapter module", "Never commit generated protobuf output",
                 "Name boolean flags with is or has prefixes", "Document public functions with a one line summary"]
        for t in texts:
            rules.add_rule(n, t, {"type": "global"}, "active")
        self.assertEqual(len(rules.load(n)), len(texts))
        res = rules.resolve(n, ["README.md"], max_tokens=60)
        self.assertGreater(res["omitted"], 0)
        self.assertLess(len(res["rules"]), len(rules.load(n)))

    def test_dedupe_and_promote(self):
        n = "demoproj"
        a, o1 = rules.add_rule(n, "Never use any in TypeScript", {"type": "global"}, "pending")
        b, o2 = rules.add_rule(n, "never use `any` in TypeScript.", {"type": "global"}, "active")
        self.assertEqual((o1, o2, a["id"]), ("added", "promoted", b["id"]))
        self.assertEqual(len(rules.load(n)), 1)

    def test_sync_writes_and_prunes_generated_files_only(self):
        n = "demoproj"
        rules.add_rule(n, "Validate input at the route boundary", {"type": "section", "value": "api"}, "active")
        rules.add_rule(n, "Prefer small functions everywhere", {"type": "global"}, "active")
        files = rules.sync_copilot(n, self.proj)
        api = next(f for f in files if "section-api" in f)
        self.assertIn('applyTo: "src/api/**"', Path(api).read_text())
        mine = self.proj / ".github" / "instructions" / "team.instructions.md"
        mine.write_text("- hand written\n")
        rules.set_status(n, [r["id"] for r in rules.load(n) if r["scope"]["type"] == "section"], None)
        rules.sync_copilot(n, self.proj)
        self.assertFalse(Path(api).exists())
        self.assertTrue(mine.exists())
        # generated files are not re-imported as rules
        self.assertEqual(trainer.train(n, self.proj / ".github" / "instructions")["added"], 1)  # only team.instructions.md


class TestTrainer(Base):
    def setUp(self):
        super().setUp()
        run("memorize.py", "--path", self.proj, env=self.env)

    def test_extract_scopes(self):
        doc = (
            "---\napplyTo: \"**/*.{ts,tsx}\"\n---\n# TS\n- Never use `any`; prefer unknown\n"
        )
        out = trainer.extract(doc, ["src/api", "src/ui"])
        self.assertEqual(out[0]["scope"], {"type": "glob", "globs": ["**/*.{ts,tsx}"]})
        md = "# Rules\n- Keep commits small and focused\n\n## API layer\n- Validate input at the boundary\n  and return typed errors\n```\n- code bullet ignored\n```\n"
        out = trainer.extract(md, ["src/api", "src/ui"])
        self.assertEqual([o["scope"]["type"] for o in out], ["global", "section"])
        self.assertEqual(out[1]["scope"]["value"], "src/api")
        self.assertIn("return typed errors", out[1]["text"])
        self.assertEqual(len(out), 2)

    def test_train_cli_folder_and_idempotent(self):
        docs = Path(self.tmp.name) / "docs"
        docs.mkdir()
        (docs / "a.md").write_text("# Standards\n- Write tests for every bug fix\n- Log errors with context\n")
        (docs / "b.txt").write_text("Always handle errors explicitly instead of swallowing them.\n")
        r = run("train.py", "--name", "demoproj", "--from", docs, env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(rules.load("demoproj")), 3)
        run("train.py", "--name", "demoproj", "--from", docs, env=self.env)
        self.assertEqual(len(rules.load("demoproj")), 3)
        self.assertNotEqual(run("train.py", "--name", "ghost", "--from", docs, env=self.env).returncode, 0)


class TestDiscover(Base):
    def test_finds_lopsided_conventions_and_ignores_vendored(self):
        p = self.proj
        (p / ".editorconfig").write_text("[*]\nindent_style = space\nindent_size = 4\nend_of_line = lf\n")
        (p / "composer.json").write_text(json.dumps({"require": {"php": "^8.3", "laravel/framework": "^11"}, "require-dev": {"pestphp/pest": "^3"}}))
        for i in range(6):
            (p / "src/ui").mkdir(parents=True, exist_ok=True)
            (p / f"src/ui/Card{i}.vue").write_text('<script setup lang="ts">\nconst a = 1;\n</script>\n')
        (p / "public/js").mkdir(parents=True)
        for i in range(6):  # vendored double-quoted JS must not influence the quote rule
            (p / f"public/js/v{i}.js").write_text('var a = "x";\n' * 50)
        texts = {c["text"]: c for c in discovery.discover(p)}
        joined = "\n".join(texts)
        self.assertIn("Formatting for all files: indent with 4 spaces; LF line endings.", texts)
        self.assertIn("Write Vue components with <script setup>.", texts)
        self.assertIn("Write PHP tests with Pest", joined)
        self.assertIn("Target PHP ^8.3", joined)
        self.assertNotIn("double quotes", joined)
        self.assertTrue(any("PascalCase" in t for t in texts))

    def test_cli_preview_saves_nothing_then_saves_pending(self):
        run("memorize.py", "--path", self.proj, env=self.env)
        (self.proj / "composer.json").write_text(json.dumps({"require": {"laravel/framework": "^11"}}))
        r = run("discover.py", "--name", "demoproj", env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(rules.load("demoproj"), [])
        run("discover.py", "--name", "demoproj", "--save", env=self.env)
        saved = rules.load("demoproj")
        self.assertTrue(saved and all(x["status"] == "pending" and x["source"] == "discover" for x in saved))
        run("discover.py", "--name", "demoproj", "--save", env=self.env)
        self.assertEqual(len(rules.load("demoproj")), len(saved))  # idempotent


class TestEcosystems(Base):
    def collect(self, files):
        for rel, text in files.items():
            fp = self.proj / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(text)
        return {c["text"]: c for c in ecosystems.collect(self.proj)}

    def test_python(self):
        out = self.collect({
            "requirements.txt": "fastapi==0.110\npytest>=8\n# comment\n-r other.txt\n",
            "pyproject.toml": '[project]\nrequires-python = ">=3.11"\ndependencies = ["pydantic>=2", "sqlalchemy[asyncio]"]\n[tool.ruff]\nline-length = 100\n',
        })
        joined = "\n".join(out)
        for needle in ("FastAPI", "pydantic", "SQLAlchemy", "pytest", "ruff", "Target Python >=3.11"):
            self.assertIn(needle, joined)

    def test_go_and_rust(self):
        out = "\n".join(self.collect({
            "go.mod": "module x\n\ngo 1.22\n\nrequire (\n\tgithub.com/gin-gonic/gin v1.9.1\n\tgithub.com/stretchr/testify v1.8.0\n)\n",
            "Cargo.toml": '[package]\nedition = "2021"\n[dependencies]\ntokio = { version = "1" }\nanyhow = "1"\n[dev-dependencies.mockall]\nversion = "0.1"\n',
            ".golangci.yml": "linters: {}\n",
        }))
        for needle in ("Target Go 1.22", "Gin", "testify", "Rust edition 2021", "tokio", "anyhow", "golangci-lint"):
            self.assertIn(needle, out)

    def test_jvm_dotnet_ruby_make(self):
        out = "\n".join(self.collect({
            "pom.xml": "<project><properties><java.version>21</java.version></properties><dependencies><dependency><artifactId>spring-boot-starter-web</artifactId></dependency></dependencies></project>",
            "build.gradle.kts": 'dependencies { testImplementation("org.junit.jupiter:junit-jupiter:5.10.0") }\n',
            "App/App.csproj": '<Project><PropertyGroup><TargetFramework>net8.0</TargetFramework><Nullable>enable</Nullable></PropertyGroup><ItemGroup><PackageReference Include="Serilog" Version="3" /></ItemGroup></Project>',
            "Gemfile": "ruby '3.3.0'\ngem 'rails'\ngem \"rspec-rails\"\n",
            "Makefile": "lint:\n\techo\ntest:\n\techo\n",
        }))
        for needle in ("Target Java 21", "Spring Boot web", "JUnit 5", "Target net8.0", "Nullable reference", "Serilog",
                       "Target Ruby 3.3.0", "Rails", "RSpec", "`make lint`"):
            self.assertIn(needle, out)

    def test_absent_markers_need_enough_clean_files(self):
        for i in range(10):
            (self.proj / "src/api").mkdir(parents=True, exist_ok=True)
            (self.proj / f"src/api/m{i}.rs").write_text("fn f() -> Result<(), E> { g()?; Ok(()) }\n")
        out = [c["text"] for c in discovery.discover(self.proj)]
        self.assertIn("Avoid .unwrap() in non-test code; propagate errors with `?`.", out)
        (self.proj / "src/api/bad.rs").write_text("fn f() { g().unwrap(); }\n")
        (self.proj / "src/api/bad2.rs").write_text("fn f() { g().unwrap(); }\n")
        out = [c["text"] for c in discovery.discover(self.proj)]
        self.assertNotIn("Avoid .unwrap() in non-test code; propagate errors with `?`.", out)


class TestStoreHome(unittest.TestCase):
    def test_default_and_override(self):
        with tempfile.TemporaryDirectory() as h:
            saved = {k: os.environ.pop(k, None) for k in ("LORE_HOME", "HOME")}
            self.addCleanup(lambda: [os.environ.__setitem__(k, v) if v is not None else os.environ.pop(k, None) for k, v in saved.items()])
            os.environ["HOME"] = h
            self.assertEqual(store.home(), Path(h) / ".lore")
            os.environ["LORE_HOME"] = "/x/elsewhere"
            self.assertEqual(store.home(), Path("/x/elsewhere"))


class TestMCP(Base):
    def setUp(self):
        super().setUp()
        run("memorize.py", "--path", self.proj, env=self.env)
        rules.add_rule("demoproj", "Validate input at the route boundary", {"type": "section", "value": "api"}, "active")

    def rpc(self, *msgs):
        r = subprocess.run([sys.executable, str(ROOT / "mcp_server.py")], capture_output=True, text=True,
                           input="\n".join(json.dumps(m) for m in msgs) + "\n", env=self.env, cwd="/")
        self.assertEqual(r.returncode, 0, r.stderr)
        return [json.loads(l) for l in r.stdout.splitlines()]

    def test_protocol_and_tools(self):
        f = str(self.proj / "src/api/users.py")
        out = self.rpc(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "get_rules", "arguments": {"paths": [f]}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "record_feedback",
             "arguments": {"rule": "Return typed errors from handlers", "paths": [f], "evidence": "user said so"}}},
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "get_rules", "arguments": {"paths": ["/elsewhere/x.py"]}}},
            {"jsonrpc": "2.0", "id": 6, "method": "nope"},
        )
        self.assertEqual(len(out), 6)  # notification gets no reply
        self.assertEqual(out[0]["result"]["protocolVersion"], "2025-03-26")
        self.assertEqual({t["name"] for t in out[1]["result"]["tools"]}, {"get_rules", "record_feedback"})
        self.assertIn("Validate input at the route boundary", out[2]["result"]["content"][0]["text"])
        self.assertIn("pending rule", out[3]["result"]["content"][0]["text"])
        pend = [r for r in rules.load("demoproj") if r["status"] == "pending"]
        self.assertEqual(pend[0]["scope"], {"type": "section", "value": "src/api"})
        self.assertIn("No lore project", out[4]["result"]["content"][0]["text"])
        self.assertEqual(out[5]["error"]["code"], -32601)


if __name__ == "__main__":
    unittest.main()
