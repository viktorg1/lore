"""Hygiene for everything that can become a rule: no hidden characters, no hidden markup, bounded size.

Rule text is an instruction a coding agent will follow, and it can come from a PR comment, an agent's own words,
a document or a manifest. Invisible characters (zero-width, bidirectional controls, Unicode "tag" characters) let
text say one thing to a reviewer and another to a model, so they are rejected rather than silently cleaned: a
person should know that something tried to hide in a rule.
"""
from __future__ import annotations

import re
import unicodedata

MAX_RULE_LENGTH = 500
MAX_SCOPE_LENGTH = 200
MAX_NOTE_LENGTH = 300       # evidence and source labels

# Format characters that are harmless next to emoji (they select text vs emoji presentation).
_ALLOWED_INVISIBLE = {"︎", "️"}
# Characters that render as blank without being control/format characters.
_BLANK_LOOKALIKES = {"ㅤ", "ﾠ", "⠀", "ᅟ", "ᅠ", "឴", "឵", "͏", "؜"}
_SCOPE_FORBIDDEN = re.compile(r'[\x00-\x1f\x7f"\\`]')
_URL = re.compile(r"^https?://[^\s<>\"'`\\]+$", re.I)


class RuleTextError(ValueError):
    """The text may not become a rule; the message says why and is fit to show to a person."""


def is_hidden(ch: str) -> bool:
    """True for characters a reader cannot see but a model receives."""
    if ch in _ALLOWED_INVISIBLE or ch in " \t\n\r":
        return False
    if ch in _BLANK_LOOKALIKES:
        return True
    category = unicodedata.category(ch)
    if category in ("Cc", "Cf", "Co", "Cn", "Cs", "Zl", "Zp"):    # control, format, private, unassigned, separators
        return True
    if category == "Mn" and ("︀" <= ch <= "️" or "\U000e0100" <= ch <= "\U000e01ef" or "᠋" <= ch <= "᠍"):
        return True                                                # variation selectors can smuggle data
    return False


def hidden_chars(text: str) -> list[str]:
    return [ch for ch in text if is_hidden(ch)]


def hidden_count(text: str) -> int:
    return len(hidden_chars(text))


def reveal(text: str) -> str:
    """The text with every hidden character spelled out, e.g. `<U+200B>`, so a person can see it."""
    return "".join(f"<U+{ord(ch):04X}>" if is_hidden(ch) else ch for ch in text)


def strip_hidden(text: str) -> str:
    return "".join(ch for ch in text if not is_hidden(ch))


def _describe(chars: list[str]) -> str:
    first = chars[0]
    return f"U+{ord(first):04X} {unicodedata.name(first, 'unassigned character')}"


def clean_rule_text(text: str) -> str:
    """The text as it will be stored: one line, visible characters only, within the length limit.

    Raises RuleTextError otherwise.
    """
    text = " ".join(text.split())
    if not text:
        raise RuleTextError("empty rule")
    bad = hidden_chars(text)
    if bad:
        raise RuleTextError(f"contains {len(bad)} hidden character(s), first {_describe(bad)}; remove them")
    if "<!--" in text or "-->" in text:
        raise RuleTextError("contains an HTML comment marker, which hides text from rendered views")
    if len(text) > MAX_RULE_LENGTH:
        raise RuleTextError(f"is {len(text)} characters long; keep a rule under {MAX_RULE_LENGTH}")
    return text


def clean_note(text: str, maxlen: int = MAX_NOTE_LENGTH) -> str:
    """Evidence and labels are shown to people, not followed: hidden characters are dropped, size is capped."""
    text = " ".join(strip_hidden(text or "").split())
    return text if len(text) <= maxlen else text[: maxlen - 1].rstrip() + "…"


def is_http_url(value: str) -> bool:
    return bool(_URL.match(value)) and not hidden_chars(value) and len(value) <= 2000


def clean_scope_token(value: str, what: str) -> str:
    """A section name or glob: printable, no quotes/backslashes/backticks/newlines, bounded."""
    value = value.strip()
    if not value:
        raise ValueError(f"empty {what}")
    if hidden_chars(value) or _SCOPE_FORBIDDEN.search(value):
        raise ValueError(f"{what} {reveal(value)[:60]!r} contains characters that are not allowed")
    if len(value) > MAX_SCOPE_LENGTH:
        raise ValueError(f"{what} is too long (over {MAX_SCOPE_LENGTH} characters)")
    return value
