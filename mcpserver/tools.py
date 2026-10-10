"""lore's two MCP tools: what to follow before editing, and what to remember after being corrected."""
from __future__ import annotations

import os

from core import projects, resolver
from core.mapper import section_of
from core.models import Scope, Status
from core.projects import Project
from core.repository import RuleRepository

from .protocol import McpServer, Tool

VERSION = "0.1.0"


def locate(paths: list[str]) -> tuple[Project | None, list[str]]:
    """Find the registered project for these paths and return (project, project-relative paths)."""
    cwd = os.getcwd()

    def absolute(p: str) -> str:
        return os.path.abspath(os.path.join(cwd, os.path.expanduser(p)))

    for p in paths:
        project = projects.find_for_path(absolute(p))
        if project:
            root = str(project.root)
            return project, [os.path.relpath(a, root).replace(os.sep, "/") if a.startswith(root) else q.lstrip("/")
                             for q in paths for a in [absolute(q)]]
    # relative paths with an unrelated cwd: accept a project only if exactly one contains them
    candidates = [pr for pr in projects.all_projects()
                  if any((pr.root / p).exists() for p in paths if not os.path.isabs(p))]
    if len(candidates) == 1:
        return candidates[0], [p.lstrip("./") for p in paths]
    return None, paths


def get_rules(args: dict) -> str:
    project, rels = locate(args.get("paths") or [])
    if not project:
        return "No lore project matches these paths (run memorize.py --path <project> to register one). Proceed normally."
    res = resolver.resolve(project.name, rels, int(args.get("max_tokens") or resolver.DEFAULT_MAX_TOKENS))
    return res.text or f"No rules apply to {', '.join(res.sections)} in `{project.name}` yet."


def record_feedback(args: dict) -> str:
    project, rels = locate(args.get("paths") or [])
    if not project:
        return "Not saved: no lore project matches these paths."
    try:
        if args.get("scope"):
            scope = Scope.parse(args["scope"])
        else:
            section = section_of(rels[0]) if rels else "root"
            scope = Scope.everywhere() if section == "root" else Scope.for_section(section)
        rule, outcome = RuleRepository(project.name).add(
            args["rule"], scope, Status.PENDING, source="feedback", evidence=args.get("evidence", ""))
    except (ValueError, KeyError) as e:
        return f"Not saved: {e}"
    if outcome.value == "duplicate":
        return f"Already known (rule {rule.id}, status {rule.status}); no change."
    return f"Saved as pending rule {rule.id} ({scope.key}). The user approves it with review.py."


TOOLS = [
    Tool(
        name="get_rules",
        description=(
            "Return the project's coding rules that apply to the given files. Call this BEFORE "
            "creating or editing any file, passing every file path you are about to change. "
            "Follow the returned rules; if a rule conflicts with the request, ask the user."),
        input_schema={
            "type": "object",
            "properties": {
                "paths": {"type": "array", "items": {"type": "string"},
                          "description": "Absolute or workspace-relative paths of files to edit or create."},
                "max_tokens": {"type": "integer", "description": "Budget for the answer (default 800)."},
            },
            "required": ["paths"],
        },
        handler=get_rules),
    Tool(
        name="record_feedback",
        description=(
            "Save a lesson as a PENDING rule when the user corrects your code or states a standard "
            "you violated. Write it as one short, imperative, generalizable sentence (what to do or "
            "avoid), not a description of this one edit. The user approves it before it takes effect."),
        input_schema={
            "type": "object",
            "properties": {
                "rule": {"type": "string", "description": "e.g. 'Use the repository layer for DB access; never query from route handlers.'"},
                "paths": {"type": "array", "items": {"type": "string"},
                          "description": "Files the correction concerned; used to find the project and default scope."},
                "scope": {"type": "string", "description": "global | section:<name> | glob:<pattern,...>. Default: section of the first path, else global."},
                "evidence": {"type": "string", "description": "The user's wording of the correction."},
            },
            "required": ["rule", "paths"],
        },
        handler=record_feedback),
]


def create_server() -> McpServer:
    return McpServer("lore", VERSION, TOOLS)
