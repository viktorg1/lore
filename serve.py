#!/usr/bin/env python3
"""Local web UI for reviewing lore's rules.

    serve.py [--port 8765] [--no-open]

Opens http://127.0.0.1:<port>/?t=<token>. Stdlib only. Listens on 127.0.0.1 only, and every API call
needs the random token printed at startup (plus a matching Host/Origin), so other web pages open in
your browser cannot read or change your rules.
"""
from __future__ import annotations

import argparse
import hmac
import json
import os
import re
import secrets
import shlex
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import rules
import store

HERE = Path(__file__).resolve().parent
UI_FILE = HERE / "ui" / "index.html"
MAX_BODY = 64 * 1024
RUN_TIMEOUT = 120          # seconds a script may run
MAX_OUTPUT = 100_000       # characters of script output returned to the page
NAME = r"[A-Za-z0-9][A-Za-z0-9._-]*"
ROUTE_PROJECTS = re.compile(r"^/api/projects$")
ROUTE_RULES = re.compile(rf"^/api/projects/({NAME})/rules$")
ROUTE_RUN = re.compile(rf"^/api/projects/({NAME})/run$")
ROUTE_RULE = re.compile(rf"^/api/projects/({NAME})/rules/([0-9a-f]{{8}})$")
CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; "
       "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def _text(body: dict, key: str, *, required: bool = True, maxlen: int = 4096) -> str:
    v = body.get(key)
    if v is None or v == "":
        if required:
            raise ApiError(400, f"{key} is required")
        return ""
    if not isinstance(v, str) or "\0" in v or len(v) > maxlen:
        raise ApiError(400, f"bad {key}")
    return v.strip()


def _number(body: dict, key: str, default, kind, lo, hi):
    v = body.get(key, default)
    try:
        v = kind(v)
    except (TypeError, ValueError):
        raise ApiError(400, f"{key} must be a number")
    if not lo <= v <= hi:
        raise ApiError(400, f"{key} must be between {lo} and {hi}")
    return v


class Runner:
    """Runs lore's own scripts as subprocesses (never a shell) and reports their output.

    Only the scripts and argument shapes built in Api.run_tool / Api.register are reachable from
    the web page; arguments are passed as an argv list, with option values glued on as --opt=value
    so a value can never be read as a flag.
    """

    def __init__(self):
        self._lock = threading.Lock()  # one script at a time: they write the same files

    def run(self, argv: list[str], stdin: str | None = None, timeout: int = RUN_TIMEOUT) -> dict:
        shown = shlex.join(["python3", *argv])
        started = time.time()
        with self._lock:
            try:
                p = subprocess.run([sys.executable, *argv], cwd=HERE, input=stdin, capture_output=True,
                                   text=True, timeout=timeout, env=os.environ.copy())
                code, out = p.returncode, p.stdout + (("\n" + p.stderr) if p.stderr.strip() else "")
            except subprocess.TimeoutExpired:
                code, out = -1, f"timed out after {timeout}s"
            except OSError as e:
                code, out = -1, f"could not start: {e}"
        out = out.strip()
        if len(out) > MAX_OUTPUT:
            out = out[:MAX_OUTPUT] + "\n… (output truncated)"
        return {"ok": code == 0, "code": code, "command": shown, "output": out, "seconds": round(time.time() - started, 1)}


