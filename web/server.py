"""The HTTP layer: security checks, routing, JSON in and out. All behaviour lives in web.api."""
from __future__ import annotations

import argparse
import hmac
import json
import re
import secrets
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from core import store

from .api import Api
from .validation import ApiError

UI_FILE = Path(__file__).resolve().parent / "index.html"
MAX_BODY = 64 * 1024
CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; "
       "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")

NAME = r"[A-Za-z0-9][A-Za-z0-9._-]*"
# (path regex, handler(api, match, body)) per method; first match wins
GET_ROUTES = [
    (re.compile(r"^/api/projects$"), lambda api, m: api.projects()),
    (re.compile(rf"^/api/projects/({NAME})/rules$"), lambda api, m: api.project_rules(m.group(1))),
]
POST_ROUTES = [
    (re.compile(r"^/api/projects$"), lambda api, m, b: api.register(b)),
    (re.compile(rf"^/api/projects/({NAME})/rules$"), lambda api, m, b: api.add_rule(m.group(1), b)),
    (re.compile(rf"^/api/projects/({NAME})/run$"), lambda api, m, b: api.run_tool(m.group(1), b)),
    (re.compile(rf"^/api/projects/({NAME})/rules/([0-9a-f]{{8}})$"), lambda api, m, b: api.act(m.group(1), m.group(2), b)),
]


class Handler(BaseHTTPRequestHandler):
    server_version = "lore"

    def log_message(self, *args):  # the first request carries the token in its URL: log nothing
        pass

    # ----- replies -----
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

    # ----- checks -----
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

    def _json_body(self) -> dict | None:
        """The request's JSON object, or None after an error reply has been sent."""
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

    # ----- methods -----
    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._serve_page()
        if path == "/favicon.ico":
            return self._send(204, b"", "image/x-icon")
        if not path.startswith("/api/"):
            return self._fail(404, "not found")
        if not self._guard(api=True):
            return
        for rx, handler in GET_ROUTES:
            m = rx.match(path)
            if m:
                try:
                    return self._json(200, handler(self.server.api, m))
                except ApiError as e:
                    return self._fail(e.status, e.message)
        self._fail(404, "not found")

    def do_POST(self):
        path = urlparse(self.path).path
        route = next(((h, m) for rx, h in POST_ROUTES if (m := rx.match(path))), None)
        if route is None:
            return self._fail(404, "not found")
        if not self._guard(api=True):
            return
        body = self._json_body()
        if body is None:
            return
        handler, match = route
        try:
            self._json(200, handler(self.server.api, match, body))
        except ApiError as e:
            self._fail(e.status, e.message)

    def _serve_page(self):
        if not self._guard(api=False):
            return
        try:
            page = UI_FILE.read_bytes()  # read on every request: edits show up on reload, nothing is cached
        except OSError:
            return self._fail(500, f"{UI_FILE} is missing")
        self._send(200, page, "text/html; charset=utf-8", {"Content-Security-Policy": CSP})


HELP = """Local web UI for lore's rules.

    serve.py [--port 8765] [--no-open]

Opens http://127.0.0.1:<port>/?t=<token>. Stdlib only. Listens on 127.0.0.1 only, and every API call
needs the random token printed at startup (plus a matching Host/Origin), so other web pages open in
your browser cannot read or change your rules or start scripts.
"""


def make_server(port: int = 8765, token: str | None = None) -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    srv.token = token or secrets.token_urlsafe(16)
    srv.api = Api()
    return srv


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=HELP, formatter_class=argparse.RawDescriptionHelpFormatter)
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
