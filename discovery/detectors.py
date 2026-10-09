"""Detectors: each inspects a Project and returns Candidates. Run in order by Discoverer."""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections import Counter

import ecosystems
import rules
from . import registry, scanner
from .core import Candidate, Project, pct
from .languages.base import Language


class Detector(ABC):
    name = "detector"

    @abstractmethod
    def detect(self, project: Project) -> list[Candidate]: ...


# ---------- tooling config ----------

class EditorConfigDetector(Detector):
    name = "editorconfig"

    def detect(self, project: Project) -> list[Candidate]:
        fp = project.root / ".editorconfig"
        if not fp.exists():
            return []
        project.has_editorconfig = True
        out: list[Candidate] = []
        glob, props = None, {}

        def flush():
            if not glob:
                return
            bits = []
            if props.get("indent_style") == "tab":
                bits.append("indent with tabs")
            elif props.get("indent_style") == "space":
                bits.append(f"indent with {props.get('indent_size', '?')} spaces")
            if props.get("end_of_line"):
                bits.append(f"{props['end_of_line'].upper()} line endings")
            if props.get("insert_final_newline") == "true":
                bits.append("end files with a newline")
            if props.get("trim_trailing_whitespace") == "true":
                bits.append("trim trailing whitespace")
            if props.get("max_line_length", "off") not in ("off", "unset"):
                bits.append(f"max line length {props['max_line_length']}")
            if bits:
                scope = {"type": "global"} if glob == "*" else {"type": "glob", "globs": rules.split_globs(glob)}
                label = "all files" if glob == "*" else glob
                out.append(Candidate(f"Formatting for {label}: " + "; ".join(bits) + ".", scope, ".editorconfig", "config"))

        for raw in fp.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line[0] in "#;":
                continue
            if line.startswith("[") and line.endswith("]"):
                flush()
                glob, props = line[1:-1], {}
            elif "=" in line and glob is not None:
                k, v = line.split("=", 1)
                props[k.strip().lower()] = v.strip().lower()
        flush()
        return out


class ManifestDetector(Detector):
    name = "manifests"

    def detect(self, project: Project) -> list[Candidate]:
        return ecosystems.candidates(project.facts, project.root)


# ---------- code statistics ----------

class StyleDetector(Detector):
    """Indentation, quotes, semicolons and line length, per language."""
    name = "style"

    def detect(self, project: Project) -> list[Candidate]:
        out: list[Candidate] = []
        for lang in registry.languages().values():
            files = project.files_of(lang.name)
            if len(files) < project.th.min_files:
                continue
            out += self._indent(lang, files, project)
            out += self._quotes(lang, files)
            out += self._semicolons(lang, files, project)
            out += self._line_length(lang, files)
        return out

    @staticmethod
    def _indent_vote(text: str) -> int | None:
        """0 = tabs, N = N spaces (mode of positive indent increases), None = unknown."""
        tabs = spaces = 0
        steps, prev = Counter(), 0
        for ln in text.splitlines():
            if not ln.strip() or ln.lstrip().startswith(("*", "//", "#")):
                continue
            lead = len(ln) - len(ln.lstrip(" \t"))
            if ln.startswith("\t"):
                tabs += 1
                continue
            if lead:
                spaces += 1
            if lead > prev:
                steps[lead - prev] += 1
            prev = lead
        if tabs > spaces and tabs >= 3:
            return 0
        if spaces >= 3 and steps:
            return steps.most_common(1)[0][0]
        return None

    def _indent(self, lang: Language, files, project) -> list[Candidate]:
        if project.has_editorconfig or lang.formatter_enforced:
            return []
        votes = Counter(v for t in files.values() if (v := self._indent_vote(t)))
        tot = sum(votes.values())
        if not votes or tot < project.th.min_files:
            return []
        style, c = votes.most_common(1)[0]
        if c / tot < project.th.min_ratio:
            return []
        what = "tabs" if style == 0 else f"{style} spaces"
        return [Candidate(f"Indent {lang.name} code with {what}.", lang.scope(), f"{pct(c, tot)} of {lang.name} files", "stats")]

    @staticmethod
    def _quotes(lang: Language, files) -> list[Candidate]:
        if not lang.check_quotes:
            return []
        single = sum(len(re.findall(r"'(?:[^'\\\n]|\\.){1,200}'", t)) for t in files.values())
        double = sum(len(re.findall(r'"(?:[^"\\\n]|\\.){1,200}"', t)) for t in files.values())
        tot = single + double
        if tot < 50:
            return []
        return [Candidate(f"Use {name} quotes for strings in {lang.name} code.", lang.scope(),
                          f"{pct(c, tot)} of string literals", "stats")
                for name, c in (("single", single), ("double", double)) if c / tot >= 0.8]

    @staticmethod
    def _semicolons(lang: Language, files, project) -> list[Candidate]:
        if not lang.check_semicolons:
            return []
        semi = total = 0
        for text in files.values():
            for ln in text.splitlines():
                s = ln.rstrip()
                if re.match(r"\s*(import|export|const|let|var|return)\b", s) and not re.search(r"[{(,=\[]$|=>$|<[a-z]", s):
                    total += 1
                    semi += s.endswith(";")
        if total < 40:
            return []
        r = project.th.min_ratio
        if semi / total >= r:
            return [Candidate(f"Terminate statements with semicolons in {lang.name} code.", lang.scope(), f"{pct(semi, total)} of statements", "stats")]
        if semi / total <= 1 - r:
            return [Candidate(f"Do not use semicolons in {lang.name} code.", lang.scope(), f"{pct(total - semi, total)} of statements have none", "stats")]
        return []

    @staticmethod
    def _line_length(lang: Language, files) -> list[Candidate]:
        if lang.formatter_enforced:
            return []
        lengths = sorted(len(ln) for t in files.values() for ln in t.splitlines() if ln.strip())
        if len(lengths) < 500:
            return []
        p99 = lengths[int(len(lengths) * 0.99)]
        for limit in (80, 100, 120):
            if p99 <= limit:
                return [Candidate(f"Keep {lang.name} lines within about {limit} characters.", lang.scope(),
                                  f"99% of {lang.name} lines are <= {p99} chars", "stats")]
        return []


