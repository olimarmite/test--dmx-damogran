#!/usr/bin/env python3
"""Damogran - petite console web Art-Net pour spots RGB (dim + couleur).

Lance un serveur web local et envoie l'Art-Net directement (sans MagicQ).
Aucune dependance : Python 3.8+ standard uniquement.

    python damogran.py            -> http://localhost:8080 (ce PC seulement)
    python damogran.py --lan      -> accessible aussi depuis un telephone sur le meme reseau
    python damogran.py --port 9000
"""
import argparse
import json
import os
import socket
import struct
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
STATE_PATH = os.path.join(HERE, "state.json")
UI_PATH = os.path.join(HERE, "ui.html")

COLOR_TOKENS = ("R", "G", "B")
EXTRA_TOKENS = ("W", "A", "U")  # blanc, ambre, UV

DEFAULT_CONFIG = {
    "target_ip": "2.255.255.255",
    "bind_ip": "",
    "port": 6454,
    "fps": 30,
    "fixtures": [
        {"id": "f%d" % (i + 1), "name": "Spot %d" % (i + 1), "universe": 0,
         "address": 1 + i * 4, "layout": "D,R,G,B"}
        for i in range(6)
    ],
}


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def parse_layout(layout):
    """'D,R,G,B,255' -> ['D','R','G','B',255]. Un nombre = valeur fixe, '-' = 0."""
    out = []
    for tok in str(layout).replace(";", ",").replace(" ", ",").split(","):
        tok = tok.strip().upper()
        if not tok:
            continue
        if tok == "-":
            out.append(0)
        elif tok.isdigit():
            out.append(max(0, min(255, int(tok))))
        else:
            out.append(tok)
    return out


