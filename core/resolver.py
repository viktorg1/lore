"""Which rules apply to the files about to be edited, most specific first, within a token budget."""
from __future__ import annotations

from dataclasses import dataclass

from .mapper import section_of
from .models import Level, Rule, Status
from .repository import RuleRepository

DEFAULT_MAX_TOKENS = 800
MAX_TOKENS_CEILING = 2000     # what a caller may ask for at most
MAX_RULES = 20                # rules per answer; beyond this a model follows fewer of them reliably


@dataclass
class Resolution:
    sections: list[str]
    rules: list[Rule]      # the rules that fit the budget
    omitted: int           # applicable rules that did not
    text: str              # what the agent is told ("" when no rule applies)
    withheld: int = 0      # active rules never served because their text contains hidden characters


def _tokens(s: str) -> int:
    return max(1, len(s) // 4)


def resolve(project: str, rel_paths: list[str], max_tokens: int = DEFAULT_MAX_TOKENS,
            max_rules: int = MAX_RULES) -> Resolution:
    """The rules for these files, most specific first.

    Stops at the first rule that does not fit the budget (or at `max_rules`), so a general rule is never served
    in place of a more specific one that was left out.
    """
    rel_paths = [p.strip("/") for p in rel_paths if p]
    stored = RuleRepository(project).with_status(Status.ACTIVE)
    active = [r for r in stored if not r.hidden]       # never hand an agent text a person cannot see
    withheld = len(stored) - len(active)
    picked: dict[str, tuple[Level, Rule]] = {}
    for rel in rel_paths:
        for rule in active:
            level = rule.scope.level_for(rel)
            if level is not None and (rule.id not in picked or level < picked[rule.id][0]):
                picked[rule.id] = (level, rule)
    ranked = sorted(picked.values(), key=lambda lr: (lr[0], lr[1].created))

    sections = sorted({section_of(p) for p in rel_paths})
    header = f"Rules for project `{project}` (follow before writing code; sections: {', '.join(sections) or '-'})"
    used, shown = _tokens(header), []
    for level, rule in ranked:
        line = f"- [{level.label}] {rule.text}"
        if len(shown) >= max_rules or used + _tokens(line) > max_tokens:
            break
        used += _tokens(line)
        shown.append((rule, line))
    omitted = len(ranked) - len(shown)

    text = header + "\n" + "\n".join(line for _, line in shown) if shown else ""
    if omitted and shown:
        text += f"\n(+{omitted} more applicable rules left out by the {max_tokens}-token / {max_rules}-rule limit)"
    return Resolution(sections, [r for r, _ in shown], omitted, text, withheld)
