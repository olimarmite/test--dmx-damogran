"""Decouverte : ArtPoll (nodes Art-Net) puis RDM via Art-Net (adresse et canaux des projecteurs)."""
import random
import struct

from .artnet import (OP_POLL, OP_POLL_REPLY, OP_RDM, OP_TOD_CONTROL, OP_TOD_DATA, OP_TOD_REQUEST,
                     PID_DEFAULT_SLOT_VALUE, PID_DEVICE_INFO, PID_DEVICE_LABEL, PID_MANUFACTURER_LABEL,
                     PID_MODEL_DESCRIPTION, PID_PERSONALITY_DESCRIPTION, PID_SLOT_INFO,
                     art_header, broadcast_targets, port_bytes, rdm_get)

# Identifiants de slot RDM (E1.20 table C-2) -> lettre de canal Damogran
SLOT_TOKENS = {0x0001: "D", 0x0002: "D", 0x0205: "R", 0x0206: "G", 0x0207: "B",
               0x0211: "A", 0x0212: "W", 0x0213: "W", 0x0214: "W"}


def ascii_text(b):
    return b.split(b"\x00")[0].decode("ascii", "replace").strip()


def uid_text(uid):
    return "%04X:%08X" % struct.unpack(">HI", uid)


def guess_layout(footprint):
    if footprint <= 3:
        return ",".join("RGB"[:max(footprint, 1)])
    return ",".join(["D", "R", "G", "B"] + ["0"] * (footprint - 4))


class Discovery:
    def __init__(self, own_ips):
        self.own_ips = own_ips
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
            for ip in broadcast_targets(target_ip, self.own_ips):
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
