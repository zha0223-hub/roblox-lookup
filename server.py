"""Serves index.html and relays GET requests to Roblox's public API.
Local:  python server.py  ->  http://localhost:8000
Render: start command `python server.py` (uses the PORT Render provides)."""
import os, urllib.request, urllib.error, urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
SERVICES = {"users", "thumbnails", "friends", "groups", "games", "badges"}
PORT = int(os.environ.get("PORT", 8000))
HOST = "0.0.0.0" if "PORT" in os.environ else "127.0.0.1"

class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/"):
            parts = self.path[5:].split("/", 1)
            if parts[0] not in SERVICES or len(parts) < 2:
                return self._send(400, b'{"error":"bad service"}', "application/json")
            url = f"https://{parts[0]}.roblox.com/{parts[1]}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=15) as r:
                    return self._send(r.status, r.read(), "application/json")
            except urllib.error.HTTPError as e:
                return self._send(e.code, e.read() or b"{}", "application/json")
            except Exception as e:
                return self._send(502, ('{"error":"%s"}' % str(e).replace('"', "'")).encode(), "application/json")
        if self.path.startswith("/img?"):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            target = (q.get("u") or [""])[0]
            p = urllib.parse.urlparse(target)
            if p.scheme != "https" or not (p.hostname or "").endswith(".rbxcdn.com"):
                return self._send(400, b"bad image url", "text/plain")
            req = urllib.request.Request(target, headers={"User-Agent": "Mozilla/5.0"})
            try:
                with urllib.request.urlopen(req, timeout=15) as r:
                    body = r.read()
                    ctype = r.headers.get("Content-Type", "image/png")
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                return self.wfile.write(body)
            except Exception:
                return self._send(502, b"image fetch failed", "text/plain")
        with open(os.path.join(HERE, "index.html"), "rb") as f:
            self._send(200, f.read(), "text/html; charset=utf-8")

    def log_message(self, *a):
        pass

if __name__ == "__main__":
    print(f"Running on http://localhost:{PORT} (Ctrl+C to stop)", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
