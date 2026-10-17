"""A project's rules on disk, with dedupe: all reads and writes of rules.json go through here."""
from __future__ import annotations

from dataclasses import dataclass, field

from . import risk, sanitize, store, textutil
from .models import Outcome, Rule, Scope, Status
from .usage import UsageLog

FORMAT_VERSION = 1


@dataclass
class AddResult:
    rule: Rule
    outcome: Outcome
    conflicts: list[Rule] = field(default_factory=list)   # similar rules in the same scope that say something different


def clean_tags(title, triggers) -> tuple[str, list[str]]:
    """Validated title and trigger words for a rule (either may be empty). Raises RuleTextError.

    They are shown to the agent in lists, so text that looks like an instruction aimed at it is refused.
    """
    title = sanitize.clean_tag_text(title, "title", sanitize.MAX_TITLE) if title else ""
    if triggers is None:
        triggers = []
    if not isinstance(triggers, list):
        raise sanitize.RuleTextError("triggers must be a list of short words or phrases")
    if len(triggers) > sanitize.MAX_TRIGGERS:
        raise sanitize.RuleTextError(f"at most {sanitize.MAX_TRIGGERS} triggers")
    words = list(dict.fromkeys(sanitize.clean_tag_text(t, "trigger", sanitize.MAX_TRIGGER).lower() for t in triggers))
    reasons = risk.check(" ".join([title] + words))
    if reasons:
        raise sanitize.RuleTextError("title/triggers look like an instruction to the agent (" + "; ".join(reasons) + ")")
    return title, words


@dataclass
class TagResult:
    updated: list[Rule] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


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
            source: str = "manual", evidence: str = "", refs: list[str] | None = None,
            title: str = "", triggers: list[str] | None = None, always: bool = False, tagged_by: str = "") -> AddResult:
        """Add a rule unless a near-identical one exists in the same scope.

        - A duplicate is not added again: the existing rule is touched (hit count, new `refs`). If the new rule is
          active and the existing one is pending, the person's wording replaces the proposal and it becomes active.
        - A rule that reverses the meaning of a similar one is added, and the similar rule is returned in `conflicts`.

        Raises sanitize.RuleTextError (a ValueError) for text that is empty, too long, or contains hidden characters.
        """
        text = sanitize.clean_rule_text(text)
        evidence, source = sanitize.clean_note(evidence), sanitize.clean_note(source, 40) or "manual"
        refs = [u for u in dict.fromkeys(refs or []) if sanitize.is_http_url(u)]
        title, triggers = clean_tags(title, triggers)
        tagged = f"{tagged_by} {store.now()}" if tagged_by and (title or triggers or always) else ""
        with store.locked(self._lock):
            rules = self.all()
            existing = self._duplicate_of(rules, text, scope)
            if existing:
                existing.hits += 1
                existing.refs += [r for r in refs if r not in existing.refs]
                if tagged and not existing.tagged:      # a duplicate may still bring the judgement the first one lacked
                    existing.title, existing.triggers, existing.always, existing.tagged = title, triggers, always, tagged
                outcome = Outcome.DUPLICATE
                if existing.status is Status.PENDING and status is Status.ACTIVE:
                    existing.text, existing.status, existing.edited = text, Status.ACTIVE, store.now()
                    outcome = Outcome.PROMOTED
                self._save(rules)
                return AddResult(existing, outcome)
            conflicts = self._conflicts_with(rules, text, scope)
            rule = Rule(id=Rule.make_id(text, scope), text=text, scope=scope, status=status,
                        source=source, evidence=evidence, created=store.now(), refs=refs,
                        always=always, title=title, triggers=triggers, tagged=tagged)
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

    def set_tags(self, items: list[dict], tagged_by: str, may_unpin: bool = False) -> TagResult:
        """Set title, triggers and `always` on existing rules, leaving their text, scope and status alone.

        Each item is {id, title?, triggers?, always?}. An item that fails validation is reported and skipped; the others
        are applied. Unless `may_unpin`, `always` can only be switched on: nothing automatic may quietly stop a rule
        from being sent.
        """
        result = TagResult()
        with store.locked(self._lock):
            rules = self.all()
            by_id = {r.id: r for r in rules}
            for item in items:
                rule = by_id.get(item.get("id")) if isinstance(item, dict) else None
                if rule is None:
                    result.errors.append(f"unknown rule id {item.get('id') if isinstance(item, dict) else item!r}")
                    continue
                try:
                    title, triggers = clean_tags(item.get("title") or rule.title, item.get("triggers") if "triggers" in item else rule.triggers)
                except ValueError as e:
                    result.errors.append(f"{rule.id}: {e}")
                    continue
                want = item.get("always")
                if want is not None and not isinstance(want, bool):
                    result.errors.append(f"{rule.id}: always must be true or false")
                    continue
                rule.title, rule.triggers = title, triggers
                if want is True or (want is False and may_unpin):
                    rule.always = want
                rule.tagged = f"{tagged_by} {store.now()}"
                result.updated.append(rule)
            if result.updated:
                self._save(rules)
        return result

    def set_always(self, ids: list[str], always: bool) -> list[Rule]:
        """Pin (or unpin) rules: pinned rules are sent with every get_rules call. Only a person does this, never a tool."""
        with store.locked(self._lock):
            rules = self.all()
            found = [r for r in rules if r.id in set(ids)]
            for r in found:
                r.always = always
            if found:
                self._save(rules)
            return found

    def set_status(self, ids: list[str], status: Status, auto: bool = False) -> list[Rule]:
        """Move the rules with these ids to `status`; returns the ones found.

        `auto=True` records that no person approved the activation (see Rule.auto). A person approving or moving a rule
        back clears that mark.

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
                r.auto = store.now() if auto and status is Status.ACTIVE else ""
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
