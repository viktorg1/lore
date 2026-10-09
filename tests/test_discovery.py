import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mapper  # noqa: E402
from discovery import (AbsentMarker, ChoiceMarker, Discoverer, FileMarker,  # noqa: E402
                                    OccurrenceMarker, Thresholds, discover, marker_from_dict, registry)


def all_markers():
    for lang in registry.languages().values():
        for m in lang.markers:
            yield f"language:{lang.name}", m
    for fw in registry.frameworks():
        for m in fw.markers:
            yield f"framework:{fw.name}", m


def find(marker_id):
    return next(m for _, m in all_markers() if m.id == marker_id)


def patterns(m):
    """Every regex a marker carries, by role."""
    if isinstance(m, FileMarker):
        return {"has": m.has, **({"when": m.when} if m.when else {})}
    if isinstance(m, OccurrenceMarker):
        return {"total": m.total, "has": m.has}
    if isinstance(m, AbsentMarker):
        return {"bad": m.bad}
    return {o.label: o.pattern for o in m.options}


class TestRegistry(unittest.TestCase):
    def test_every_code_language_is_registered(self):
        self.assertEqual(set(registry.languages()), {
            "php", "javascript", "typescript", "vue", "svelte", "python", "go", "ruby", "java", "kotlin",
            "csharp", "rust", "scala", "dart", "elixir", "lua", "swift", "c", "cpp"})

    def test_extensions_agree_with_the_mapper(self):
        for lang in registry.languages().values():
            for ext in lang.extensions:
                self.assertEqual(mapper.LANGS.get("." + ext), lang.name, f"{lang.name}.{ext}")

    def test_requested_frameworks_present(self):
        names = {f.name for f in registry.frameworks()}
        for expected in ("React", "Express", "Vue", "Laravel", "Django", "Gin", "Rails", "Spring Boot",
                         "ASP.NET Core", "Axum", "Angular", "SvelteKit", "Ktor", "Play", "Phoenix",
                         "Flutter", "LOVE", "SwiftUI", "Qt"):
            self.assertIn(expected, names)

    def test_marker_ids_unique_and_well_formed(self):
        ids = [m.id for _, m in all_markers()]
        self.assertEqual(len(ids), len(set(ids)), [i for i in ids if ids.count(i) > 1])
        for owner, m in all_markers():
            self.assertTrue(m.glob and m.id, owner)
            if isinstance(m, ChoiceMarker):
                self.assertGreaterEqual(len(m.options), 2, m.id)
                self.assertTrue(any(o.rule for o in m.options), m.id)
            else:
                self.assertTrue(m.rule, m.id)

    def test_every_regex_compiles(self):
        for owner, m in all_markers():
            for role, pat in patterns(m).items():
                try:
                    re.compile(pat, re.M)
                except re.error as e:
                    self.fail(f"{m.id} ({owner}) {role}: {e}")

    def test_every_framework_has_markers_and_a_detector(self):
        for fw in registry.frameworks():
            self.assertTrue(fw.markers, fw.name)
            self.assertTrue(fw.deps or fw.signatures, fw.name)


