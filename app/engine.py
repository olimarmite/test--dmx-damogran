"""Moteur : etat du plateau, sortie Art-Net, entree console / MIDI, ambiances et fondus."""
import json
import select
import socket
import struct
import threading
import time

from .artnet import OP_DMX, artdmx, local_ips
from .colors import hs_to_rgb, white_values
from .config import CONFIG_PATH, DEFAULT_CONFIG, STATE_PATH, clean_remote, default_input, load_json, parse_layout, save_json
from .discovery import Discovery
from .effects import EFFECTS, effect_values

LED_TOKENS = ("R", "G", "B", "W", "A", "U", "L")   # lettres de canal : rouge, vert, bleu, blanc, ambre, UV, lime
FADE_KEYS = ("dim", "r", "g", "b", "w", "a", "u", "l")   # valeurs fondues lors du rappel d'une memoire
SCENE_KEYS = FADE_KEYS + ("h", "s", "k", "tint")   # k : temperature du blanc choisi (affichage)


class Engine:
    def __init__(self):
        self.lock = threading.Lock()
        self.config = load_json(CONFIG_PATH, None) or json.loads(json.dumps(DEFAULT_CONFIG))
        self.config.setdefault("input", default_input(self.config["fixtures"]))
        self.config.setdefault("grid", {"cols": 12, "rows": 7})
        self.state = load_json(STATE_PATH, None) or {}
        for k, v in (("master", 255), ("blackout", False), ("fixtures", {}), ("scenes", []),
                     ("fade", 2.0), ("active_scene", None), ("effect", None)):
            self.state.setdefault(k, v)
        self.state.pop("speed", None)   # ancienne cle, plus utilisee
        self.fade = None         # fondu en cours : {"from", "to", "t0", "dur"}
        self.raw = None          # {"universe", "address", "value"} testeur de canal
        self.identify = {}       # id -> timestamp de fin
        self.sock = None
        self.sock_key = None
        self.last_error = ""
        self.packets = 0
        self.dirty = False
        self.wake = threading.Event()
        self.rx_ok = False       # True si on ecoute bien le port Art-Net (necessaire a la decouverte)
        self.local_ips = local_ips()
        self.discovery = Discovery(self.local_ips)
        self.in_values = bytearray(512)   # derniere valeur recue de la console, par canal
        self.in_seen = 0.0                # heure du dernier paquet console
        self.in_source = ""
        self.xbase = {}                   # transitions manuelles : etat de depart par memoire
        self.midi_vals = {}               # derniere valeur recue par commande MIDI ("cc7", "n36")
        self.effect_phase = 0.0
        self.fx_speed = 1.0               # vitesse donnee par un fader console, pour le prochain effet lance
        self.effect_clock = time.time()

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
        eff = self.state.get("effect")
        if eff:   # la phase avance avec la vitesse : changer de vitesse ne fait pas sauter l'effet
            self.effect_phase += (now - self.effect_clock) * float(eff.get("speed", 1.0))
        self.effect_clock = now
        n = len(self.config["fixtures"])
        for idx, fx in enumerate(self.config["fixtures"]):
            uni = int(fx.get("universe", 0))
            buf = unis.setdefault(uni, bytearray(512))
            st = self.state["fixtures"].get(fx["id"], {})
            if eff:
                st = effect_values(eff["name"], idx, n, self.effect_phase, st, fx.get("layout", ""))
            layout = parse_layout(fx.get("layout", "D,R,G,B"))
            has_dim = "D" in layout
            dim = st.get("dim", 0) / 255.0 * master
            if blackout:
                dim = 0.0
            vals = {"D": dim * 255}
            col_scale = 1.0 if has_dim else dim
            for t in LED_TOKENS:
                vals[t] = st.get(t.lower(), 0) * col_scale
            ident = self.identify.get(fx["id"], 0)
            if ident > now:
                on = int(now * 6) % 2 == 0
                vals = {t: (255 if on else 0) for t in ("D",) + LED_TOKENS}
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
                unis = None
                if now >= next_frame or self.wake.is_set():
                    self._step_fade(now)
                    unis = self.build_universes()
            if sock is None:
                time.sleep(0.5)
                continue
            if unis is not None:
                self.wake.clear()
                seq = seq % 255 + 1
                try:
                    for uni, data in sorted(unis.items()):
                        sock.sendto(artdmx(uni, data, seq), target)
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
                with self.lock:
                    if data[8:10] == struct.pack("<H", OP_DMX):   # ArtDmx : peut-etre la console
                        self._console_packet(data, addr)
                    else:
                        self.discovery.on_packet(data, addr, time.time())

    # ---- entree console (Art-Net venant de MagicQ / Mini Connect) --------
    def _output_universes(self):
        return {int(fx.get("universe", 0)) for fx in self.config["fixtures"]}

    def _console_packet(self, data, addr):
        inp = self.config.get("input") or {}
        if len(data) < 18 or not inp.get("enabled"):
            return
        uni = data[14] | ((data[15] & 0x7F) << 8)
        # l'univers de la console doit etre different de ceux des projecteurs (sinon c'est notre propre sortie)
        if uni != int(inp.get("universe", 1)) or uni in self._output_universes():
            return
        n = min(512, (data[16] << 8) | data[17], len(data) - 18)
        dmx = data[18:18 + n]
        now = time.time()
        fresh = now - self.in_seen > 3.0   # console (re)connectee : on prend les positions sans rien appliquer
        if not fresh:
            for ch_s, target in (inp.get("map") or {}).items():
                ch = int(ch_s) - 1
                if 0 <= ch < n and dmx[ch] != self.in_values[ch]:
                    self._apply_target(str(target), dmx[ch], self.in_values[ch])
        self.in_values[:n] = dmx
        self.in_seen, self.in_source = now, addr[0]

    def _apply_target(self, target, v, old):
        kind, _, arg = target.partition(":")
        fx_ids = [fx["id"] for fx in self.config["fixtures"]]
        targets = fx_ids if arg == "all" else [arg] if arg in fx_ids else []
        fixtures = self.state["fixtures"]
        if kind == "master":
            self.state["master"] = v
        elif kind == "blackout":
            if (v >= 128) != (old >= 128):
                self.state["blackout"] = v >= 128
        elif kind == "scene":
            if v >= 128 > old:   # le fader passe la moitie en montant : GO
                sc = next((x for x in self.state["scenes"] if x["id"] == arg), None)
                if sc:
                    self.state["active_scene"] = sc["id"]
                    self._start_fade(sc.get("fixtures") or {}, self.state["fade"])
        elif kind == "xfade":
            self._xfade(arg, v, old)
        elif kind == "fx":   # au-dela de la moitie : l'effet tourne ; en dessous : il s'arrete
            if v >= 128 > old:
                self._set_effect({"name": arg, "speed": self.fx_speed})
            elif old >= 128 > v and (self.state.get("effect") or {}).get("name") == arg:
                self._set_effect(None)
        elif kind == "fxspeed":
            self.fx_speed = round(0.25 + v * 2.75 / 255, 2)
            if self.state.get("effect"):
                self.state["effect"]["speed"] = self.fx_speed
        elif kind in ("dim", "white", "hue") and targets:
            self.fade = None
            self.state["active_scene"] = None
            for fid in targets:
                cur = fixtures.setdefault(fid, {})
                if kind == "dim":
                    cur["dim"] = v
                elif kind == "white":
                    fx = next(f for f in self.config["fixtures"] if f["id"] == fid)
                    cur.update(white_values(fx.get("layout", ""), 2700 + v * 3800 / 255.0))
                else:
                    h, s = int(round(v * 359 / 255.0)), cur.get("s") or 255
                    r, g, b = hs_to_rgb(h, s)
                    cur.update({"h": h, "s": s, "r": r, "g": g, "b": b, "w": 0, "l": 0, "k": 0})
        self.dirty = True
        self.wake.set()

    def _set_effect(self, eff):
        if not eff or eff.get("name") not in EFFECTS:
            self.state["effect"] = None
            return
        cur = self.state.get("effect") or {}
        if cur.get("name") != eff["name"]:
            self.effect_phase = 0.0
        self.state["effect"] = {"name": eff["name"], "speed": max(0.25, min(3.0, float(eff.get("speed", 1.0))))}

    def _xfade(self, scene_id, v, old):
        """Fader de transition : 0 = etat de depart (pris quand le fader quitte 0), 100 % = la memoire."""
        sc = next((x for x in self.state["scenes"] if x["id"] == scene_id), None)
        if not sc:
            return
        self.fade = None
        self.state["effect"] = None
        target = sc.get("fixtures") or {}
        fixtures = self.state["fixtures"]
        base = self.xbase.get(scene_id)
        if base is None:
            base = {fid: {k: float(fixtures.get(fid, {}).get(k, 0)) for k in SCENE_KEYS} for fid in target}
            self.xbase[scene_id] = base
        f = v / 255.0
        for fid, to in target.items():
            cur, b = fixtures.setdefault(fid, {}), base.get(fid, {})
            for key in FADE_KEYS:
                cur[key] = round(b.get(key, 0) + (float(to.get(key, 0)) - b.get(key, 0)) * f, 1)
            src = to if f >= 0.5 else b   # teinte, saturation, temperature : affichage seulement
            for key in ("h", "s", "k"):
                cur[key] = src.get(key, 0)
        self.state["active_scene"] = sc["id"] if v == 255 else None
        if v == 0:
            self.xbase.pop(scene_id, None)   # revenu au depart : la prochaine montee repart de l'etat du moment

    def set_input(self, body):
        with self.lock:
            inp = self.config.get("input") or {}
            if "enabled" in body:
                inp["enabled"] = bool(body["enabled"])
            if "universe" in body:
                inp["universe"] = max(0, min(32767, int(body["universe"])))
            if "map" in body:
                inp["map"] = {str(int(k)): str(v) for k, v in (body["map"] or {}).items()
                              if 1 <= int(k) <= 512 and v}
            if "midi_map" in body:
                inp["midi_map"] = {str(k)[:8]: str(v) for k, v in (body["midi_map"] or {}).items() if v}
            self.config["input"] = inp
            save_json(CONFIG_PATH, self.config)

    def set_layout(self, body):
        """Plan de scene : taille de la grille et case de chaque spot."""
        with self.lock:
            g = body.get("grid") or self.config.get("grid") or {}
            self.config["grid"] = {"cols": max(4, min(24, int(g.get("cols", 12)))), "rows": max(3, min(14, int(g.get("rows", 7))))}
            pos = body.get("positions") or {}
            for fx in self.config["fixtures"]:
                if fx["id"] in pos:
                    x, y = pos[fx["id"]]
                    fx["x"] = max(0, min(self.config["grid"]["cols"] - 1, int(x)))
                    fx["y"] = max(0, min(self.config["grid"]["rows"] - 1, int(y)))
            save_json(CONFIG_PATH, self.config)

    # ---- MIDI : le navigateur lit le controleur USB et transmet chaque mouvement ----
    def midi_input(self, body):
        key = str(body.get("key", ""))[:8]          # "cc7" (fader, bouton CC) ou "n36" (note / pad)
        v = int(round(max(0, min(127, int(body.get("value", 0)))) * 255 / 127.0))
        with self.lock:
            old = self.midi_vals.get(key, 0)
            self.midi_vals[key] = v
            target = ((self.config.get("input") or {}).get("midi_map") or {}).get(key)
            if target and v != old:
                self._apply_target(str(target), v, old)

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
                    "local_ips": self.local_ips, "discovery": self.discovery.snapshot(),
                    "fading": self.fade is not None, "effect_phase": round(self.effect_phase, 3),
                    "input": {"values": list(self.in_values[:24]), "source": self.in_source,
                              "seen": round(time.time() - self.in_seen, 1) if self.in_seen else None,
                              "conflict": int((self.config.get("input") or {}).get("universe", 1)) in self._output_universes()}}

    def patch_state(self, body):
        with self.lock:
            if body.get("fixtures"):
                # une action manuelle prend la main sur le fondu en cours
                self.fade = None
                self.state["active_scene"] = None
            for fid, vals in (body.get("fixtures") or {}).items():
                cur = self.state["fixtures"].setdefault(fid, {})
                for k, v in vals.items():
                    if isinstance(v, (int, float)):
                        lo = -100 if k == "tint" else 0   # tint : correction vert (-) / rose (+)
                        cur[k] = max(lo, min({"h": 360, "k": 20000, "tint": 100}.get(k, 255), v))
            if "master" in body:
                self.state["master"] = max(0, min(255, int(body["master"])))
            if "blackout" in body:
                self.state["blackout"] = bool(body["blackout"])
            if "effect" in body:
                self._set_effect(body["effect"])
            if "raw" in body:
                self.raw = body["raw"] or None
            for fid in body.get("identify") or []:
                self.identify[fid] = time.time() + 2.5
            self.dirty = True
        self.wake.set()

    # ---- memoires -------------------------------------------------------
    def _start_fade(self, target, dur):
        self.state["effect"] = None   # rappeler une memoire arrete l'effet en cours
        fx = self.state["fixtures"]
        self.fade = {
            "from": {fid: {k: float(fx.get(fid, {}).get(k, 0)) for k in FADE_KEYS} for fid in target},
            "to": {fid: {k: float(v.get(k, 0)) for k in FADE_KEYS} for fid, v in target.items()},
            "t0": time.time(), "dur": dur,
        }
        for fid, v in target.items():   # teinte/saturation : uniquement pour l'affichage, pas de fondu
            cur = fx.setdefault(fid, {})
            cur["h"], cur["s"] = v.get("h", 0), v.get("s", 0)
        self._step_fade(time.time())

    def _step_fade(self, now):
        f = self.fade
        if not f:
            return
        k = 1.0 if f["dur"] <= 0 else min(1.0, (now - f["t0"]) / f["dur"])
        for fid, to in f["to"].items():
            cur = self.state["fixtures"].setdefault(fid, {})
            frm = f["from"][fid]
            for key in FADE_KEYS:
                cur[key] = round(frm[key] + (to[key] - frm[key]) * k, 1)
        if k >= 1.0:
            self.fade = None
            self.dirty = True

    def scene_action(self, body):
        act = body.get("action")
        with self.lock:
            scenes = self.state["scenes"]
            sc = next((x for x in scenes if x["id"] == body.get("id")), None)
            name = str(body.get("name") or "").strip()[:30]
            if act == "save":
                if sc is None:
                    sc = {"id": "s%d" % int(time.time() * 1000), "name": name or "Mémoire %d" % (len(scenes) + 1)}
                    scenes.append(sc)
                elif name:
                    sc["name"] = name
                sc["fixtures"] = {fid: {k: v for k, v in vals.items() if k in SCENE_KEYS}
                                  for fid, vals in self.state["fixtures"].items()}
                self.state["active_scene"] = sc["id"]
            elif act == "rename" and sc and name:
                sc["name"] = name
            elif act == "delete" and sc:
                scenes.remove(sc)
                if self.state["active_scene"] == sc["id"]:
                    self.state["active_scene"] = None
            elif act == "recall" and sc:
                fade = float(body.get("fade", self.state["fade"]))
                self.state["active_scene"] = sc["id"]
                self._start_fade(sc.get("fixtures") or {}, max(0.0, min(60.0, fade)))
            elif act == "go" and scenes:   # memoire suivante, avec le fondu choisi
                ids = [x["id"] for x in scenes]
                cur = self.state.get("active_scene") or body.get("after")   # apres un reglage a la main : la derniere rappelee
                sc = scenes[(ids.index(cur) + 1) % len(scenes)] if cur in ids else scenes[0]
                self.state["active_scene"] = sc["id"]
                self._start_fade(sc.get("fixtures") or {}, self.state["fade"])
            elif act == "fade":
                self.state["fade"] = max(0.0, min(60.0, float(body.get("fade", 0))))
            else:
                raise ValueError("Mémoire introuvable ou action inconnue")
            self.dirty = True
        self.wake.set()

    def start_discovery(self, _body=None):
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
            if isinstance(fx.get("x"), int) and isinstance(fx.get("y"), int):   # place sur le plan
                fixtures[-1]["x"], fixtures[-1]["y"] = fx["x"], fx["y"]
        with self.lock:
            self.config = {
                "target_ip": str(cfg.get("target_ip") or "255.255.255.255").strip(),
                "bind_ip": str(cfg.get("bind_ip") or "").strip(),
                "port": int(cfg.get("port") or 6454),
                "fps": int(cfg.get("fps") or 30),
                "fixtures": fixtures,
                "input": self.config.get("input") or default_input(fixtures),
                "grid": self.config.get("grid") or {"cols": 12, "rows": 7},
                "remote": clean_remote(cfg["remote"]) if "remote" in cfg else self.config.get("remote"),
            }
            self.sock_key = None
            save_json(CONFIG_PATH, self.config)
        self.wake.set()
