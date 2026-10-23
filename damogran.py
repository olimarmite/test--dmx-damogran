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
import random
import select
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


# ---- decouverte : ArtPoll (nodes) + RDM via Art-Net (projecteurs) ---------------
OP_POLL, OP_POLL_REPLY, OP_DMX = 0x2000, 0x2100, 0x5000
OP_TOD_REQUEST, OP_TOD_DATA, OP_TOD_CONTROL, OP_RDM = 0x8000, 0x8100, 0x8200, 0x8300

PID_DEVICE_INFO = 0x0060
PID_MODEL_DESCRIPTION = 0x0080
PID_MANUFACTURER_LABEL = 0x0081
PID_DEVICE_LABEL = 0x0082
PID_PERSONALITY_DESCRIPTION = 0x00E1
PID_SLOT_INFO = 0x0120
PID_DEFAULT_SLOT_VALUE = 0x0121

# Identifiants de slot RDM (E1.20 table C-2) -> lettre de canal Damogran
SLOT_TOKENS = {0x0001: "D", 0x0002: "D", 0x0205: "R", 0x0206: "G", 0x0207: "B",
               0x0211: "A", 0x0212: "W", 0x0213: "W", 0x0214: "W"}


def art_header(op):
    return b"Art-Net\x00" + struct.pack("<H", op) + b"\x00\x0e"


def port_bytes(universe):
    return bytes([(universe >> 8) & 0x7F]), bytes([universe & 0xFF])


def rdm_get(dest, src, tn, pid, pd=b""):
    """Requete RDM GET, sans le start code 0xCC (comme l'attend ArtRdm), checksum inclus."""
    msg = (bytes([0xCC, 0x01, 24 + len(pd)]) + dest + src + bytes([tn, 1, 0]) + b"\x00\x00"
           + bytes([0x20]) + struct.pack(">H", pid) + bytes([len(pd)]) + pd)
    return msg[1:] + struct.pack(">H", sum(msg) & 0xFFFF)


def ascii_text(b):
    return b.split(b"\x00")[0].decode("ascii", "replace").strip()


def uid_text(uid):
    return "%04X:%08X" % struct.unpack(">HI", uid)


def guess_layout(footprint):
    if footprint <= 3:
        return ",".join("RGB"[:max(footprint, 1)])
    return ",".join(["D", "R", "G", "B"] + ["0"] * (footprint - 4))


def broadcast_targets(target_ip):
    out = [target_ip, "255.255.255.255", "2.255.255.255", "10.255.255.255"]
    for ip in LOCAL_IPS:
        if not ip.startswith("127."):
            out.append(ip.rsplit(".", 1)[0] + ".255")
    return list(dict.fromkeys(t for t in out if t))


