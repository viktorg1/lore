"""Manifest + tooling-config readers for many ecosystems (stdlib only, regex-based).

Each reader extracts (a) dependency names, (b) language/runtime targets, (c) project scripts.
Dependencies are matched against DEPS to produce factual, scoped rules; evidence names the file.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from core.models import Scope

from .models import Candidate

SCOPES = {
    "any": "global",
    "php": "glob:**/*.php",
    "py": "glob:**/*.py",
    "js": "glob:**/*.{js,jsx,mjs,ts,tsx,vue,svelte}",
    "ts": "glob:**/*.{ts,tsx,vue}",
    "css": "glob:**/*.{css,scss,vue,tsx,jsx,html}",
    "go": "glob:**/*.go",
    "rs": "glob:**/*.rs",
    "jvm": "glob:**/*.{java,kt,kts}",
    "cs": "glob:**/*.cs",
    "rb": "glob:**/*.rb",
    "tests": "glob:**/{test,tests,spec,__tests__}/**",
}

# dependency (lowercase; artifact id / module path / package name) -> (scope key, rule text)
DEPS = {
    # PHP
    "laravel/framework": ("any", "This is a Laravel project: follow Laravel conventions (Eloquent, service container, Artisan generators)."),
    "symfony/framework-bundle": ("any", "This is a Symfony project: follow Symfony conventions (services, attributes, Doctrine)."),
    "pestphp/pest": ("tests", "Write PHP tests with Pest (it()/test() closures), not PHPUnit test classes."),
    "phpunit/phpunit": ("tests", "PHP tests use PHPUnit."),
    "laravel/pint": ("php", "Format PHP with Laravel Pint (vendor/bin/pint) before finishing."),
    "phpstan/phpstan": ("php", "The project uses PHPStan: keep new code free of PHPStan errors."),
    "larastan/larastan": ("php", "The project uses Larastan/PHPStan: keep new code free of its errors."),
    "vimeo/psalm": ("php", "The project uses Psalm: keep new code free of Psalm errors."),
    "filament/filament": ("any", "The admin UI uses Filament: add admin features as Filament resources/pages."),
    "inertiajs/inertia-laravel": ("any", "The app uses Inertia: render pages with Inertia::render() from controllers."),
    "livewire/livewire": ("any", "The app uses Livewire: build interactive UI as Livewire components."),
    # JS / TS
    "@inertiajs/vue3": ("js", "Frontend pages are Inertia + Vue components: use Inertia links/router for navigation."),
    "react": ("js", "The frontend uses React: write function components and hooks."),
    "next": ("any", "This is a Next.js project: follow its routing and data-fetching conventions."),
    "vue": ("js", "The frontend uses Vue: follow existing component patterns."),
    "nuxt": ("any", "This is a Nuxt project: follow Nuxt conventions (auto-imports, pages/, composables/)."),
    "svelte": ("js", "The frontend uses Svelte: follow existing component patterns."),
    "@angular/core": ("ts", "The frontend uses Angular: follow its module/component/service conventions."),
    "express": ("js", "The backend uses Express: follow the existing router/middleware structure."),
    "@nestjs/core": ("ts", "The backend uses NestJS: follow its module/controller/provider structure."),
    "typescript": ("ts", "The project is TypeScript: prefer precise types over `any`."),
    "zod": ("ts", "Validate external input with the project's zod schemas."),
    "@prisma/client": ("any", "Database access goes through Prisma; change schema.prisma and migrate, don't hand-write SQL."),
    "drizzle-orm": ("any", "Database access goes through Drizzle ORM."),
    "@reduxjs/toolkit": ("js", "Application state uses Redux Toolkit slices."),
    "@tanstack/react-query": ("js", "Server state is fetched with TanStack Query."),
    "tailwindcss": ("css", "Style with Tailwind utility classes (the project's CSS framework)."),
    "@playwright/test": ("any", "End-to-end tests use Playwright; add or update specs for user-facing flows."),
    "cypress": ("any", "End-to-end tests use Cypress."),
    "vitest": ("js", "Unit tests use Vitest."),
    "jest": ("js", "Unit tests use Jest."),
    "mocha": ("js", "Unit tests use Mocha."),
    "eslint": ("js", "Code must pass ESLint with the project config."),
    "prettier": ("js", "Format JS/TS/Vue with Prettier using the project config."),
    "@biomejs/biome": ("js", "Lint and format with Biome using the project config."),
    "stylelint": ("css", "Styles must pass stylelint with the project config."),
    # Python
    "django": ("any", "This is a Django project: follow Django conventions (apps, models, migrations)."),
    "fastapi": ("py", "The API uses FastAPI: declare request/response models with pydantic."),
    "flask": ("py", "The web app uses Flask: follow the existing blueprint structure."),
    "pydantic": ("py", "Use pydantic models for structured/validated data."),
    "sqlalchemy": ("py", "Database access goes through SQLAlchemy."),
    "alembic": ("py", "Schema changes are Alembic migrations."),
    "celery": ("py", "Background work runs as Celery tasks."),
    "pytest": ("tests", "Write Python tests with pytest."),
    "ruff": ("py", "Python code must pass ruff with the project config."),
    "black": ("py", "Format Python with black."),
    "isort": ("py", "Keep Python imports sorted with isort."),
    "flake8": ("py", "Python code must pass flake8."),
    "mypy": ("py", "Python code must type-check under mypy."),
    "pyright": ("py", "Python code must type-check under pyright."),
    # Go
    "gin-gonic/gin": ("go", "HTTP handlers use Gin."),
    "labstack/echo": ("go", "HTTP handlers use Echo."),
    "go-chi/chi": ("go", "HTTP routing uses chi."),
    "gorilla/mux": ("go", "HTTP routing uses gorilla/mux."),
    "stretchr/testify": ("tests", "Go tests use testify assertions."),
    "gorm.io/gorm": ("go", "Database access goes through GORM."),
    "spf13/cobra": ("go", "CLI commands are built with cobra."),
    "go.uber.org/zap": ("go", "Log with zap, not fmt.Print*/log."),
    "rs/zerolog": ("go", "Log with zerolog, not fmt.Print*/log."),
    "sirupsen/logrus": ("go", "Log with logrus, not fmt.Print*/log."),
    # Rust
    "tokio": ("rs", "Async code runs on tokio."),
    "serde": ("rs", "Serialization uses serde derives."),
    "anyhow": ("rs", "Application errors use anyhow::Result with context."),
    "thiserror": ("rs", "Library error types derive thiserror::Error."),
    "clap": ("rs", "CLI arguments are defined with clap derives."),
    "axum": ("rs", "HTTP handlers use axum extractors."),
    "actix-web": ("rs", "HTTP handlers use actix-web."),
    "sqlx": ("rs", "Database access goes through sqlx."),
    "diesel": ("rs", "Database access goes through diesel."),
    "tracing": ("rs", "Log with the tracing crate, not println!."),
    # JVM
    "spring-boot-starter-web": ("jvm", "This is a Spring Boot web app: follow its controller/service/repository layering."),
    "spring-boot-starter": ("jvm", "This is a Spring Boot app: follow its configuration and dependency-injection conventions."),
    "lombok": ("jvm", "Lombok is available: use its annotations instead of hand-written boilerplate."),
    "junit-jupiter": ("tests", "Tests use JUnit 5."),
    "mockito-core": ("tests", "Mock collaborators with Mockito."),
    "ktor-server-core": ("jvm", "The server uses Ktor."),
    "kotlinx-coroutines-core": ("jvm", "Asynchronous code uses Kotlin coroutines."),
    # .NET
    "microsoft.entityframeworkcore": ("cs", "Database access goes through Entity Framework Core."),
    "xunit": ("tests", "Tests use xUnit."),
    "nunit": ("tests", "Tests use NUnit."),
    "moq": ("tests", "Mock dependencies with Moq."),
    "serilog": ("cs", "Log with Serilog."),
    "fluentvalidation": ("cs", "Validate input with FluentValidation validators."),
    "mediatr": ("cs", "Requests are handled through MediatR handlers."),
    # Ruby
    "rails": ("any", "This is a Rails project: follow Rails conventions (MVC, ActiveRecord, generators)."),
    "rspec": ("tests", "Write Ruby tests with RSpec."),
    "rspec-rails": ("tests", "Write Ruby tests with RSpec."),
    "rubocop": ("rb", "Ruby code must pass RuboCop with the project config."),
    "sidekiq": ("rb", "Background jobs run on Sidekiq."),
}

# config file name (regex on root-level names) -> (scope key, rule text)
TOOL_CONFIGS = [
    (r"\.?eslintrc(\..+)?$|eslint\.config\..+$", "js", "Code must pass ESLint with the project config."),
    (r"\.prettierrc(\..+)?$|prettier\.config\..+$", "js", "Format with Prettier using the project config."),
    (r"biome\.jsonc?$", "js", "Lint and format with Biome using the project config."),
    (r"\.?ruff\.toml$", "py", "Python code must pass ruff with the project config."),
    (r"\.flake8$", "py", "Python code must pass flake8."),
    (r"mypy\.ini$", "py", "Python code must type-check under mypy."),
    (r"\.golangci\.ya?ml$", "go", "Go code must pass golangci-lint with the project config."),
    (r"\.?rustfmt\.toml$", "rs", "Format Rust with rustfmt using the project config."),
    (r"clippy\.toml$", "rs", "Rust code must pass clippy."),
    (r"\.rubocop\.yml$", "rb", "Ruby code must pass RuboCop with the project config."),
    (r"\.clang-format$", "any", "Format C/C++ with clang-format using the project config."),
    (r"phpcs\.xml(\.dist)?$", "php", "PHP code must pass PHP_CodeSniffer with the project ruleset."),
    (r"pint\.json$", "php", "Format PHP with Laravel Pint (vendor/bin/pint) using the project config."),
    (r"phpstan\.neon(\.dist)?$", "php", "Keep new PHP code free of PHPStan errors."),
    (r"psalm\.xml(\.dist)?$", "php", "Keep new PHP code free of Psalm errors."),
    (r"checkstyle\.xml$", "jvm", "Java code must pass Checkstyle."),
    (r"detekt\.ya?ml$", "jvm", "Kotlin code must pass detekt."),
    (r"\.scalafmt\.conf$", "any", "Format Scala with scalafmt."),
    (r"\.pre-commit-config\.ya?ml$", "any", "Pre-commit hooks are configured: make sure changes pass them."),
    (r"stylelint\.config\..+$|\.stylelintrc(\..+)?$", "css", "Styles must pass stylelint with the project config."),
]
SCRIPT_KEYS = ["lint", "format", "typecheck", "type-check", "test", "test:e2e", "build"]
MAKE_TARGETS = ["lint", "fmt", "format", "check", "test", "build", "vet"]


def _read(fp: Path) -> str:
    try:
        return fp.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _mapping(value) -> dict:
    """`value` if it is a JSON object, else {} (manifests in the wild are not always well-formed)."""
    return value if isinstance(value, dict) else {}


def _json(fp: Path) -> dict:
    try:
        return _mapping(json.loads(fp.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return {}


class Facts:
    def __init__(self):
        self.deps: dict[str, str] = {}      # lowercase dep -> file it came from
        self.notes: list[tuple[str, str, str]] = []  # (text, scope key, evidence)

    def dep(self, name: str, file: str):
        self.deps.setdefault(name.lower(), file)

    def note(self, text: str, scope: str, evidence: str):
        self.notes.append((text, scope, evidence))


def _composer(root: Path, f: Facts):
    j = _json(root / "composer.json")
    for key in ("require", "require-dev"):
        for d in _mapping(j.get(key)):
            f.dep(d, "composer.json")
    php = _mapping(j.get("require")).get("php")
    if php:
        f.note(f"Target PHP {php}; use language features available there, nothing newer.", "php", f"composer.json require.php = {php}")


def _package_json(root: Path, f: Facts):
    j = _json(root / "package.json")
    for key in ("dependencies", "devDependencies"):
        for d in _mapping(j.get(key)):
            f.dep(d, "package.json")
    node = _mapping(j.get("engines")).get("node")
    if node:
        f.note(f"Target Node {node}.", "js", f"package.json engines.node = {node}")
    scripts = _mapping(j.get("scripts"))
    cmds = [f"`npm run {k}`" for k in SCRIPT_KEYS if k in scripts]
    if cmds:
        f.note("Verify changes with the project scripts: " + ", ".join(cmds) + " (as relevant to what you touched).", "any", "package.json scripts")
    ts = _read(root / "tsconfig.json")
    if re.search(r'"strict"\s*:\s*true', ts):
        f.note("TypeScript strict mode is enabled: no implicit any; avoid explicit `any`.", "ts", "tsconfig.json strict: true")


def _python(root: Path, f: Facts):
    for fp in sorted(root.glob("requirements*.txt")) + sorted((root / "requirements").glob("*.txt") if (root / "requirements").is_dir() else []):
        for line in _read(fp).splitlines():
            m = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", line)
            if m and not line.lstrip().startswith(("#", "-")):
                f.dep(m.group(1).replace("_", "-"), fp.name)
    text = _read(root / "pyproject.toml")
    if text:
        for m in re.finditer(r"""["']([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*(?:[<>=!~;][^"']*)?["']""", text):
            f.dep(m.group(1).replace("_", "-"), "pyproject.toml")
        for m in re.finditer(r"^\[tool\.([A-Za-z0-9_-]+)", text, re.M):
            f.dep(m.group(1), "pyproject.toml")
        for m in re.finditer(r"^\s*([A-Za-z0-9_-]+)\s*=\s*[\"{]", text, re.M):  # poetry-style `name = "^1.0"`
            f.dep(m.group(1).replace("_", "-"), "pyproject.toml")
        m = re.search(r"""requires-python\s*=\s*["']([^"']+)["']""", text)
        if m:
            f.note(f"Target Python {m.group(1)}; use language features available there.", "py", f"pyproject.toml requires-python = {m.group(1)}")


def _go(root: Path, f: Facts):
    text = _read(root / "go.mod")
    if not text:
        return
    m = re.search(r"^go\s+(\S+)", text, re.M)
    if m:
        f.note(f"Target Go {m.group(1)}.", "go", f"go.mod go {m.group(1)}")
    for line in text.splitlines():
        m = re.match(r"\s*(?:require\s+)?([A-Za-z0-9.\-]+\.[a-z]+/[^\s]+)\s+v", line)
        if m:
            path = m.group(1).lower()
            f.dep(path, "go.mod")
            parts = path.split("/")
            f.dep("/".join(parts[1:3]), "go.mod")  # github.com/org/repo -> org/repo


def _cargo(root: Path, f: Facts):
    text = _read(root / "Cargo.toml")
    if not text:
        return
    m = re.search(r"""^edition\s*=\s*["'](\d+)["']""", text, re.M)
    if m:
        f.note(f"Rust edition {m.group(1)}.", "rs", f"Cargo.toml edition = {m.group(1)}")
    section = ""
    for line in text.splitlines():
        h = re.match(r"\s*\[([^\]]+)\]", line)
        if h:
            section = h.group(1)
            m = re.match(r"(?:dev-|build-)?dependencies\.([A-Za-z0-9_-]+)", section)
            if m:
                f.dep(m.group(1), "Cargo.toml")
        elif re.search(r"dependencies$", section):
            m = re.match(r"\s*([A-Za-z0-9_-]+)\s*=", line)
            if m:
                f.dep(m.group(1), "Cargo.toml")


def _jvm(root: Path, f: Facts):
    pom = _read(root / "pom.xml")
    for m in re.finditer(r"<artifactId>([^<]+)</artifactId>", pom):
        f.dep(m.group(1).strip(), "pom.xml")
    m = re.search(r"<(?:java\.version|maven\.compiler\.(?:source|release)|release)>(\d+)</", pom)
    if m:
        f.note(f"Target Java {m.group(1)}.", "jvm", f"pom.xml java {m.group(1)}")
    for name in ("build.gradle", "build.gradle.kts"):
        g = _read(root / name)
        for m in re.finditer(r"""["']([\w.\-]+):([\w.\-]+)(?::[^"']*)?["']""", g):
            f.dep(m.group(2), name)
        for m in re.finditer(r"""(?:id\(|id\s+|kotlin\()["']([\w.\-]+)["']""", g):
            f.dep(m.group(1), name)
        m = re.search(r"(?:jvmToolchain|JavaVersion\.VERSION_|languageVersion.*?of)\(?\s*_?(\d+)", g)
        if m:
            f.note(f"Target JVM {m.group(1)}.", "jvm", f"{name} jvm {m.group(1)}")


def _dotnet(root: Path, f: Facts):
    for fp in sorted(root.glob("**/*.csproj"))[:20]:
        text = _read(fp)
        name = fp.name
        m = re.search(r'<Project\s+Sdk="([^"]+)"', text)
        if m:
            f.dep(m.group(1), name)  # e.g. Microsoft.NET.Sdk.Web marks an ASP.NET Core app
        for m in re.finditer(r'<PackageReference\s+Include="([^"]+)"', text):
            f.dep(m.group(1), name)
        m = re.search(r"<TargetFramework>([^<]+)</TargetFramework>", text)
        if m:
            f.note(f"Target {m.group(1)}.", "cs", f"{name} TargetFramework")
        if re.search(r"<Nullable>enable</Nullable>", text):
            f.note("Nullable reference types are enabled: annotate nullability and do not suppress warnings with `!`.", "cs", f"{name} Nullable=enable")
        if re.search(r"<TreatWarningsAsErrors>true</TreatWarningsAsErrors>", text):
            f.note("Warnings are errors: new code must compile warning-free.", "cs", f"{name} TreatWarningsAsErrors")


def _ruby(root: Path, f: Facts):
    text = _read(root / "Gemfile")
    for m in re.finditer(r"""^\s*gem\s+["']([\w\-]+)["']""", text, re.M):
        f.dep(m.group(1), "Gemfile")
    m = re.search(r"""^\s*ruby\s+["']([^"']+)["']""", text, re.M)
    if m:
        f.note(f"Target Ruby {m.group(1)}.", "rb", f"Gemfile ruby {m.group(1)}")


def _build_tools(root: Path, f: Facts):
    for name in ("Makefile", "makefile", "justfile"):
        text = _read(root / name)
        if text:
            targets = [t for t in MAKE_TARGETS if re.search(rf"^{t}\s*:", text, re.M)]
            cmd = "just" if name == "justfile" else "make"
            if targets:
                f.note("Verify changes with the project targets: " + ", ".join(f"`{cmd} {t}`" for t in targets) + " (as relevant).", "any", name)
            break


def _dart(root: Path, f: Facts):
    text = _read(root / "pubspec.yaml")
    section = ""
    for line in text.splitlines():
        if re.match(r"^\w", line):
            section = line.split(":")[0]
        elif section in ("dependencies", "dev_dependencies"):
            m = re.match(r"^  ([A-Za-z0-9_]+):", line)
            if m:
                f.dep(m.group(1), "pubspec.yaml")


def _elixir(root: Path, f: Facts):
    for m in re.finditer(r"\{:(\w+),", _read(root / "mix.exs")):
        f.dep(m.group(1), "mix.exs")


def _scala(root: Path, f: Facts):
    for m in re.finditer(r"""["']([\w.\-]+)["']\s*%{1,3}\s*["']([\w.\-]+)["']""", _read(root / "build.sbt") + _read(root / "project" / "plugins.sbt")):
        f.dep(m.group(1), "build.sbt")
        f.dep(m.group(2), "build.sbt")


def _cmake(root: Path, f: Facts):
    text = _read(root / "CMakeLists.txt")
    for m in re.finditer(r"find_package\(\s*([A-Za-z0-9_]+)", text):
        f.dep(m.group(1), "CMakeLists.txt")
    for m in re.finditer(r"\b(Qt\d?)::", text):
        f.dep(m.group(1), "CMakeLists.txt")
    if any(root.glob("*.pro")):
        f.dep("qt", "*.pro")


READERS = (_composer, _package_json, _python, _go, _cargo, _jvm, _dotnet, _ruby, _dart, _elixir, _scala, _cmake, _build_tools)


def read_facts(root: Path) -> Facts:
    """Parse every known manifest under root into dependency names and targets."""
    f = Facts()
    for reader in READERS:
        reader(root, f)
    if "pestphp/pest" in f.deps:
        f.deps.pop("phpunit/phpunit", None)
    if "rspec-rails" in f.deps:
        f.deps.pop("rspec", None)
    return f


def collect(root: Path) -> list[dict]:
    return candidates(read_facts(root), root)


def candidates(f: Facts, root: Path) -> list:
    """Turn parsed facts and tool-config files into Candidate rules."""
    cands, seen_text = [], set()

    def add(text, scope_key, evidence, kind="config"):
        if text not in seen_text:
            seen_text.add(text)
            cands.append(Candidate(text, Scope.parse(SCOPES[scope_key]), evidence, kind))

    for dep, file in f.deps.items():
        if dep in DEPS:
            sk, text = DEPS[dep]
            add(text, sk, f"{dep} in {file}")
    for text, sk, ev in f.notes:
        add(text, sk, ev)
    try:
        names = [p.name for p in root.iterdir() if p.is_file()]
    except OSError:
        names = []
    for pat, sk, text in TOOL_CONFIGS:
        hit = next((n for n in sorted(names) if re.fullmatch(pat, n)), None)
        if hit:
            add(text, sk, f"{hit} present")
    return cands