# (marker id, role, text that must match, text that must not)
REGEX_CASES = [
    ("js-loose-equality", "bad", "if (a == b) {", "if (a === b) {"),
    ("js-loose-equality", "bad", "if (a != b) {", "if (a !== b) {"),
    ("ts-non-null", "bad", "const n = user!.name;", "if (a !== b || !flag) {"),
    ("php-error-suppress", "bad", "@unlink($file);", "mail('a@example.com', 'x');"),
    ("php-array-fn", "bad", "$a = array('x');", "$b = array_map($f, $x); function f(array $x) {}"),
    ("py-print", "bad", "    print('x')", "    pprint(x)\n    # print(x)"),
    ("py-bare-except", "bad", "    except:\n", "    except ValueError:\n"),
    ("py-mutable-default", "bad", "def f(a, b=[]):", "def f(a, b=None):"),
    ("py-string-format", "% formatting", 'msg = "%s items" % n', 'msg = "100%"'),
    ("py-string-format", "f-strings", 'x = f"hi {name}"', 'x = buf"raw"'),
    ("py-generics", "builtin generics", "x: list[int] = []", "y = mylist[0]"),
    ("go-empty-interface", "bad", "func f(x interface{}) {", "func f(x any) {"),
    ("go-fmt-print", "bad", 'fmt.Println("x")', 'fmt.Sprintf("x")'),
    ("swift-force-unwrap", "bad", "let n = name!.count", "if x != y { }\nif !flag { }"),
    ("kt-bang-bang", "bad", "val n = name!!.length", "if (a != b) {}"),
    ("c-unsafe-libc", "bad", "strcpy(dst, src);", "strncpy(dst, src, n); snprintf(b, n, f);"),
    ("rs-unwrap", "bad", "let v = x.unwrap();", "let v = x?;"),
    ("java-print-stack-trace", "bad", "e.printStackTrace();", "log.error(\"x\", e);"),
    ("django-views", "class-based views", "class UserList(LoginRequiredMixin, ListView):", "def user_list(request):"),
    ("django-views", "function-based views", "def user_list(request):", "class UserList(ListView):"),
    ("spring-injection", "field @Autowired", "@Autowired\n    private UserService userService;", "private final UserService userService;"),
    ("spring-injection", "constructor injection", "    private final UserService userService;", "@Autowired\n private UserService s;"),
    ("react-component-kind", "function components", "export default function Home() {", "function useThing() {"),
    ("react-component-kind", "function components", "const Button = ({ label }) => (", "const handler = (e) => foo(e);"),
    ("react-component-kind", "class components", "class App extends React.Component {", "class Store {"),
    ("vue-component-tags", "PascalCase tags", "<MyButton :x=\"1\" />", "<div class=\"a\">"),
    ("vue-component-tags", "kebab-case tags", "<my-button />", "<div></div>"),
    ("rb-hash-syntax", "key: value", "foo(name: 'x')", "a = b ? c : d"),
    ("express-handler-style", "async handlers", "router.get('/x', async (req, res) => {", "router.get('/x', handler)"),
]


class TestRegexPrecision(unittest.TestCase):
    def test_cases(self):
        for mid, role, good, bad in REGEX_CASES:
            pat = re.compile(patterns(find(mid))[role], re.M)
            self.assertTrue(pat.search(good), f"{mid}/{role} should match: {good!r}")
            self.assertFalse(pat.search(bad), f"{mid}/{role} should NOT match: {bad!r}")


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def many(self, pattern, n, text):
        for i in range(n):
            self.write(pattern.replace("{i}", str(i)), text.replace("{i}", str(i)))

    def texts(self, **kw):
        return [c.text for c in discover(self.root, **kw)]


class TestFrameworkMarkers(Fixture):
    def test_laravel_fires_only_when_laravel_is_a_dependency(self):
        self.many("app/Models/M{i}.php", 6, "<?php\nclass M{i} extends Model { protected $fillable = []; }\n")
        want = "Declare $fillable (or $guarded) explicitly on every Eloquent model."
        self.assertNotIn(want, self.texts())  # models alone are not enough
        self.write("composer.json", json.dumps({"require": {"laravel/framework": "^11"}}))
        cands = {c.text: c for c in discover(self.root)}
        self.assertIn(want, cands)
        self.assertEqual(cands[want].kind, "framework")
        self.assertIn("Laravel: laravel/framework in composer.json", cands[want].evidence)

    def test_laravel_choice_marker_picks_the_dominant_style(self):
        self.write("composer.json", json.dumps({"require": {"laravel/framework": "^11"}}))
        self.write("app/Http/Controllers/A.php", "<?php\n" + "use App\\Http\\Requests\\StoreThing;\n" * 18)
        self.write("app/Http/Controllers/B.php", "<?php\n$request->validate([]);\n")
        out = self.texts()
        self.assertIn("Validate controller input with dedicated Form Request classes, not inline.", out)
        self.assertNotIn("Validate request input inline with $request->validate([...]) in controllers.", out)

    def test_react_function_components(self):
        self.write("package.json", json.dumps({"dependencies": {"react": "^18"}}))
        self.many("src/C{i}.tsx", 16, "export default function C{i}() { return null; }\n")
        self.assertIn("Write function components with hooks; do not write class components.", self.texts())

    def test_express_router(self):
        self.write("package.json", json.dumps({"dependencies": {"express": "^4"}}))
        self.write("src/routes.js", "const r = express.Router();\n" * 16)
        self.assertIn("Define routes on express.Router() modules and mount them with app.use().", self.texts())

    def test_django_model_str(self):
        self.write("requirements.txt", "Django==5.0\n")
        self.many("app{i}/models.py", 4, "class A(models.Model):\n    def __str__(self):\n        return ''\n")
        self.assertIn("Define __str__ on every model.", self.texts())

    def test_spring_constructor_injection(self):
        self.write("pom.xml", "<project><dependencies><dependency><artifactId>spring-boot-starter-web</artifactId></dependency></dependencies></project>")
        self.many("src/main/java/S{i}.java", 16, "class S{i} {\n    private final Repo repo;\n}\n")
        self.assertTrue(any("through the constructor" in t for t in self.texts()))

    def test_gin_bind_style(self):
        self.write("go.mod", "module x\n\ngo 1.22\n\nrequire github.com/gin-gonic/gin v1.9.1\n")
        self.write("h.go", "package h\n" + "func f(c *gin.Context) { c.ShouldBindJSON(&x) }\n" * 16)
        self.assertIn("Bind requests with ShouldBind*() and handle the error yourself.", self.texts())

    def test_rails_dependent(self):
        self.write("Gemfile", "gem 'rails'\n")
        self.many("app/models/m{i}.rb", 6, "class M{i} < ApplicationRecord\n  has_many :things, dependent: :destroy\nend\n")
        self.assertIn("Declare dependent: on every has_many/has_one association.", self.texts())

    def test_framework_detected_from_source_signature(self):
        self.many("App/V{i}.swift", 4, "import SwiftUI\n@Observable class M{i} {}\n" + "@Observable class N {}\n" * 5)
        self.assertIn("Model state with the @Observable macro.", self.texts())

    def test_undetected_framework_stays_silent(self):
        self.many("src/C{i}.tsx", 16, "export default function C{i}() { return null; }\n")  # React code, no react dependency
        self.assertNotIn("Write function components with hooks; do not write class components.", self.texts())