class Discovery:
    def __init__(self):
        self.src_uid = struct.pack(">HI", 0x7FF0, random.getrandbits(32))  # plage "prototype" ESTA
        self.tn = 0
        self.reset()

    def reset(self):
        self.running = False
        self.phase = ""
        self.error = ""
        self.nodes = {}       # ip -> infos
        self.devices = {}     # uid (bytes) -> infos
        self.queue = []       # requetes RDM a envoyer
        self.inflight = None
        self.step = None
        self.next_at = 0.0
        self.flushed = False

    def start(self, now, rx_ok):
        self.reset()
        if not rx_ok:
            self.error = "Port Art-Net 6454 occupé : ferme MagicQ (ou tout autre logiciel Art-Net) puis relance."
            return
        self.running = True
        self.step, self.next_at = "poll1", now

    # -- reception ---------------------------------------------------------
    def on_packet(self, data, addr, now):
        if len(data) < 12 or data[:8] != b"Art-Net\x00":
            return
        op = struct.unpack("<H", data[8:10])[0]
        if op == OP_POLL_REPLY and len(data) >= 197:
            self._poll_reply(data, addr)
        elif op == OP_TOD_DATA and len(data) >= 28:
            uni = ((data[21] & 0x7F) << 8) | data[23]
            count = data[27]
            for i in range(count):
                uid = data[28 + 6 * i: 34 + 6 * i]
                if len(uid) == 6 and uid not in self.devices:
                    self.devices[uid] = {"uid": uid_text(uid), "ip": addr[0], "universe": uni,
                                         "manufacturer": "", "model": "", "label": "", "address": 0,
                                         "footprint": 0, "personality": 0, "personality_count": 0,
                                         "personality_name": "", "slots": None, "defaults": {},
                                         "layout": "", "layout_sure": False, "error": ""}
        elif op == OP_RDM and len(data) > 24:
            self._rdm_reply(data[24:], now)

    def _poll_reply(self, d, addr):
        ip = ".".join(str(x) for x in d[10:14])
        if ip == "0.0.0.0":
            ip = addr[0]
        node = self.nodes.setdefault(ip, {"ip": ip, "short_name": "", "long_name": "", "universes": [],
                                          "rdm": False, "style": 0, "report": "", "mac": ""})
        node["short_name"] = ascii_text(d[26:44])
        node["long_name"] = ascii_text(d[44:108])
        node["report"] = ascii_text(d[108:172])
        node["rdm"] = node["rdm"] or bool(d[23] & 0x02)
        node["style"] = d[200] if len(d) > 200 else 0
        if len(d) > 206:
            node["mac"] = ":".join("%02X" % x for x in d[201:207])
        net, sub = d[18] & 0x7F, d[19] & 0x0F
        for i in range(min(d[173], 4)):
            if d[174 + i] & 0x80:  # port de sortie
                uni = (net << 8) | (sub << 4) | (d[190 + i] & 0x0F)
                if uni not in node["universes"]:
                    node["universes"].append(uni)
        node["universes"].sort()

    def _rdm_reply(self, r, now):
        if r[0] == 0xCC:
            r = r[1:]
        if len(r) < 23 or r[0] != 0x01 or r[19] != 0x21:
            return
        req = self.inflight
        src, tn, rtype, pid, pdl = r[8:14], r[14], r[15], struct.unpack(">H", r[20:22])[0], r[22]
        if not req or src != req["uid"] or pid != req["pid"] or tn != req["tn"]:
            return
        self.inflight = None
        dev = self.devices.get(src)
        if dev is None:
            return
        if rtype != 0x00:  # NACK / ACK_TIMER / OVERFLOW : on fait sans
            if pid == PID_DEVICE_INFO:
                dev["error"] = "Le projecteur refuse la lecture RDM"
            return
        self._apply(dev, src, pid, r[23:23 + pdl])

    def _apply(self, dev, uid, pid, pd):
        if pid == PID_DEVICE_INFO and len(pd) >= 19:
            dev["footprint"] = struct.unpack(">H", pd[10:12])[0]
            dev["personality"], dev["personality_count"] = pd[12], pd[13]
            dev["address"] = struct.unpack(">H", pd[14:16])[0]
            follow = [(PID_MANUFACTURER_LABEL, b""), (PID_MODEL_DESCRIPTION, b""), (PID_DEVICE_LABEL, b"")]
            if dev["personality"]:
                follow.append((PID_PERSONALITY_DESCRIPTION, bytes([dev["personality"]])))
            if dev["footprint"]:
                follow += [(PID_SLOT_INFO, b""), (PID_DEFAULT_SLOT_VALUE, b"")]
            self.queue = [(uid, p, d) for p, d in follow] + self.queue
        elif pid == PID_MANUFACTURER_LABEL:
            dev["manufacturer"] = ascii_text(pd)
        elif pid == PID_MODEL_DESCRIPTION:
            dev["model"] = ascii_text(pd)
        elif pid == PID_DEVICE_LABEL:
            dev["label"] = ascii_text(pd)
        elif pid == PID_PERSONALITY_DESCRIPTION and len(pd) >= 3:
            dev["personality_name"] = ascii_text(pd[3:])
        elif pid == PID_SLOT_INFO:
            dev["slots"] = {struct.unpack(">H", pd[i:i + 2])[0]: (pd[i + 2], struct.unpack(">H", pd[i + 3:i + 5])[0])
                            for i in range(0, len(pd) - 4, 5)}
        elif pid == PID_DEFAULT_SLOT_VALUE:
            dev["defaults"] = {struct.unpack(">H", pd[i:i + 2])[0]: pd[i + 2] for i in range(0, len(pd) - 2, 3)}

    # -- deroulement (appele en boucle par le moteur) -----------------------
    def tick(self, now, send, target_ip):
        if not self.running:
            return
        if self.step in ("poll1", "poll2") and now >= self.next_at:
            self.phase = "Recherche des nodes Art-Net…"
            for ip in broadcast_targets(target_ip):
                send(art_header(OP_POLL) + b"\x00\x00", ip)
            self.step, self.next_at = ("poll2", now + 1.0) if self.step == "poll1" else ("tod", now + 2.0)
        elif self.step in ("tod", "tod2") and now >= self.next_at:
            if not self.nodes:
                return self._finish("Aucun node Art-Net n'a répondu. Vérifie le câble réseau, la carte choisie et que MagicQ est fermé.")
            self.phase = "Recherche RDM des projecteurs…"
            for node in self.nodes.values():
                for uni in node["universes"]:
                    net, adr = port_bytes(uni)
                    send(art_header(OP_TOD_REQUEST) + bytes(9) + net + b"\x00\x01" + adr, node["ip"])
            self.step, self.next_at = ("tod_wait", now + 2.5)
        elif self.step == "tod_wait" and now >= self.next_at:
            if not self.devices and not self.flushed:
                # Certains nodes ne font la decouverte RDM que sur demande : on la force une fois.
                self.flushed = True
                self.phase = "Relance de la découverte RDM sur les nodes…"
                for node in self.nodes.values():
                    for uni in node["universes"]:
                        net, adr = port_bytes(uni)
                        send(art_header(OP_TOD_CONTROL) + bytes(9) + net + b"\x01" + adr, node["ip"])
                self.step, self.next_at = "tod2", now + 6.0
            else:
                self.queue = [(uid, PID_DEVICE_INFO, b"") for uid in self.devices]
                self.step = "rdm"
        elif self.step == "rdm":
            req = self.inflight
            if req and now - req["sent"] > 0.8:
                self.inflight = None
                if req["tries"] < 2:
                    self.queue.insert(0, (req["uid"], req["pid"], req["pd"], req["tries"]))
                elif req["pid"] == PID_DEVICE_INFO:
                    self.devices[req["uid"]]["error"] = "Pas de réponse RDM"
            if self.inflight is None and self.queue:
                item = self.queue.pop(0)
                uid, pid, pd = item[:3]
                tries = item[3] + 1 if len(item) > 3 else 1
                dev = self.devices[uid]
                self.tn = (self.tn + 1) & 0xFF
                net, adr = port_bytes(dev["universe"])
                send(art_header(OP_RDM) + b"\x01\x00" + bytes(7) + net + b"\x00" + adr
                     + rdm_get(uid, self.src_uid, self.tn, pid, pd), dev["ip"])
                self.inflight = {"uid": uid, "pid": pid, "pd": pd, "tn": self.tn, "sent": now, "tries": tries}
                done = sum(1 for d in self.devices.values() if d["address"] or d["error"])
                self.phase = "Lecture des projecteurs (%d/%d)…" % (done, len(self.devices))
            elif self.inflight is None:
                self._finish("")

    def _finish(self, error):
        for dev in self.devices.values():
            dev["layout"], dev["layout_sure"] = self._layout(dev)
        self.running, self.error, self.step = False, error, None
        n = len(self.devices)
        self.phase = "Terminé : %d node(s), %d projecteur(s) RDM" % (len(self.nodes), n)
        if self.nodes and not n:
            self.phase += " — pas de RDM ici, saisie manuelle nécessaire"

    @staticmethod
    def _layout(dev):
        fp = dev["footprint"]
        if not fp:
            return "", False
        slots = dev["slots"]
        if not slots:
            return guess_layout(fp), False
        toks, used = [], set()
        for off in range(fp):
            kind, label = slots.get(off, (0xFF, 0))
            tok = SLOT_TOKENS.get(label) if kind == 0 else None
            if tok and tok not in used:
                used.add(tok)
                toks.append(tok)
            else:
                toks.append(str(dev["defaults"].get(off, 0)))
        return ",".join(toks), {"R", "G", "B"} <= used

    def snapshot(self):
        devs = []
        for d in self.devices.values():
            devs.append({k: v for k, v in d.items() if k not in ("slots", "defaults")})
        devs.sort(key=lambda d: (d["universe"], d["address"]))
        return {"running": self.running, "phase": self.phase, "error": self.error,
                "nodes": sorted(self.nodes.values(), key=lambda n: n["ip"]), "devices": devs}


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
        self.rx_ok = False       # True si on ecoute bien le port Art-Net (necessaire a la decouverte)
        self.discovery = Discovery()

    # ---- sortie Art-Net -------------------------------------------------
    def _socket(self):
        key = (self.config.get("bind_ip") or "",)
        if self.sock is None or self.sock_key != key:
            if self.sock:
                self.sock.close()
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SIO_UDP_CONNRESET"):  # Windows : evite les erreurs 10054 en reception
                s.ioctl(socket.SIO_UDP_CONNRESET, False)
            # Art-Net : on ecoute sur 6454 pour recevoir les reponses des nodes (ArtPollReply, RDM)
            try:
                s.bind((key[0], 6454))
                self.rx_ok = True
            except OSError:
                s.bind((key[0], 0))
                self.rx_ok = False
            s.setblocking(False)
            self.sock, self.sock_key = s, key
        return self.sock

    def _send_to(self, pkt, ip):
        try:
            self.sock.sendto(pkt, (ip, int(self.config.get("port", 6454))))
        except OSError:
            pass  # destination de broadcast injoignable sur ce PC : on ignore

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
        next_frame = 0.0
        while True:
            now = time.time()
            with self.lock:
                fps = max(1, min(44, int(self.config.get("fps", 30))))
                target = (self.config.get("target_ip") or "255.255.255.255",
                          int(self.config.get("port", 6454)))
                try:
                    sock = self._socket()
                except OSError as e:
                    sock = None
                    self.last_error = "Socket: %s" % e
                if sock:
                    self.discovery.tick(now, self._send_to, target[0])
                unis = self.build_universes() if now >= next_frame or self.wake.is_set() else None
            if sock is None:
                time.sleep(0.5)
                continue
            if unis is not None:
                self.wake.clear()
                seq = seq % 255 + 1
                try:
                    for uni, data in sorted(unis.items()):
                        sock.sendto(self.artdmx(uni, data, seq), target)
                        self.packets += 1
                    self.last_error = ""
                except OSError as e:
                    self.last_error = "Envoi vers %s : %s" % (target[0], e)
                next_frame = now + 1.0 / fps
            try:
                ready = select.select([sock], [], [], max(0.0, min(next_frame - time.time(), 0.01)))[0]
            except (OSError, ValueError):
                ready = []
            while ready:
                try:
                    data, addr = sock.recvfrom(2048)
                except OSError:
                    break
                if data[8:10] != b"\x00\x50":  # on ignore l'ArtDmx (y compris le notre)
                    with self.lock:
                        self.discovery.on_packet(data, addr, time.time())

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
                    "local_ips": LOCAL_IPS, "discovery": self.discovery.snapshot()}

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

    def start_discovery(self):
        with self.lock:
            if not self.rx_ok:
                self.sock_key = None  # MagicQ a peut-etre ete ferme depuis : on retente le port 6454
            try:
                self._socket()
            except OSError:
                pass
            self.discovery.start(time.time(), self.rx_ok)

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
            elif self.path == "/api/discover":
                ENGINE.start_discovery()
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
