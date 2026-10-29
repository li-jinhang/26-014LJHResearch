import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
from urllib.parse import urlparse
import webbrowser

from ljh_research.public import dispatch


def server_for(project_root, port=0):
    root = str(Path(project_root).resolve())
    token = secrets.token_urlsafe(32)
    web = Path(__file__).with_name("web")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, code, value, content_type="application/json; charset=utf-8"):
            data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def valid_host(self):
            return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

        def do_GET(self):
            if not self.valid_host():
                self.send(403, {"error": "Invalid host"})
                return
            route = urlparse(self.path).path
            if route == "/api/bootstrap":
                self.send(200, {"protocol_version": 1, "csrf_token": token})
                return
            name = {"/": "index.html", "/app.js": "app.js", "/styles.css": "styles.css"}.get(route)
            if not name:
                self.send(404, {"error": "Not found"})
                return
            mime = {"index.html": "text/html; charset=utf-8", "app.js": "text/javascript; charset=utf-8", "styles.css": "text/css; charset=utf-8"}[name]
            self.send(200, (web / name).read_bytes(), mime)

        def do_POST(self):
            origin = self.headers.get("Origin")
            if not self.valid_host() or origin not in {None, f"http://127.0.0.1:{self.server.server_port}"} or not secrets.compare_digest(self.headers.get("X-LJH-Token", ""), token):
                self.send(403, {"error": "Invalid local user request"})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 2_100_000:
                    raise ValueError("Invalid request size")
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError("Request body must be a JSON object")
                if self.path == "/api/controller/start":
                    task_id = body["task_id"]
                    checked = dispatch({"protocol_version": 1, "project_root": root, "method": "task.get", "params": {"task_id": task_id}})
                    if not checked["ok"]:
                        self.send(400, checked)
                        return
                    task = checked["result"]
                    if not task["authorized"] or task["revoked"] or task["status"] not in {"queued", "paused"}:
                        raise ValueError("Task must be authorized and ready before starting")
                    result = dispatch({"protocol_version": 1, "project_root": root,
                                       "method": "controller.start", "params": {"task_id": task_id}},
                                      human=True, evidence="User started the configured controller in the local panel")
                    self.send(200 if result["ok"] else 400, result)
                    return
                if self.path != "/api/operation":
                    self.send(404, {"error": "Unknown operation route"})
                    return
                request = {**body, "project_root": root}
                result = dispatch(request, human=True, evidence=body.get("user_evidence", "User initiated this operation in the local panel"))
                self.send(200 if result["ok"] else 400, result)
            except (ValueError, KeyError, ImportError, OSError) as exc:
                self.send(400, {"ok": False, "error": {"code": "panel_operation", "message": str(exc)}})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description="Local LJH Research browser panel")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()
    server = server_for(args.project_root, args.port)
    url = f"http://127.0.0.1:{server.server_port}"
    print(json.dumps({"url": url, "project_root": str(Path(args.project_root).resolve())}), flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
