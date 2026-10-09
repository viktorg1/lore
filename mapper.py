"""Build a compact structural map of a project (no file contents)."""
from __future__ import annotations

import os
import subprocess
from collections import Counter
from pathlib import Path

IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env", ".tox",
    "dist", "build", "target", ".next", ".nuxt", ".gradle", ".idea", ".vscode",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "coverage", ".cache", "vendor",
    ".terraform", "bin", "obj",
}
# Top-level folders that merely group real sections (src/api -> section "src/api").
CONTAINERS = {"src", "packages", "apps", "services", "lib", "libs", "modules", "internal", "cmd", "pkg"}
MANIFESTS = {
    "package.json", "pyproject.toml", "requirements.txt", "setup.py", "Cargo.toml",
    "go.mod", "pom.xml", "build.gradle", "build.gradle.kts", "Gemfile", "composer.json",
    "Dockerfile", "docker-compose.yml", "Makefile", "justfile", "tsconfig.json", "CMakeLists.txt",
    "build.sbt", "pubspec.yaml", "mix.exs", "deno.json", "Pipfile", "Package.swift",
}
LANGS = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".mts": "typescript", ".cjs": "javascript", ".go": "go", ".rs": "rust",
    ".java": "java", ".kt": "kotlin", ".cs": "csharp", ".rb": "ruby", ".php": "php",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp", ".swift": "swift",
    ".vue": "vue", ".svelte": "svelte", ".sql": "sql", ".sh": "shell",
    ".html": "html", ".css": "css", ".scss": "css", ".md": "markdown",
    ".yml": "yaml", ".yaml": "yaml", ".json": "json", ".tf": "terraform",
    ".cc": "cpp", ".cxx": "cpp", ".scala": "scala", ".dart": "dart", ".ex": "elixir",
    ".exs": "elixir", ".lua": "lua", ".zig": "zig", ".kts": "kotlin", ".m": "objc",
}
MAX_FILES = 200_000
MAX_SUBDIRS = 8


def section_of(rel: str) -> str:
    """Deterministic section id for a project-relative posix path."""
    parts = rel.split("/")
    if len(parts) == 1:
        return "root"
    top = parts[0]
    if top in CONTAINERS and len(parts) > 2:
        return f"{top}/{parts[1]}"
    return top


def list_files(root: Path) -> list[str]:
    """Project-relative posix paths. Uses git when available (honours .gitignore)."""
    try:
        res = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-co", "--exclude-standard", "-z"],
            capture_output=True, timeout=60,
        )
        if res.returncode == 0:
            files = [f for f in res.stdout.decode("utf-8", "replace").split("\0") if f]
            files = [f for f in files if not set(f.split("/")[:-1]) & IGNORE_DIRS]
            return sorted(files)[:MAX_FILES]
    except (OSError, subprocess.SubprocessError):
        pass
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORE_DIRS)
        rel_dir = os.path.relpath(dirpath, root)
        for fn in sorted(filenames):
            out.append(fn if rel_dir == "." else f"{rel_dir}/{fn}".replace(os.sep, "/"))
            if len(out) >= MAX_FILES:
                return out
    return out


def build_map(name: str, root: Path) -> dict:
    files = list_files(root)
    sections: dict[str, dict] = {}
    langs_total: Counter = Counter()
    manifests = []
    subdirs: dict[str, Counter] = {}

    for rel in files:
        sec = section_of(rel)
        info = sections.setdefault(sec, {"path": "" if sec == "root" else sec, "files": 0, "_langs": Counter()})
        info["files"] += 1
        base = rel.rsplit("/", 1)[-1]
        if "/" not in rel and base in MANIFESTS:
            manifests.append(base)
        lang = LANGS.get(os.path.splitext(base)[1].lower())
        if lang and lang not in ("markdown", "json", "yaml"):
            info["_langs"][lang] += 1
            langs_total[lang] += 1
        sec_path = info["path"]
        rest = rel[len(sec_path) + 1:] if sec_path else rel
        if "/" in rest:
            subdirs.setdefault(sec, Counter())[rest.split("/", 1)[0]] += 1

    for sec, info in sections.items():
        info["languages"] = dict(info.pop("_langs").most_common(3))
        info["subdirs"] = [d for d, _ in subdirs.get(sec, Counter()).most_common(MAX_SUBDIRS)]

    return {
        "name": name,
        "root": str(root),
        "generated": None,  # filled by caller
        "files_total": len(files),
        "languages": dict(langs_total.most_common(5)),
        "manifests": sorted(set(manifests)),
        "sections": dict(sorted(sections.items())),
    }
