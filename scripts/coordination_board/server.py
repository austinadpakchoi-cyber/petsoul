"""Loopback-only, allowlisted HTTP reader. No application imports or mutation API."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .projection import build_board, read_document

ASSETS = {"/": ("petsoul-live-board.html", "text/html"),
          "/board.css": ("petsoul-live-board.css", "text/css"),
          "/board.js": ("petsoul-live-board.js", "text/javascript")}


class BoardServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, repo: Path, port: int):
        self.repo = repo.resolve()
        super().__init__(("127.0.0.1", port), BoardHandler)


class BoardHandler(BaseHTTPRequestHandler):
    server_version = "PetSoulBlackboard/1"

    def log_message(self, fmt, *args):
        # Do not print source contents, arbitrary URLs or query strings.
        if len(args) > 1 and str(args[1]).startswith("5"):
            print("Blackboard request failed", flush=True)

    def trusted_request(self) -> bool:
        port = self.server.server_port
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        origin = self.headers.get("Origin")
        return self.headers.get("Host") in hosts and (not origin or origin in {f"http://{host}" for host in hosts})

    def respond(self, status: int, content, mime="application/json"):
        data = content if isinstance(content, bytes) else json.dumps(content, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", f"{mime}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'self'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def do_GET(self):
        if not self.trusted_request():
            return self.respond(403, {"error": "Only same-origin loopback requests are allowed"})
        route = urlsplit(self.path)
        root = self.server.repo / "docs" / "coordination"
        try:
            if route.path == "/api/health":
                return self.respond(200, {"application": "petsoul-live-blackboard", "repo": str(self.server.repo), "version": 1})
            if route.path == "/api/board":
                return self.respond(200, build_board(self.server.repo))
            if route.path == "/api/log":
                raw, _ = read_document(root, parse_qs(route.query).get("name", [""])[0])
                return self.respond(200, raw.encode("utf-8"), "text/plain")
            if route.path in ASSETS:
                filename, mime = ASSETS[route.path]
                return self.respond(200, (root / filename).read_bytes(), mime)
            return self.respond(404, {"error": "Not found"})
        except (ValueError, UnicodeError):
            return self.respond(400, {"error": "Invalid or changing document; refresh to retry"})
        except OSError:
            return self.respond(503, {"error": "Source unavailable; no cached success returned"})

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        self.respond(405, {"error": "Read-only board"})

    do_PUT = do_POST
    do_PATCH = do_POST
    do_DELETE = do_POST
    do_OPTIONS = do_POST