class Api:
    """The UI's operations, with no HTTP in sight (so they can be tested directly)."""

    def __init__(self, runner: Runner | None = None):
        self._lock = threading.Lock()  # read-modify-write of rules.json
        self.runner = runner or Runner()

    @staticmethod
    def _meta(name: str) -> dict:
        meta = store.project_meta(name)
        if not meta:
            raise ApiError(404, f"unknown project {name!r}")
        return meta

    @staticmethod
    def _view(r: dict) -> dict:
        return {"id": r["id"], "text": r["text"], "scope": rules.scope_key(r["scope"]), "status": r["status"],
                "source": r.get("source", ""), "evidence": r.get("evidence", ""), "created": r.get("created", "")}

    def projects(self) -> list[dict]:
        out = []
        for meta in store.list_projects():
            rs = rules.load(meta["name"])
            out.append({"name": meta["name"], "root": meta["root"],
                        "active": sum(r["status"] == "active" for r in rs),
                        "pending": sum(r["status"] == "pending" for r in rs)})
        return out

    def project_rules(self, name: str) -> dict:
        meta = self._meta(name)
        amap = store.load_json(store.project_dir(name) / "map.json", {"sections": {}})
        return {"name": name, "root": meta["root"], "sections": sorted(amap["sections"]),
                "rules": [self._view(r) for r in rules.load(name)]}

    def add_rule(self, name: str, body: dict) -> dict:
        self._meta(name)
        text, scope = _text(body, "text", maxlen=2000), _text(body, "scope", required=False) or "global"
        status = body.get("status", "active")
        if status not in ("active", "pending"):
            raise ApiError(400, "status must be active or pending")
        try:
            with self._lock:
                rule, outcome = rules.add_rule(name, text, rules.parse_scope(scope), status, source="ui")
        except ValueError as e:
            raise ApiError(400, str(e))
        return {"rule": self._view(rule), "outcome": outcome}

    def register(self, body: dict) -> dict:
        """memorize.py: map a project folder and register it."""
        path = _text(body, "path")
        name = _text(body, "name", required=False, maxlen=100)
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
        meta = self._meta(name)
        tool, p = body.get("tool"), body.get("params") or {}
        if not isinstance(p, dict):
            raise ApiError(400, "params must be an object")
        if tool == "remap":
            return self.runner.run(["memorize.py", f"--path={meta['root']}", f"--name={name}"])
        if tool == "train":
            argv = ["train.py", "--name", name, f"--from={_text(p, 'path')}"]
            scope = _text(p, "scope", required=False)
            if scope:
                try:
                    rules.parse_scope(scope)
                except ValueError as e:
                    raise ApiError(400, str(e))
                argv.append(f"--scope={scope}")
            argv += (["--pending"] if p.get("pending") else []) + (["--dry-run"] if p.get("dryRun") else [])
            return self.runner.run(argv)
        if tool == "discover":
            mode = p.get("mode", "preview")
            if mode not in ("preview", "save", "activate"):
                raise ApiError(400, "mode must be preview, save or activate")
            argv = ["discover.py", "--name", name,
                    f"--min-ratio={_number(p, 'minRatio', 0.9, float, 0.5, 1.0)}",
                    f"--min-files={_number(p, 'minFiles', 5, int, 1, 1000)}"]
            argv += {"preview": [], "save": ["--save"], "activate": ["--save", "--activate"]}[mode]
            return self.runner.run(argv)
        if tool == "resolve":
            paths = p.get("paths")
            if not isinstance(paths, list) or not 0 < len(paths) <= 20:
                raise ApiError(400, "give 1-20 paths")
            clean = [_text({"x": v}, "x") for v in paths]
            if any(c.startswith("-") for c in clean):
                raise ApiError(400, "paths must not start with '-'")
            return self.runner.run(["review.py", "--name", name, "resolve", *clean])
        if tool == "sync":
            return self.runner.run(["review.py", "--name", name, "sync"])
        if tool == "mcp-check":
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
        raise ApiError(400, f"unknown tool {tool!r}")

    def act(self, name: str, rule_id: str, body: dict) -> dict:
        self._meta(name)
        action = body.get("action")
        with self._lock:
            if not any(r["id"] == rule_id for r in rules.load(name)):
                raise ApiError(404, f"no rule {rule_id}")
            if action in ("approve", "unapprove"):
                rules.set_status(name, [rule_id], "active" if action == "approve" else "pending")
            elif action == "remove":
                rules.set_status(name, [rule_id], None)
                return {"removed": rule_id}
            elif action == "edit":
                text, scope = body.get("text"), body.get("scope")
                if not isinstance(text, str) or not isinstance(scope, str):
                    raise ApiError(400, "edit needs text and scope")
                try:
                    rules.edit_rule(name, rule_id, text, rules.parse_scope(scope))
                except ValueError as e:
                    raise ApiError(400, str(e))
            else:
                raise ApiError(400, f"unknown action {action!r}")
            return self._view(next(r for r in rules.load(name) if r["id"] == rule_id))


