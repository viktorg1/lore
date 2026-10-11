"""Small text helpers shared by rules, dedupe and ids."""
from __future__ import annotations

import difflib
import hashlib
import re

# High on purpose: a wrong merge silently loses a rule, while a missed duplicate is only clutter.
SIMILARITY = 0.92
RELATED = 0.6   # close enough in wording that a person should compare the two for contradictions


def squash(text: str) -> str:
    """Collapse all whitespace runs to single spaces."""
    return " ".join(text.split())


def normalize(text: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace: the form used to compare rules."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text.lower())).strip()


def similar(a: str, b: str) -> bool:
    return difflib.SequenceMatcher(None, normalize(a), normalize(b)).ratio() >= SIMILARITY


def related(a: str, b: str) -> bool:
    """Close enough in wording that a person should compare the two (looser than `similar`)."""
    return difflib.SequenceMatcher(None, normalize(a), normalize(b)).ratio() >= RELATED


# Words that cannot both be asked for at once. A pair of rules that differ by one of these says opposite things.
_EXCLUSIVE_GROUPS = [set(g.split()) for g in (
    "tabs spaces", "tab space", "single double", "always never", "use avoid", "allow forbid disallow prohibit ban",
    "require forbid", "enable disable", "before after", "first last", "top bottom", "sync async synchronous asynchronous",
    "mutable immutable", "public private protected", "uppercase lowercase", "upper lower", "prefix suffix",
    "camelcase snake kebab pascalcase pascal", "include exclude", "add remove", "increase decrease", "true false",
    "must may", "inline separate", "named default", "static dynamic", "eager lazy", "positive negative",
)]
_NEGATIONS = {"not", "never", "no", "without", "dont", "doesnt", "cannot", "cant", "wont", "nor"}
_AUXILIARIES = {"do", "does", "did", "should", "must", "please", "we", "you", "always"}


def _words(text: str) -> list[str]:
    return normalize(text.replace("'", "").replace("’", "")).split()


def contradicts(a: str, b: str) -> bool:
    """True when two near-identical rules differ in a way that reverses their meaning.

    Looks at the words that are only in one of the two: opposite options (tabs/spaces, always/never), a negation
    on one side only ("do not use X" vs "use X"), or different numbers ("max 80" vs "max 120"). Heuristic: it
    exists to stop `similar` from merging opposite rules, not to understand language.
    """
    ta, tb = _words(a), _words(b)
    only_a, only_b = set(ta) - set(tb), set(tb) - set(ta)
    if not only_a and not only_b:
        return False
    if any(x.isdigit() for x in only_a) and any(y.isdigit() for y in only_b):
        return True
    for group in _EXCLUSIVE_GROUPS:
        if only_a & group and only_b & group and (only_a & group) != (only_b & group):
            return True
    neg_a, neg_b = only_a & _NEGATIONS, only_b & _NEGATIONS
    if bool(neg_a) != bool(neg_b):
        rest = (only_a | only_b) - _NEGATIONS - _AUXILIARIES
        if not rest:
            return True
    return False


def short_hash(text: str, length: int = 8) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:length]