def local_ips():
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    for probe in ("2.255.255.255", "10.255.255.255", "192.168.1.1"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((probe, 6454))
            ips.add(s.getsockname()[0])
            s.close()
        except OSError:
            pass
    ips.discard("0.0.0.0")
    return sorted(ips)


class Engine:
    def __init__(self):
        self.lock = threading.Lock()
        self.config = load_json(CONFIG_PATH, None) or json.loads(json.dumps(DEFAULT_CONFIG))
        self.state = load_json(STATE_PATH, None) or {}
        self.state.setdefault("master", 255)
        self.state.setdefault("blackout", False)
        self.state.setdefault("fixtures", {})
        self.raw = None          # {"universe", "address", "value"} testeur de canal
        self.identify = {}       # id -> timestamp de fin
        self.sock = None
        self.sock_key = None
        self.last_error = ""
        self.packets = 0
        self.dirty = False
        self.wake = threading.Event()

    # ---- sortie Art-Net -------------------------------------------------
    def _socket(self):
        key = (self.config.get("bind_ip") or "",)
        if self.sock is None or self.sock_key != key:
            if self.sock:
                self.sock.close()
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            if key[0]:
                s.bind((key[0], 0))
            self.sock, self.sock_key = s, key
        return self.sock

    def build_universes(self):
        now = time.time()
        unis = {}
        master = self.state["master"] / 255.0
        blackout = self.state["blackout"]
        for fx in self.config["fixtures"]:
            uni = int(fx.get("universe", 0))
            buf = unis.setdefault(uni, bytearray(512))
            st = self.state["fixtures"].get(fx["id"], {})
            layout = parse_layout(fx.get("layout", "D,R,G,B"))
            has_dim = "D" in layout
            dim = st.get("dim", 0) / 255.0 * master
            if blackout:
                dim = 0.0
            vals = {"D": dim * 255}
            col_scale = 1.0 if has_dim else dim
            for t in COLOR_TOKENS + EXTRA_TOKENS:
                vals[t] = st.get(t.lower(), 0) * col_scale
            ident = self.identify.get(fx["id"], 0)
            if ident > now:
                on = int(now * 6) % 2 == 0
                vals = {t: (255 if on else 0) for t in ("D",) + COLOR_TOKENS + EXTRA_TOKENS}
            base = int(fx.get("address", 1)) - 1
            for i, tok in enumerate(layout):
                ch = base + i
                if 0 <= ch < 512:
                    v = tok if isinstance(tok, int) else vals.get(tok, 0)
                    buf[ch] = max(0, min(255, int(round(v))))
        if self.raw:
            uni = int(self.raw["universe"])
            buf = unis.setdefault(uni, bytearray(512))
            ch = int(self.raw["address"]) - 1
            if 0 <= ch < 512:
                buf[ch] = int(self.raw["value"])
        return unis

    @staticmethod
    def artdmx(universe, data, seq):
        return (b"Art-Net\x00" + struct.pack("<H", 0x5000) + struct.pack(">H", 14)
                + bytes([seq, 0]) + struct.pack("<H", universe & 0x7FFF)
                + struct.pack(">H", len(data)) + bytes(data))

    def run(self):
        seq = 0
        while True:
            with self.lock:
                fps = max(1, min(44, int(self.config.get("fps", 30))))
                unis = self.build_universes()
                target = (self.config.get("target_ip") or "255.255.255.255",
                          int(self.config.get("port", 6454)))
                try:
                    sock = self._socket()
                except OSError as e:
                    sock = None
                    self.last_error = "Socket: %s" % e
            seq = seq % 255 + 1
            if sock:
                try:
                    for uni, data in sorted(unis.items()):
                        sock.sendto(self.artdmx(uni, data, seq), target)
                        self.packets += 1
                    self.last_error = ""
                except OSError as e:
                    self.last_error = "Envoi vers %s : %s" % (target[0], e)
            self.wake.wait(1.0 / fps)
            self.wake.clear()

    # ---- persistance ----------------------------------------------------
    def saver(self):
        while True:
            time.sleep(1.0)
            if self.dirty:
                with self.lock:
                    self.dirty = False
                    data = json.loads(json.dumps(self.state))
                try:
                    save_json(STATE_PATH, data)
                except OSError:
                    pass

    def snapshot(self):
        with self.lock:
            return {"config": self.config, "state": self.state, "raw": self.raw,
                    "error": self.last_error, "packets": self.packets,
                    "local_ips": LOCAL_IPS}

    def patch_state(self, body):
        with self.lock:
            for fid, vals in (body.get("fixtures") or {}).items():
                cur = self.state["fixtures"].setdefault(fid, {})
                for k, v in vals.items():
                    if isinstance(v, (int, float)):
                        cur[k] = max(0, min(360 if k == "h" else 255, v))
            if "master" in body:
                self.state["master"] = max(0, min(255, int(body["master"])))
            if "blackout" in body:
                self.state["blackout"] = bool(body["blackout"])
            if "raw" in body:
                self.raw = body["raw"] or None
            for fid in body.get("identify") or []:
                self.identify[fid] = time.time() + 2.5
            self.dirty = True
        self.wake.set()

    def set_config(self, cfg):
        fixtures = []
        for i, fx in enumerate(cfg.get("fixtures") or []):
            fixtures.append({
                "id": str(fx.get("id") or "f%d_%d" % (i, int(time.time()))),
                "name": str(fx.get("name") or "Spot %d" % (i + 1))[:40],
                "universe": max(0, min(32767, int(fx.get("universe", 0)))),
                "address": max(1, min(512, int(fx.get("address", 1)))),
                "layout": str(fx.get("layout") or "D,R,G,B"),
            })
        with self.lock:
            self.config = {
                "target_ip": str(cfg.get("target_ip") or "255.255.255.255").strip(),
                "bind_ip": str(cfg.get("bind_ip") or "").strip(),
                "port": int(cfg.get("port") or 6454),
                "fps": int(cfg.get("fps") or 30),
                "fixtures": fixtures,
            }
            self.sock_key = None
            save_json(CONFIG_PATH, self.config)
        self.wake.set()


ENGINE = None
LOCAL_IPS = []


class Handler(BaseHTTPRequestHandler):
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
            with open(UI_PATH, "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
        elif self.path == "/api/state":
            self._send(200, ENGINE.snapshot())
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            if self.path == "/api/state":
                ENGINE.patch_state(body)
            elif self.path == "/api/config":
                ENGINE.set_config(body)
            else:
                return self._send(404, {"error": "not found"})
            self._send(200, {"ok": True})
        except Exception as e:  # renvoie l'erreur a l'interface plutot que de planter
            self._send(400, {"error": str(e)})


def main():
    global ENGINE, LOCAL_IPS
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--lan", action="store_true", help="ecoute sur toutes les interfaces (telephone/tablette)")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    LOCAL_IPS = local_ips()
    ENGINE = Engine()
    threading.Thread(target=ENGINE.run, daemon=True).start()
    threading.Thread(target=ENGINE.saver, daemon=True).start()

    host = "0.0.0.0" if args.lan else "127.0.0.1"
    srv = ThreadingHTTPServer((host, args.port), Handler)
    url = "http://localhost:%d" % args.port
    print("Damogran pret : %s" % url)
    if args.lan:
        for ip in LOCAL_IPS:
            print("  depuis un telephone : http://%s:%d" % (ip, args.port))
    print("Art-Net -> %s  (Ctrl+C pour quitter)" % ENGINE.config["target_ip"])
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        save_json(STATE_PATH, ENGINE.state)
        sys.exit(0)


if __name__ == "__main__":
    main()
