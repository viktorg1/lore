"""Which rules are relevant to a piece of work: plain keyword ranking (BM25) over the rule texts. No model, no network.

A rule is described by its wording and its scope (a rule scoped to `src/api` is about the API); the work is described
by a sentence from the agent plus the files being edited. Words are lower-cased, split out of identifiers and file
names (`UserRepository`, `user_repo.py`), and reduced to a rough stem so "validate" finds "validation".
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable

from .models import Rule

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9]*|\d+")
_CAMEL = re.compile(r"[a-z0-9]+|[A-Z][a-z0-9]*|[A-Z]+(?![a-z])")
_STOP = frozenset("""a an the and or but to of in on for with at by from into as is are was were be been it its this that
these those we you i can should must do does not no use using when where while if then so than also any all each only
new add make makes made get gets code file files rule rules project""".split())
# file extensions and folder names that say what kind of work it is
_ALIASES = {"py": "python", "ts": "typescript", "tsx": "typescript react", "js": "javascript", "jsx": "javascript react",
            "rb": "ruby", "rs": "rust", "kt": "kotlin", "cs": "csharp", "md": "markdown", "yml": "yaml", "sh": "shell",
            "db": "database", "sql": "database", "repo": "repository", "test": "test", "tests": "test", "spec": "test"}

K1, B = 1.5, 0.75
_EXTENSION = re.compile(r"(?<=\w)\.(?:py|ts|tsx|js|jsx|rb|rs|kt|cs|md|yml|sh|sql)\b")

# Words that belong to the same area of work. A word also matches every other word of its topic, so a task about a
# "column" finds the rule about "migrations". Plain lists on purpose: easy to read, extend and test.
_TOPICS = {
    "data": "database db sql schema table column migration migrate query orm model repository record row index transaction "
            "postgres mysql sqlite mongo redis",
    "http": "endpoint route router controller handler request response api http rest url status header middleware graphql",
    "test": "test testing spec assert assertion mock stub fixture coverage pytest jest unit integration",
    "log": "log logging logger print diagnostic trace metric monitoring observability",
    "error": "error exception fail failure raise throw catch retry timeout fallback crash",
    "ui": "ui component react vue view screen page render frontend css style layout button form",
    "types": "type typing hint annotation interface generic typescript mypy",
    "naming": "name naming rename variable identifier convention case camel snake pascal",
    "security": "secret key token password credential encrypt encryption auth authentication authorization permission "
                "sanitize xss injection csrf",
    "config": "config configuration env environment setting flag option",
    "dependency": "dependency import package library sdk vendor adapter client install",
    "docs": "doc documentation comment docstring readme openapi swagger changelog",
    "validate": "validate validation schema input sanitize parse serialize",
    "style": "format formatting lint linter prettier ruff eslint indent tab space quote semicolon",
    "git": "git commit branch merge pull review changelog release version",
}


_SUFFIXES = tuple(sorted(("izations", "ization", "isations", "isation", "izing", "ising", "ized", "ised", "izes", "ises", "ize", "ise",
                          "ations", "ation", "ating", "ated", "ate", "ings", "ing", "ions", "ion", "ies", "ers", "er", "ed", "es", "s"),
                         key=len, reverse=True))


def _stem(word: str) -> str:
    """A rough stem, only good enough to make "validate", "validation" and "validating" meet."""
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            word = word[: len(word) - len(suffix)]
            break
    return word[:-1] if word[-1:] in ("e", "y") and len(word) > 4 else word


def _topic_table() -> dict[str, list[str]]:
    table: dict[str, list[str]] = {}
    for topic, words in _TOPICS.items():
        for w in words.split():
            table.setdefault(_stem(w), []).append(f"~{topic}")
    return table


_BY_STEM: dict[str, list[str]] | None = None


def _by_stem() -> dict[str, list[str]]:
    global _BY_STEM
    if _BY_STEM is None:
        _BY_STEM = _topic_table()
    return _BY_STEM


def terms(text: str) -> list[str]:
    """Searchable words of a text: identifiers split, stop words dropped, aliases expanded, stemmed.

    A file extension glued to a name ("scanner.py") is not a word of the text: it would make every rule that mentions
    Python look relevant to any task that names a Python file.
    """
    text = _EXTENSION.sub(" ", text)
    out: list[str] = []
    for raw in _WORD.findall(text):
        for part in _CAMEL.findall(raw) if not raw.isupper() else [raw]:
            word = part.lower()
            for w in _ALIASES.get(word, word).split():
                if w not in _STOP and len(w) > 1:
                    stem = _stem(w)
                    out.append(stem)
                    out.extend(_by_stem().get(stem, ()))      # the topics this word belongs to
    return out


def query_terms(task: str = "", paths: Iterable[str] = ()) -> list[str]:
    """The words describing the work: the agent's sentence plus the names and folders of the files being edited."""
    words = terms(task)
    for p in paths:
        words += terms(p.replace("/", " ").replace(".", " ").replace("_", " ").replace("-", " "))
    return words


def _meaning(rule: Rule) -> list[str]:
    """What the rule is about: its text, its title, and the trigger words an agent chose for it (counted twice)."""
    return terms(rule.text) + terms(rule.title) + 2 * terms(" ".join(rule.triggers))


def _document(rule: Rule, with_scope: bool = True) -> list[str]:
    if not with_scope:
        return _meaning(rule)
    scope = rule.scope.key.split(":", 1)[-1] if rule.scope.key != "global" else ""
    return _meaning(rule) + terms(scope.replace("/", " ").replace("*", " ").replace(",", " ").replace(".", " "))


def rank(rules: list[Rule], query: list[str], with_scope: bool = True) -> list[tuple[Rule, float]]:
    """Every rule with its relevance to `query` (0 when it shares no word), best first; ties keep the given order.

    `with_scope`: also match the words of the rule's scope (a rule for `db` is about databases).
    """
    if not rules:
        return []
    docs = [Counter(_document(r, with_scope)) for r in rules]
    lengths = [sum(d.values()) or 1 for d in docs]
    average = sum(lengths) / len(lengths)
    wanted = set(query)
    df = {t: sum(1 for d in docs if t in d) for t in wanted}
    scored = []
    for rule, doc, length in zip(rules, docs, lengths):
        score = 0.0
        for t in wanted:
            tf = doc.get(t, 0)
            if tf:
                idf = math.log(1 + (len(rules) - df[t] + 0.5) / (df[t] + 0.5))
                score += idf * tf * (K1 + 1) / (tf + K1 * (1 - B + B * length / average))
        scored.append((rule, score))
    order = sorted(range(len(scored)), key=lambda i: (-scored[i][1], i))
    return [scored[i] for i in order]
