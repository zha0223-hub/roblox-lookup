"""Serves index.html, relays Roblox public API calls, and offers a keyed JSON API.
Local:  python server.py  ->  http://localhost:8000
Render: start command `python server.py`. Set env var SECRET_KEY so API keys survive restarts."""
import os, json, hmac, hashlib, secrets, urllib.request, urllib.error, urllib.parse
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
SERVICES = {"users", "thumbnails", "friends", "groups", "games", "badges"}
PORT = int(os.environ.get("PORT", 8000))
HOST = "0.0.0.0" if "PORT" in os.environ else "127.0.0.1"
SECRET = (os.environ.get("SECRET_KEY") or secrets.token_hex(32)).encode()
UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

def sign(nonce):
    return hmac.new(SECRET, nonce.encode(), hashlib.sha256).hexdigest()[:24]

def new_key():
    nonce = secrets.token_hex(8)
    return f"rbl_{nonce}.{sign(nonce)}"

def valid_key(key):
    try:
        head, sig = key.split(".", 1)
        nonce = head[4:]
        return head.startswith("rbl_") and hmac.compare_digest(sig, sign(nonce))
    except Exception:
        return False

def rb(service, path):
    try:
        req = urllib.request.Request(f"https://{service}.roblox.com/{path}", headers=UA)
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception:
        return None

def profile(name):
    q = urllib.parse.quote(name)
    res = rb("users", f"v1/users/search?keyword={q}&limit=10")
    if res is None:
        return 502, {"error": "Roblox unreachable"}
    found = next((u for u in res.get("data", []) if u["name"].lower() == name.lower()), None)
    if not found:
        return 404, {"error": "user not found"}
    i = found["id"]
    jobs = {
        "details": ("users", f"v1/users/{i}"),
        "avatar": ("thumbnails", f"v1/users/avatar?userIds={i}&size=420x420&format=Png"),
        "headshot": ("thumbnails", f"v1/users/avatar-headshot?userIds={i}&size=420x420&format=Png"),
        "friends_count": ("friends", f"v1/users/{i}/friends/count"),
        "followers_count": ("friends", f"v1/users/{i}/followers/count"),
        "following_count": ("friends", f"v1/users/{i}/followings/count"),
        "groups": ("groups", f"v2/users/{i}/groups/roles"),
        "games": ("games", f"v2/users/{i}/games?limit=50&sortOrder=Asc"),
        "badges": ("badges", f"v1/users/{i}/badges?limit=30&sortOrder=Desc"),
        "friends": ("friends", f"v1/users/{i}/friends"),
        "past_names": ("users", f"v1/users/{i}/username-history?limit=10&sortOrder=Desc"),
    }
    with ThreadPoolExecutor(8) as ex:
        futs = {k: ex.submit(rb, *v) for k, v in jobs.items()}
        r = {k: f.result() for k, f in futs.items()}
    img = lambda d: ((d or {}).get("data") or [{}])[0].get("imageUrl")
    d = r["details"] or {}
    return 200, {
        "id": i, "username": found["name"], "displayName": d.get("displayName") or found.get("displayName"),
        "description": d.get("description"), "created": d.get("created"),
        "isBanned": d.get("isBanned"), "hasVerifiedBadge": d.get("hasVerifiedBadge"),
        "avatarUrl": img(r["avatar"]), "headshotUrl": img(r["headshot"]),
        "friendsCount": (r["friends_count"] or {}).get("count"),
        "followersCount": (r["followers_count"] or {}).get("count"),
        "followingCount": (r["following_count"] or {}).get("count"),
        "pastNames": [x["name"] for x in (r["past_names"] or {}).get("data", [])],
        "groups": [{"id": g["group"]["id"], "name": g["group"]["name"], "role": g["role"]["name"],
                    "memberCount": g["group"].get("memberCount")} for g in (r["groups"] or {}).get("data", [])],
        "games": [{"id": g["id"], "name": g["name"], "visits": g.get("placeVisits"),
                   "placeId": (g.get("rootPlace") or {}).get("id")} for g in (r["games"] or {}).get("data", [])],
        "badges": [{"id": b["id"], "name": b["name"]} for b in (r["badges"] or {}).get("data", [])],
        "friends": [{"id": f["id"], "username": f["name"], "displayName": f["displayName"]}
                    for f in (r["friends"] or {}).get("data", [])],
    }

class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj).encode(), "application/json")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "X-API-Key")
        self.end_headers()

    def do_POST(self):
        if self.path.split("?")[0] == "/keys/new":
            return self._json(200, {"key": new_key()})
        self._json(404, {"error": "not found"})

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        if url.path.startswith("/v1/user/"):
            q = urllib.parse.parse_qs(url.query)
            key = self.headers.get("X-API-Key") or (q.get("key") or [""])[0]
            if not valid_key(key):
                return self._json(401, {"error": "missing or invalid API key"})
            name = urllib.parse.unquote(url.path[len("/v1/user/"):]).strip()
            if not name:
                return self._json(400, {"error": "username required"})
            code, obj = profile(name)
            return self._json(code, obj)
        if self.path.startswith("/api/"):
            parts = self.path[5:].split("/", 1)
            if parts[0] not in SERVICES or len(parts) < 2:
                return self._json(400, {"error": "bad service"})
            req = urllib.request.Request(f"https://{parts[0]}.roblox.com/{parts[1]}", headers=UA)
            try:
                with urllib.request.urlopen(req, timeout=15) as r:
                    return self._send(r.status, r.read(), "application/json")
            except urllib.error.HTTPError as e:
                return self._send(e.code, e.read() or b"{}", "application/json")
            except Exception as e:
                return self._json(502, {"error": str(e)})
        if self.path.startswith("/img?"):
            target = (urllib.parse.parse_qs(url.query).get("u") or [""])[0]
            p = urllib.parse.urlparse(target)
            if p.scheme != "https" or not (p.hostname or "").endswith(".rbxcdn.com"):
                return self._send(400, b"bad image url", "text/plain")
            try:
                with urllib.request.urlopen(urllib.request.Request(target, headers={"User-Agent": "Mozilla/5.0"}), timeout=15) as r:
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
