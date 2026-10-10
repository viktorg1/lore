"""A project's rules on disk, with dedupe: all reads and writes of rules.json go through here."""
from __future__ import annotations

from typing import NamedTuple

from . import store, textutil
from .models import Outcome, Rule, Scope, Status

FORMAT_VERSION = 1


class AddResult(NamedTuple):
    rule: Rule
    outcome: Outcome


class RuleRepository:
    def __init__(self, project: str):
        self.project = project
        self._path = store.project_dir(project) / "rules.json"

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
        """An existing rule with the same scope and near-identical wording."""
        return next((r for r in rules if r is not ignore and r.scope.key == scope.key and textutil.similar(r.text, text)), None)

    # --- writing ---
    def add(self, text: str, scope: Scope, status: Status = Status.PENDING,
            source: str = "manual", evidence: str = "") -> AddResult:
        """Add a rule unless a near-identical one exists in the same scope (then that one is touched instead)."""
        text = textutil.squash(text)
        if not text:
            raise ValueError("empty rule")
        rules = self.all()
        existing = self._duplicate_of(rules, text, scope)
        if existing:
            existing.hits += 1
            outcome = Outcome.DUPLICATE
            if existing.status is Status.PENDING and status is Status.ACTIVE:
                existing.status, outcome = Status.ACTIVE, Outcome.PROMOTED
            self._save(rules)
            return AddResult(existing, outcome)
        rule = Rule(id=Rule.make_id(text, scope), text=text, scope=scope, status=status,
                    source=source, evidence=evidence, created=store.now())
        rules.append(rule)
        self._save(rules)
        return AddResult(rule, Outcome.ADDED)

    def edit(self, rule_id: str, text: str | None = None, scope: Scope | None = None) -> Rule:
        """Change a rule's text and/or scope in place (id and status are kept).

        Raises KeyError for an unknown id and ValueError for empty text or a clash with another rule.
        """
        rules = self.all()
        rule = next((r for r in rules if r.id == rule_id), None)
        if rule is None:
            raise KeyError(rule_id)
        new_text = textutil.squash(text) if text is not None else rule.text
        if not new_text:
            raise ValueError("empty rule")
        new_scope = scope if scope is not None else rule.scope
        clash = self._duplicate_of(rules, new_text, new_scope, ignore=rule)
        if clash:
            raise ValueError(f"duplicate of rule {clash.id}")
        rule.text, rule.scope, rule.edited = new_text, new_scope, store.now()
        self._save(rules)
        return rule

    def set_status(self, ids: list[str], status: Status) -> list[Rule]:
        """Move the rules with these ids to `status`; returns the ones found."""
        rules = self.all()
        hit = [r for r in rules if r.id in ids]
        for r in hit:
            r.status = status
        self._save(rules)
        return hit

    def remove(self, ids: list[str]) -> list[Rule]:
        """Delete the rules with these ids; returns the ones found."""
        rules = self.all()
        gone = [r for r in rules if r.id in ids]
        self._save([r for r in rules if r.id not in ids])
        return gone
