"""Which rules apply to the files about to be edited, and which of those matter most for the work at hand."""
from __future__ import annotations

from dataclasses import dataclass, field

from . import sanitize, search
from .mapper import section_of
from .models import Level, Rule, Status
from .repository import RuleRepository

MAX_LABEL = 60       # longest folder name echoed back in the header
SMALL_SET = 10       # up to this many applicable rules are all sent: filtering them would save almost nothing
RELATIVE_CUTOFF = 0.3   # with a task, a rule must score at least this share of the best match to be sent


@dataclass
class Resolution:
    sections: list[str]
    rules: list[Rule]      # the rules handed over
    omitted: int           # applicable rules left out because the caller set a limit
    text: str              # what the agent is told ("" when no rule applies)
    withheld: int = 0      # active rules never served because their text contains hidden characters
    held: list[Rule] = field(default_factory=list)   # applicable rules not sent because they do not match the task
    repeated: int = 0      # applicable, relevant rules left out because the caller already has them
    untagged: int = 0      # applicable rules the agent has not tagged yet (so they are matched on their text alone)


def _tokens(s: str) -> int:
    return max(1, len(s) // 4)


def _label(section: str) -> str:
    """A folder name made safe to echo to an agent. Folder names come from whatever repository is open."""
    return sanitize.label(section, MAX_LABEL)


def _servable(project: str) -> tuple[list[Rule], int]:
    """Active rules whose text a person can fully see, and how many were held back for hiding characters."""
    stored = RuleRepository(project).with_status(Status.ACTIVE)
    active = [r for r in stored if not r.hidden]       # never hand an agent text a person cannot see
    return active, len(stored) - len(active)


def resolve(project: str, rel_paths: list[str], task: str = "", max_tokens: int | None = None,
            max_rules: int | None = None, select: bool = False, skip: frozenset[str] = frozenset(),
            include: frozenset[str] = frozenset()) -> Resolution:
    """The rules for these files, most specific first.

    By default every active rule whose scope covers the files. With `select=True` and a `task` (a sentence about the
    work), a long list is cut down to what the work needs: pinned rules (`always`), plus rules that share words with the
    task and score at least `RELATIVE_CUTOFF` of the best match; the rest (minus what the caller already has) is in `held`. Up to `SMALL_SET`
    applicable rules are all sent, because filtering so few saves nothing and a missed rule costs more.
    `skip` holds ids the caller already has; they are counted in `repeated` instead of being sent again.
    `include` holds ids the caller asked for by name: they are sent even if the task does not match them.
    `max_tokens` / `max_rules` are optional hard caps; when one is hit, serving stops at the first rule that does not fit,
    so a general rule is never served in place of a more specific one that was left out.
    """
    rel_paths = [p.strip("/") for p in rel_paths if p]
    active, withheld = _servable(project)
    picked: dict[str, tuple[Level, Rule]] = {}
    for rel in rel_paths:
        for rule in active:
            level = rule.scope.level_for(rel)
            if level is not None and (rule.id not in picked or level < picked[rule.id][0]):
                picked[rule.id] = (level, rule)

    untagged = sum(1 for _, r in picked.values() if not r.tagged)       # counted before any rule is held back
    scores: dict[str, float] = {}
    held: list[Rule] = []
    if task.strip():
        scores = {r.id: sc for r, sc in search.rank([r for _, r in picked.values()], search.query_terms(task), with_scope=False)}
        if select and len(picked) > SMALL_SET:
            top = max(scores.values(), default=0.0)
            keep = {i: lr for i, lr in picked.items()
                    if lr[1].always or i in include or (scores[i] > 0 and scores[i] >= RELATIVE_CUTOFF * top)}
            held = [lr[1] for i, lr in picked.items() if i not in keep and i not in skip]   # the caller has those already
            picked = keep
    if scores:
        ranked = sorted(picked.values(), key=lambda lr: (not lr[1].always, -scores.get(lr[1].id, 0.0), lr[0], lr[1].created))
    else:
        ranked = sorted(picked.values(), key=lambda lr: (not lr[1].always, lr[0], lr[1].created))
    forgo = skip - include
    repeated = sum(1 for _, r in ranked if r.id in forgo)
    ranked = [lr for lr in ranked if lr[1].id not in forgo]

    sections = sorted({_label(section_of(p)) for p in rel_paths})
    header = f"Rules for project `{project}` (follow before writing code; sections: {', '.join(sections) or '-'})"
    used, shown = _tokens(header), []
    for level, rule in ranked:
        line = f"- [{level.label}] {rule.text}"
        if (max_rules is not None and len(shown) >= max_rules) or (max_tokens is not None and used + _tokens(line) > max_tokens):
            break
        used += _tokens(line)
        shown.append((rule, line))
    omitted = len(ranked) - len(shown)

    text = header + "\n" + "\n".join(line for _, line in shown) if shown else ""
    if omitted and shown:
        text += f"\n(+{omitted} more applicable rules left out by the limit you set)"
    return Resolution(sections, [r for r, _ in shown], omitted, text, withheld, held, repeated, untagged)


def find(project: str, query: str, paths: list[str] | None = None, limit: int = 10) -> list[tuple[Rule, float]]:
    """Active rules matching a search, across the whole project (scope is ignored), best first. Only real matches."""
    active, _ = _servable(project)
    ranked = search.rank(active, search.query_terms(query, paths or []))
    return [(r, s) for r, s in ranked if s > 0][:limit]
