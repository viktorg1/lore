"""Heuristic warnings for rule text that looks like an attack on the agent, not a coding convention.

This is a tripwire for lazy or copy-pasted attacks, not a defence: a well-worded malicious rule passes. Its job is to
make a person stop and read before approving. False alarms are fine; they only cost one extra confirmation.
"""
from __future__ import annotations

import re

_I = re.IGNORECASE
_CHECKS: tuple[tuple[str, re.Pattern], ...] = (
    ("pipes a download into a shell", re.compile(r"\b(curl|wget)\b[^|\n]*\|\s*(sudo\s+)?(ba|z|da|k)?sh\b", _I)),
    ("tries to override earlier instructions", re.compile(
        r"\b(ignore|disregard|forget|override)\b.{0,40}\b(instructions?|rules?|prompts?|guidelines|directions)\b", _I)),
    ("imitates a system or developer message", re.compile(
        r"(^|[\s>\[(])(system|assistant|developer)\s*(prompt|message)?\s*:|you are now\b|developer mode|new instructions", _I)),
    ("asks to reveal the prompt", re.compile(
        r"\b(reveal|print|show|output|repeat|leak)\b.{0,30}\b(system|hidden|initial)\s+(prompt|instructions?)\b", _I)),
    ("mentions credentials or key files", re.compile(
        r"\.ssh\b|id_rsa|id_ed25519|\.aws\b|\.netrc|\.npmrc|\.pypirc|/etc/(passwd|shadow)|keychain|\.gnupg", _I)),
    ("contains a web address", re.compile(r"\bhttps?://|\bwww\.\w", _I)),
    ("runs a dangerous command", re.compile(
        r"\bsudo\b|\brm\s+-[a-z]*r[a-z]*f|\bchmod\s+-?[a-z]*\s*777\b|\beval\s*\(|\bbase64\s+(-d|--decode)\b|\bnc\s+-[a-z]*e\b", _I)),
    ("tells the agent to skip checks or review", re.compile(
        r"\b(disable|turn off|skip|bypass|ignore)\b.{0,25}\b(safety|security|review|approval|verification|permissions?|confirmation|checks?)\b"
        r"|\bwithout (asking|review|confirmation|approval)\b|\bpush\b.{0,15}\b(directly )?to (main|master|prod)\b|\bforce[- ]push\b", _I)),
    ("contains an encoded blob", re.compile(r"[A-Za-z0-9+/]{40,}={0,2}")),
)


def check(text: str) -> list[str]:
    """Short reasons a person should look twice at this rule (empty when nothing stands out)."""
    return [reason for reason, pattern in _CHECKS if pattern.search(text)]
