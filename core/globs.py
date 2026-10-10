"""Glob patterns as the rest of lore understands them: `**`, `*`, `?` and `{a,b}`; a bare `*.py` matches anywhere."""
from __future__ import annotations

import functools
import re


def split_globs(value: str) -> list[str]:
    """Split a comma-separated list of globs on commas that are not inside {braces}."""
    out, depth, cur = [], 0, ""
    for ch in value:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    out.append(cur.strip())
    return [g.strip("'\"") for g in out if g]


def _expand_braces(pattern: str) -> list[str]:
    m = re.search(r"\{([^{}]*)\}", pattern)
    if not m:
        return [pattern]
    return [r for alt in m.group(1).split(",")
            for r in _expand_braces(pattern[:m.start()] + alt + pattern[m.end():])]


@functools.lru_cache(maxsize=512)
def glob_regexes(pattern: str) -> tuple[re.Pattern, ...]:
    """Compile a glob (brace alternatives expand to several regexes) against project-relative posix paths."""
    res = []
    for p in _expand_braces(pattern):
        if p.startswith("./"):
            p = p[2:]
        if "/" not in p:
            p = "**/" + p
        out, i = "", 0
        while i < len(p):
            if p.startswith("**/", i):
                out += "(?:.*/)?"; i += 3
            elif p.startswith("**", i):
                out += ".*"; i += 2
            elif p[i] == "*":
                out += "[^/]*"; i += 1
            elif p[i] == "?":
                out += "[^/]"; i += 1
            else:
                out += re.escape(p[i]); i += 1
        res.append(re.compile("^" + out + "$"))
    return tuple(res)


def glob_match(pattern: str, rel: str) -> bool:
    return any(r.match(rel) for r in glob_regexes(pattern))
