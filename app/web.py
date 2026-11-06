"""Serveur web local : la page (assemblee depuis web/) et l'API JSON."""
import json
import os
import re
from http.server import BaseHTTPRequestHandler

from .config import WEB_DIR


def build_page():
    """index.html avec la feuille de style et les scripts recopies dedans : une seule page autonome
    (la telecommande telephone la recoit d'un bloc par le canal P2P)."""
    def read(name):
        with open(os.path.join(WEB_DIR, name), encoding="utf-8") as f:
            return f.read()
    page = read("index.html")
    page = re.sub(r'<link rel="stylesheet" href="([^"]+)">', lambda m: "<style>\n" + read(m.group(1)) + "</style>", page)
    page = re.sub(r'<script src="([^"]+)"></script>', lambda m: "<script>\n" + read(m.group(1)) + "</script>", page)
    return page.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    engine = None   # le moteur, donne au demarrage (damogran.py)

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, build_page(), "text/html; charset=utf-8")
        elif self.path == "/api/state":
            self._send(200, self.engine.snapshot())
        else:
            self._send(404, {"error": "not found"})

    ROUTES = {"/api/state": "patch_state", "/api/config": "set_config", "/api/input": "set_input",
              "/api/layout": "set_layout", "/api/midi": "midi_input", "/api/scene": "scene_action",
              "/api/discover": "start_discovery"}

    def do_POST(self):
        try:
            action = self.ROUTES.get(self.path)
            if not action:
                return self._send(404, {"error": "not found"})
            n = int(self.headers.get("Content-Length") or 0)
            getattr(self.engine, action)(json.loads(self.rfile.read(n) or b"{}"))
            self._send(200, {"ok": True})
        except Exception as e:  # renvoie l'erreur a l'interface plutot que de planter
            self._send(400, {"error": str(e)})