class TestLanguageMarkers(Fixture):
    def test_vanilla_markers_without_any_framework(self):
        self.many("lib/m{i}.py", 10, "from __future__ import annotations\n\n\ndef f{i}(a: int) -> int:\n    return a\n")
        out = self.texts()
        self.assertIn("Start Python modules with `from __future__ import annotations`.", out)
        self.assertIn("Use the logging module, not print(), in application code.", out)  # 10/10 files are print-free

    def test_choice_below_threshold_is_not_a_rule(self):
        self.many("src/a{i}.js", 8, "import x from 'y';\n" * 2 + "const z = require('q');\n" * 2)
        self.assertFalse([t for t in self.texts() if "ES modules" in t or "CommonJS" in t])

    def test_absent_marker_broken_by_offenders(self):
        self.many("src/ok{i}.rs", 10, "fn f() -> Result<(), E> { g()?; Ok(()) }\n")
        self.assertIn("Avoid .unwrap() in non-test code; propagate errors with `?`.", self.texts())
        self.many("src/bad{i}.rs", 2, "fn f() { g().unwrap(); }\n")
        self.assertNotIn("Avoid .unwrap() in non-test code; propagate errors with `?`.", self.texts())

    def test_test_files_do_not_count_against_absent_markers(self):
        self.many("src/ok{i}.rs", 10, "fn f() -> Result<(), E> { g()?; Ok(()) }\n")
        self.many("tests/t{i}.rs", 6, "fn t() { g().unwrap(); }\n")
        self.assertIn("Avoid .unwrap() in non-test code; propagate errors with `?`.", self.texts())


class TestExtensibility(Fixture):
    def test_marker_from_json_dict(self):
        m = marker_from_dict({"kind": "absent", "id": "x", "glob": "**/*.py", "bad": r"TODO", "rule": "No TODOs."})
        self.assertIsInstance(m, AbsentMarker)
        c = marker_from_dict({"kind": "choice", "id": "y", "glob": "**/*.py", "options": [
            {"label": "a", "pattern": "aaa", "rule": "Use a."}, {"label": "b", "pattern": "bbb"}]})
        self.assertIsInstance(c, ChoiceMarker)
        self.many("src/m{i}.py", 10, "x = 1\n")
        self.assertIn("No TODOs.", [c.text for c in discover(self.root, extra_markers=[
            {"kind": "absent", "id": "x", "glob": "**/*.py", "bad": "TODO", "rule": "No TODOs."}])])

    def test_discoverer_accepts_custom_detector_list(self):
        from discovery import Candidate, Detector

        class Fixed(Detector):
            def detect(self, project):
                return [Candidate("fixed", {"type": "global"}, "test", "config")]

        self.assertEqual([c.text for c in Discoverer(detectors=[Fixed()]).run(self.root)], ["fixed"])

    def test_thresholds_are_respected(self):
        self.many("src/ok{i}.rs", 10, "fn f() -> Result<(), E> { g()?; Ok(()) }\n")
        strict = Discoverer(Thresholds(free_ratio=1.01)).run(self.root)
        self.assertFalse([c for c in strict if "unwrap" in c.text])


if __name__ == "__main__":
    unittest.main()
