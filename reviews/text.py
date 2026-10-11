"""Turning review-comment markdown into comparable words, and a comment into a rule-shaped sentence."""
from __future__ import annotations

import re

CODE_BLOCK = re.compile(r"```.*?```|~~~.*?~~~", re.S)
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
QUOTED_LINE = re.compile(r"^\s*>.*$", re.M)
URL = re.compile(r"https?://\S+")
MENTION = re.compile(r"(?<!\w)@[\w-]+")
LABEL = re.compile(r"^\s*(?:\*\*)?(?:nit(?:pick)?|suggestion|optional|minor|question|thought|issue|todo|style|"
                   r"praise|chore|important|blocking|non-blocking)(?:\s*\([^)]*\))?(?:\*\*)?\s*[:\-–]\s*", re.I)
POLITE = re.compile(r"^(?:(?:hey|hi|hello)[ ,]+)?(?:please|pls|plz|could you|can you|can we|could we|would you|"
                    r"maybe|perhaps|i think(?: we)?(?: should)?|we should|you should|let's|lets|just)\s+", re.I)
PRAISE = re.compile(r"^(?:lgtm|looks good|looks great|nice|great|good|thanks|thank you|ty|done|fixed|ack|agreed|"
                    r"👍|\+1|sounds good|makes sense|ok|okay|yes|no|sure|same|ditto)\b[\s.!,]*$", re.I)
DIRECTIVE = re.compile(r"\b(?:use|using|avoid|don'?t|do not|never|always|prefer|instead|should|must|need|remove|"
                       r"add|rename|move|extract|replace|keep|wrap|return|throw|handle|validate|check)\b", re.I)

STOPWORDS = frozenset("""
a an the and or but to of in on for with at by from into onto as is are was were be been being it its this that
these those there here we you i he she they them our your my me us can could would will shall may might do does
did have has had if then so than also just still too very more most some any each all both only own same such
what which who whom how when where why please pls maybe perhaps rather like one thing things way make makes made
get gets got put here instead really actually""".split())

# words that mean the same thing in review comments; keys are already stemmed
SYNONYMS = {
    "db": "database", "sql": "database", "repo": "repository", "logger": "log", "logg": "log",
    "hint": "annotation", "typ": "type", "func": "function", "fn": "function", "method": "function",
    "var": "variable", "dont": "not", "doesnt": "not", "shouldnt": "not", "cant": "not", "wont": "not",
    "isnt": "not", "arent": "not", "mustnt": "not", "dont't": "not",
}


def clean(body: str) -> str:
    """The reviewer's own words: no code, quotes, links, mentions or label prefixes, on one line."""
    s = HTML_COMMENT.sub(" ", body or "")
    s = CODE_BLOCK.sub(" ", s)
    s = QUOTED_LINE.sub(" ", s)
    s = URL.sub(" ", s)
    s = MENTION.sub(" ", s)
    s = s.replace("**", "").replace("__", "")
    s = " ".join(s.split())
    s = LABEL.sub("", s)
    return s.strip()


def is_actionable(cleaned: str) -> bool:
    """Worth clustering: not praise or an acknowledgement, and long enough to say something."""
    if not cleaned or PRAISE.match(cleaned):
        return False
    return len(tokens(cleaned)) >= 3


def _stem(word: str) -> str:
    if len(word) > 5 and word.endswith("ies"):
        word = word[:-3] + "y"
    elif len(word) > 5 and word.endswith("ing"):
        word = word[:-3]
    elif len(word) > 4 and word.endswith("ed"):
        word = word[:-2]
    elif len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        word = word[:-1]
    return SYNONYMS.get(word, word)


def tokens(cleaned: str) -> frozenset[str]:
    """Content words, lightly stemmed, with CamelCase and snake_case split and common synonyms merged.

    Negations stay: 'do not use X' and 'use X' should not look identical.
    """
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", cleaned).replace("_", " ")
    words = re.findall(r"[a-z0-9]+", spaced.lower().replace("'", "").replace("’", ""))
    return frozenset(_stem(w) for w in words if w not in STOPWORDS and len(w) > 1)


def similarity(a: frozenset[str], b: frozenset[str], min_shared: int = 3) -> float:
    """Jaccard overlap of content words, 0 unless they share at least `min_shared`."""
    shared = len(a & b)
    if shared < min(min_shared, len(a), len(b)):
        return 0.0
    return shared / len(a | b)


def imperative_score(cleaned: str) -> int:
    """Rough 'sounds like a rule' score used to pick the representative of a cluster."""
    return 2 * bool(DIRECTIVE.search(cleaned)) + (0 if cleaned.rstrip().endswith("?") else 1)


def rule_text(cleaned: str, max_len: int = 200) -> str:
    """A reviewer remark as a one-sentence instruction: drop politeness, keep the first sentence."""
    s = POLITE.sub("", cleaned.strip())
    s = POLITE.sub("", s)
    first = re.split(r"(?<=[.!?])\s+(?=[A-Z`])", s, maxsplit=1)[0]
    if len(tokens(first)) >= 2:
        s = first
    s = s.rstrip(" ?!.,;:") if s.endswith("?") else s.rstrip(" ,;:")
    if len(s) > max_len:
        s = s[:max_len].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    if s and s[0].islower():
        s = s[0].upper() + s[1:]
    return s if s.endswith((".", "…")) else s + "."