class Handler(BaseHTTPRequestHandler):
    server_version = "lore"

    def log_message(self, *args):  # the first request carries the token in its URL: log nothing
        pass

    # ----- plumbing -----
    def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, obj):
        self._send(status, json.dumps(obj).encode(), "application/json; charset=utf-8")

    def _fail(self, status: int, message: str):
        self._json(status, {"error": message})

    def _allowed_hosts(self) -> set[str]:
        port = self.server.server_address[1]
        return {f"127.0.0.1:{port}", f"localhost:{port}"}

    def _guard(self, api: bool) -> bool:
        """DNS-rebinding and CSRF defence. Returns False (after replying) when the request must stop."""
        hosts = self._allowed_hosts()
        if self.headers.get("Host", "") not in hosts:
            self._fail(403, "bad Host header")
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin not in {f"http://{h}" for h in hosts}:
            self._fail(403, "bad Origin")
            return False
        if api and not hmac.compare_digest(self.headers.get("X-Lore-Token", ""), self.server.token):
            self._fail(401, "missing or wrong token")
            return False
        return True

    # ----- routes -----
    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            if self._guard(api=False):
                try:
                    page = UI_FILE.read_bytes()  # read on every request: edits show up on reload, nothing is cached
                except OSError:
                    return self._fail(500, f"{UI_FILE} is missing")
                self._send(200, page, "text/html; charset=utf-8", {"Content-Security-Policy": CSP})
        elif path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
        elif path.startswith("/api/"):
            if not self._guard(api=True):
                return
            try:
                m = ROUTE_RULES.match(path)
                if path == "/api/projects":
                    self._json(200, self.server.api.projects())
                elif m:
                    self._json(200, self.server.api.project_rules(m.group(1)))
                else:
                    self._fail(404, "not found")
            except ApiError as e:
                self._fail(e.status, e.message)
        else:
            self._fail(404, "not found")

    def _body(self) -> dict | None:
        """Parsed JSON object body, or None after an error reply has been sent."""
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            self._fail(415, "Content-Type must be application/json")
            return None
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._fail(400, "bad Content-Length")
            return None
        if not 0 < length <= MAX_BODY:
            self._fail(413 if length > MAX_BODY else 400, "bad body size")
            return None
        try:
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError
        except ValueError:
            self._fail(400, "body must be a JSON object")
            return None
        return body

    def do_POST(self):
        path = urlparse(self.path).path
        api = self.server.api
        routes = [
            (ROUTE_PROJECTS, lambda m, b: api.register(b)),
            (ROUTE_RULES, lambda m, b: api.add_rule(m.group(1), b)),
            (ROUTE_RUN, lambda m, b: api.run_tool(m.group(1), b)),
            (ROUTE_RULE, lambda m, b: api.act(m.group(1), m.group(2), b)),
        ]
        for rx, fn in routes:
            m = rx.match(path)
            if m:
                break
        else:
            return self._fail(404, "not found")
        if not self._guard(api=True):
            return
        body = self._body()
        if body is None:
            return
        try:
            self._json(200, fn(m, body))
        except ApiError as e:
            self._fail(e.status, e.message)


def make_server(port: int = 8765, token: str | None = None) -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    srv.token = token or secrets.token_urlsafe(16)
    srv.api = Api()
    return srv


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true", help="do not open the browser")
    args = ap.parse_args(argv)
    if not UI_FILE.exists():
        print(f"error: {UI_FILE} is missing", file=sys.stderr)
        return 2
    try:
        srv = make_server(args.port)
    except OSError as e:
        print(f"error: cannot listen on 127.0.0.1:{args.port}: {e}", file=sys.stderr)
        return 2
    url = f"http://127.0.0.1:{srv.server_address[1]}/?t={srv.token}"
    print(f"lore UI: {url}\nData: {store.home()}\nCtrl+C to stop.", flush=True)
    if not args.no_open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
