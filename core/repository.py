"""A project's rules on disk, with dedupe: all reads and writes of rules.json go through here."""
from __future__ import annotations

from dataclasses import dataclass, field

from . import sanitize, store, textutil
from .models import Outcome, Rule, Scope, Status
from .usage import UsageLog

FORMAT_VERSION = 1


@dataclass
class AddResult:
    rule: Rule
    outcome: Outcome
    conflicts: list[Rule] = field(default_factory=list)   # similar rules in the same scope that say something different


class RuleRepository:
    def __init__(self, project: str):
        self.project = project
        self._path = store.project_dir(project) / "rules.json"
        self._lock = store.project_dir(project) / ".rules.lock"

    # --- reading ---
    def all(self) -> list[Rule]:
        data = store.load_json(self._path, {"version": FORMAT_VERSION, "rules": []})
        return [Rule.from_dict(d) for d in data["rules"]]

    def with_status(self, status: Status) -> list[Rule]:
        return [r for r in self.all() if r.status is status]

    def get(self, rule_id: str) -> Rule | None:
        return next((r for r in self.all() if r.id == rule_id), None)

    def _save(self, rules: list[Rule]) -> None:
        store.save_json(self._path, {"version": FORMAT_VERSION, "rules": [r.to_dict() for r in rules]})

    @staticmethod
    def _duplicate_of(rules: list[Rule], text: str, scope: Scope, ignore: Rule | None = None) -> Rule | None:
        """An existing rule with the same scope and near-identical wording that means the same thing."""
        return next((r for r in rules if r is not ignore and r.scope.key == scope.key and textutil.similar(r.text, text)
                     and not textutil.contradicts(r.text, text)), None)

    @staticmethod
    def _conflicts_with(rules: list[Rule], text: str, scope: Scope, ignore: Rule | None = None) -> list[Rule]:
        """Rules in the same scope worded much like `text` but reversing its meaning (tabs vs spaces, do vs don't)."""
        return [r for r in rules if r is not ignore and r.scope.key == scope.key and textutil.related(r.text, text)
                and textutil.contradicts(r.text, text)]

    # --- writing ---
    def add(self, text: str, scope: Scope, status: Status = Status.PENDING,
            source: str = "manual", evidence: str = "", refs: list[str] | None = None) -> AddResult:
        """Add a rule unless a near-identical one exists in the same scope.

        - A duplicate is not added again: the existing rule is touched (hit count, new `refs`). If the new rule is
          active and the existing one is pending, the person's wording replaces the proposal and it becomes active.
        - A rule that reverses the meaning of a similar one is added, and the similar rule is returned in `conflicts`.

        Raises sanitize.RuleTextError (a ValueError) for text that is empty, too long, or contains hidden characters.
        """
        text = sanitize.clean_rule_text(text)
        evidence, source = sanitize.clean_note(evidence), sanitize.clean_note(source, 40) or "manual"
        refs = [u for u in dict.fromkeys(refs or []) if sanitize.is_http_url(u)]
        with store.locked(self._lock):
            rules = self.all()
            existing = self._duplicate_of(rules, text, scope)
            if existing:
                existing.hits += 1
                existing.refs += [r for r in refs if r not in existing.refs]
                outcome = Outcome.DUPLICATE
                if existing.status is Status.PENDING and status is Status.ACTIVE:
                    existing.text, existing.status, existing.edited = text, Status.ACTIVE, store.now()
                    outcome = Outcome.PROMOTED
                self._save(rules)
                return AddResult(existing, outcome)
            conflicts = self._conflicts_with(rules, text, scope)
            rule = Rule(id=Rule.make_id(text, scope), text=text, scope=scope, status=status,
                        source=source, evidence=evidence, created=store.now(), refs=refs)
            rules.append(rule)
            self._save(rules)
            return AddResult(rule, Outcome.ADDED, conflicts)

    def edit(self, rule_id: str, text: str | None = None, scope: Scope | None = None) -> Rule:
        """Change a rule's text and/or scope in place (id and status are kept).

        Raises KeyError for an unknown id and ValueError for bad text or a clash with another rule.
        """
        new_text = sanitize.clean_rule_text(text) if text is not None else None
        with store.locked(self._lock):
            rules = self.all()
            rule = next((r for r in rules if r.id == rule_id), None)
            if rule is None:
                raise KeyError(rule_id)
            new_text = new_text if new_text is not None else rule.text
            new_scope = scope if scope is not None else rule.scope
            clash = self._duplicate_of(rules, new_text, new_scope, ignore=rule)
            if clash:
                raise ValueError(f"duplicate of rule {clash.id}")
            rule.text, rule.scope, rule.edited = new_text, new_scope, store.now()
            self._save(rules)
            return rule

    def set_status(self, ids: list[str], status: Status) -> list[Rule]:
        """Move the rules with these ids to `status`; returns the ones found.

        Raises RuleTextError, changing nothing, if asked to activate a rule whose text contains hidden characters.
        """
        with store.locked(self._lock):
            rules = self.all()
            hit = [r for r in rules if r.id in ids]
            if status is Status.ACTIVE:
                unsafe = [r.id for r in hit if r.hidden]
                if unsafe:
                    raise sanitize.RuleTextError(
                        f"rule(s) {', '.join(unsafe)} contain hidden characters; edit or reject them before approving")
            for r in hit:
                r.status = status
            self._save(rules)
            return hit

    def remove(self, ids: list[str]) -> list[Rule]:
        """Delete the rules with these ids; returns the ones found."""
        with store.locked(self._lock):
            rules = self.all()
            gone = [r for r in rules if r.id in ids]
            self._save([r for r in rules if r.id not in ids])
            UsageLog(self.project).forget(r.id for r in gone)
            return gone
