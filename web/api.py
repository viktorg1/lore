"""What the page can do, with no HTTP in sight (so it can be tested directly)."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from core import projects, store
from core.models import Rule, Scope, Status
from core.projects import Project
from core.repository import RuleRepository

from .runner import Runner
from .validation import ApiError, number_field, text_field

MAX_RESOLVE_PATHS = 20


def rule_view(r: Rule) -> dict:
    return {"id": r.id, "text": r.text, "scope": r.scope.key, "status": r.status.value,
            "source": r.source, "evidence": r.evidence, "created": r.created}


def parse_scope(spec: str) -> Scope:
    try:
        return Scope.parse(spec)
    except ValueError as e:
        raise ApiError(400, str(e))


class Api:
    def __init__(self, runner: Runner | None = None):
        self._lock = threading.Lock()  # read-modify-write of rules.json
        self.runner = runner or Runner()
        # tool name -> handler(project, params); each builds the argv of one lore script
        self._tools = {"remap": self._tool_remap, "train": self._tool_train, "discover": self._tool_discover,
                       "resolve": self._tool_resolve, "sync": self._tool_sync, "mcp-check": self._tool_mcp_check}

    @staticmethod
    def _project(name: str) -> Project:
        project = projects.get(name)
        if project is None:
            raise ApiError(404, f"unknown project {name!r}")
        return project

    # ----- reading -----
    def projects(self) -> list[dict]:
        out = []
        for p in projects.all_projects():
            repo = RuleRepository(p.name)
            out.append({"name": p.name, "root": str(p.root),
                        "active": len(repo.with_status(Status.ACTIVE)), "pending": len(repo.with_status(Status.PENDING))})
        return out

    def project_rules(self, name: str) -> dict:
        project = self._project(name)
        return {"name": name, "root": str(project.root), "sections": sorted(project.load_map()["sections"]),
                "rules": [rule_view(r) for r in RuleRepository(name).all()]}

    # ----- rules -----
    def add_rule(self, name: str, body: dict) -> dict:
        self._project(name)
        text = text_field(body, "text", maxlen=2000)
        scope = parse_scope(text_field(body, "scope", required=False) or "global")
        try:
            status = Status(body.get("status", "active"))
        except ValueError:
            raise ApiError(400, "status must be active or pending")
        try:
            with self._lock:
                rule, outcome = RuleRepository(name).add(text, scope, status, source="ui")
        except ValueError as e:
            raise ApiError(400, str(e))
        return {"rule": rule_view(rule), "outcome": outcome.value}

    def act(self, name: str, rule_id: str, body: dict) -> dict:
        """approve / unapprove / remove / edit one rule."""
        self._project(name)
        action, repo = body.get("action"), RuleRepository(name)
        with self._lock:
            if repo.get(rule_id) is None:
                raise ApiError(404, f"no rule {rule_id}")
            if action == "approve":
                repo.set_status([rule_id], Status.ACTIVE)
            elif action == "unapprove":
                repo.set_status([rule_id], Status.PENDING)
            elif action == "remove":
                repo.remove([rule_id])
                return {"removed": rule_id}
            elif action == "edit":
                text, scope = body.get("text"), body.get("scope")
                if not isinstance(text, str) or not isinstance(scope, str):
                    raise ApiError(400, "edit needs text and scope")
                try:
                    repo.edit(rule_id, text, parse_scope(scope))
                except ValueError as e:
                    raise ApiError(400, str(e))
            else:
                raise ApiError(400, f"unknown action {action!r}")
            return rule_view(repo.get(rule_id))

    # ----- scripts -----
    def register(self, body: dict) -> dict:
        """memorize.py: map a project folder and register it."""
        path = text_field(body, "path")
        name = text_field(body, "name", required=False, maxlen=100)
        if name:
            try:
                store.validate_name(name)
            except ValueError as e:
                raise ApiError(400, str(e))
        argv = ["memorize.py", f"--path={path}"] + ([f"--name={name}"] if name else []) + (["--no-import"] if body.get("noImport") else [])
        res = self.runner.run(argv)
        res["name"] = name or Path(os.path.expanduser(path)).resolve().name
        return res

    def run_tool(self, name: str, body: dict) -> dict:
        project = self._project(name)
        params = body.get("params") or {}
        if not isinstance(params, dict):
            raise ApiError(400, "params must be an object")
        handler = self._tools.get(body.get("tool"))
        if handler is None:
            raise ApiError(400, f"unknown tool {body.get('tool')!r}")
        return handler(project, params)

    def _tool_remap(self, project: Project, p: dict) -> dict:
        return self.runner.run(["memorize.py", f"--path={project.root}", f"--name={project.name}"])

    def _tool_train(self, project: Project, p: dict) -> dict:
        argv = ["train.py", "--name", project.name, f"--from={text_field(p, 'path')}"]
        scope = text_field(p, "scope", required=False)
        if scope:
            parse_scope(scope)  # reject early with a readable message
            argv.append(f"--scope={scope}")
        argv += (["--pending"] if p.get("pending") else []) + (["--dry-run"] if p.get("dryRun") else [])
        return self.runner.run(argv)

    def _tool_discover(self, project: Project, p: dict) -> dict:
        flags = {"preview": [], "save": ["--save"], "activate": ["--save", "--activate"]}
        mode = p.get("mode", "preview")
        if mode not in flags:
            raise ApiError(400, "mode must be preview, save or activate")
        return self.runner.run(["discover.py", "--name", project.name,
                                f"--min-ratio={number_field(p, 'minRatio', 0.9, float, 0.5, 1.0)}",
                                f"--min-files={number_field(p, 'minFiles', 5, int, 1, 1000)}", *flags[mode]])

    def _tool_resolve(self, project: Project, p: dict) -> dict:
        paths = p.get("paths")
        if not isinstance(paths, list) or not 0 < len(paths) <= MAX_RESOLVE_PATHS:
            raise ApiError(400, f"give 1-{MAX_RESOLVE_PATHS} paths")
        clean = [text_field({"x": v}, "x") for v in paths]
        if any(c.startswith("-") for c in clean):
            raise ApiError(400, "paths must not start with '-'")
        return self.runner.run(["review.py", "--name", project.name, "resolve", *clean])

    def _tool_sync(self, project: Project, p: dict) -> dict:
        return self.runner.run(["review.py", "--name", project.name, "sync"])

    def _tool_mcp_check(self, project: Project, p: dict) -> dict:
        """Do the MCP handshake against mcp_server.py, the way a client would."""
        msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
        res = self.runner.run(["mcp_server.py"], stdin="\n".join(json.dumps(m) for m in msgs) + "\n", timeout=20)
        try:
            lines = [json.loads(l) for l in res["output"].splitlines() if l.startswith("{")]
            tools = [t["name"] for t in lines[1]["result"]["tools"]]
            res["output"] = f"mcp_server.py answers the MCP handshake.\nServer: {lines[0]['result']['serverInfo']['name']}\nTools: {', '.join(tools)}"
        except (IndexError, KeyError, ValueError, TypeError):
            res["ok"] = False
        return res
