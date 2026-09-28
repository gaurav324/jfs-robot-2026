"""
Zero-dependency HTTP server for the FLL simulator.

Serves the browser UI from static/ and exposes a small JSON API:
  POST /api/run     {code, robot, board} -> simulation trace
  GET  /api/boards  -> list of built-in board names
  GET  /api/board/<name>   -> a board's JSON
  GET  /api/example/<name> -> an example program's source
"""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .simulator import run_code

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")
BOARDS = os.path.join(HERE, "boards")
EXAMPLES = os.path.join(HERE, "examples")

# Only one simulation at a time (the API classes use a single global context).
_RUN_LOCK = threading.Lock()

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "FLLSim/1.0"

    def log_message(self, fmt, *args):
        pass  # keep the console quiet

    # -- helpers -------------------------------------------------------------
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path):
        if not os.path.isfile(path):
            return self._send(404, {"error": "not found"})
        ext = os.path.splitext(path)[1]
        ctype = _CONTENT_TYPES.get(ext, "application/octet-stream")
        with open(path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def _list_json_dir(self, path):
        if not os.path.isdir(path):
            return []
        return sorted(os.path.splitext(f)[0] for f in os.listdir(path)
                      if f.endswith(".json"))

    # -- routes --------------------------------------------------------------
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/" or path == "":
            return self._send_file(os.path.join(STATIC, "index.html"))
        if path == "/api/boards":
            return self._send(200, self._list_json_dir(BOARDS))
        if path == "/api/examples":
            names = []
            if os.path.isdir(EXAMPLES):
                names = sorted(os.path.splitext(f)[0] for f in os.listdir(EXAMPLES)
                               if f.endswith(".py"))
            return self._send(200, names)
        if path.startswith("/api/board/"):
            name = os.path.basename(path[len("/api/board/"):])
            return self._send_file(os.path.join(BOARDS, name + ".json"))
        if path.startswith("/api/example/"):
            name = os.path.basename(path[len("/api/example/"):])
            fp = os.path.join(EXAMPLES, name + ".py")
            if not os.path.isfile(fp):
                return self._send(404, {"error": "not found"})
            with open(fp, "r") as f:
                return self._send(200, {"name": name, "code": f.read()})
        if path.startswith("/static/"):
            return self._send_file(os.path.join(STATIC, os.path.relpath(path, "/static")))
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/run":
            data = self._read_json()
            code = data.get("code", "")
            robot = data.get("robot", {})
            board = data.get("board", {})
            with _RUN_LOCK:
                try:
                    result = run_code(code, robot, board)
                except Exception as e:  # last-resort guard
                    return self._send(200, {"ok": False, "error":
                                            {"type": "error", "message": str(e)},
                                            "frames": [], "path": [], "events": [],
                                            "console": []})
            return self._send(200, result)
        return self._send(404, {"error": "not found"})


def serve(host="127.0.0.1", port=8000):
    httpd = ThreadingHTTPServer((host, port), Handler)
    return httpd
