"""Which rules apply to the files about to be edited, most specific first, within a token budget."""
from __future__ import annotations

from dataclasses import dataclass

from .mapper import section_of
from .models import Level, Rule, Status
from .repository import RuleRepository

DEFAULT_MAX_TOKENS = 800


@dataclass
class Resolution:
    sections: list[str]
    rules: list[Rule]      # the rules that fit the budget
    omitted: int           # applicable rules that did not
    text: str              # what the agent is told ("" when no rule applies)


def _tokens(s: str) -> int:
    return max(1, len(s) // 4)


def resolve(project: str, rel_paths: list[str], max_tokens: int = DEFAULT_MAX_TOKENS) -> Resolution:
    rel_paths = [p.strip("/") for p in rel_paths if p]
    active = RuleRepository(project).with_status(Status.ACTIVE)
    picked: dict[str, tuple[Level, Rule]] = {}
    for rel in rel_paths:
        for rule in active:
            level = rule.scope.level_for(rel)
            if level is not None and (rule.id not in picked or level < picked[rule.id][0]):
                picked[rule.id] = (level, rule)
    ranked = sorted(picked.values(), key=lambda lr: (lr[0], lr[1].created))

    sections = sorted({section_of(p) for p in rel_paths})
    header = f"Rules for project `{project}` (follow before writing code; sections: {', '.join(sections) or '-'})"
    used, shown, omitted = _tokens(header), [], 0
    for level, rule in ranked:
        line = f"- [{level.label}] {rule.text}"
        if used + _tokens(line) > max_tokens:
            omitted += 1
            continue
        used += _tokens(line)
        shown.append((rule, line))

    text = header + "\n" + "\n".join(line for _, line in shown) if shown else ""
    if omitted:
        text += f"\n(+{omitted} more rules omitted by the {max_tokens}-token budget)"
    return Resolution(sections, [r for r, _ in shown], omitted, text)