class NamingDetector(Detector):
    """File-name casing per folder, grouped so one rule covers every folder that agrees."""
    name = "naming"
    CASES = {
        "PascalCase": re.compile(r"^[A-Z][a-z0-9]+([A-Z][a-z0-9]*)*$"),
        "camelCase": re.compile(r"^[a-z][a-z0-9]*([A-Z][a-z0-9]*)+$"),
        "kebab-case": re.compile(r"^[a-z0-9]+(-[a-z0-9]+)+$"),
        "snake_case": re.compile(r"^[a-z0-9]+(_[a-z0-9]+)+$"),
    }
    MAX_RULES = 12

    def _case(self, stem: str) -> str | None:
        for k, rx in self.CASES.items():
            if rx.match(stem):
                return k
        return None  # a single lowercase word fits several styles, so it casts no vote

    def detect(self, project: Project) -> list[Candidate]:
        code_exts = registry.code_extensions()
        by_dir: dict[tuple[str, str], list[str]] = {}
        for rel in project.files:
            if scanner.is_vendored(rel):
                continue
            d, _, base = rel.rpartition("/")
            stem, dot, ext = base.partition(".")
            last = ext.rsplit(".", 1)[-1]
            if not dot or not d or "." + last not in code_exts:
                continue
            by_dir.setdefault((d, last), []).append(stem)
        groups: dict[tuple[str, str], list[tuple[str, int, int]]] = {}
        for (d, ext), stems in by_dir.items():
            votes = Counter(c for s in stems if (c := self._case(s)))
            tot = sum(votes.values())
            if tot >= 4:
                style, c = votes.most_common(1)[0]
                if c / tot >= project.th.min_ratio:
                    groups.setdefault((ext, style), []).append((d, c, tot))
        ranked = sorted(groups.items(), key=lambda kv: -sum(t for _, _, t in kv[1]))[:self.MAX_RULES]
        out = []
        for (ext, style), dirs in ranked:
            dirs = sorted(dirs, key=lambda x: -x[2])[:8]
            out.append(Candidate(
                f"Name .{ext} files in {style} ({', '.join(d for d, _, _ in dirs)}).",
                {"type": "glob", "globs": [f"{d}/*.{ext}" for d, _, _ in dirs]},
                "; ".join(f"{d}: {pct(c, t)}" for d, c, t in dirs[:3]), "stats"))
        return out


# ---------- pattern markers ----------

class LanguageMarkerDetector(Detector):
    """Framework-independent ("vanilla") markers of every language present in the project."""
    name = "language-markers"

    def __init__(self, extra=()):
        self.extra = list(extra)

    def detect(self, project: Project) -> list[Candidate]:
        out = []
        for lang in registry.languages().values():
            if not project.files_of(lang.name):
                continue
            for marker in lang.markers:
                out += marker.evaluate(project)
        for marker in self.extra:
            out += marker.evaluate(project)
        return out


class FrameworkMarkerDetector(Detector):
    """Markers of each framework the project demonstrably uses."""
    name = "framework-markers"

    def detect(self, project: Project) -> list[Candidate]:
        out = []
        for fw in registry.frameworks():
            evidence = fw.detect(project)
            if not evidence:
                continue
            for marker in fw.markers:
                for c in marker.evaluate(project):
                    c.kind = "framework"
                    c.evidence += f" ({fw.name}: {evidence})"
                    out.append(c)
        return out
