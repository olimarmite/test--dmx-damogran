"""Fichiers de reglages (config.json) et d'etat (state.json), valeurs par defaut, petits utilitaires."""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config.json")
STATE_PATH = os.path.join(ROOT, "state.json")
WEB_DIR = os.path.join(ROOT, "web")

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


def default_input(fixtures):
    """Correspondance proposee pour la Mini Connect : faders 1-8 = spots, 9 = blanc, 10 = master."""
    m = {str(i + 1): "dim:" + fx["id"] for i, fx in enumerate(fixtures[:8])}
    m["9"], m["10"] = "white:all", "master"
    return {"enabled": True, "universe": 1, "map": m}


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


def clean_remote(r):
    """Telecommande telephone : identifiant du PC sur le relais PeerJS, cle du QR code, adresse de la page."""
    if not isinstance(r, dict):
        return None
    tok = lambda v: re.sub(r"[^A-Za-z0-9_-]", "", str(v or ""))[:64]
    page = str(r.get("page") or "").strip()[:300]
    if not re.match(r"^https?://[^\s\"'<>]+$", page):
        page = ""
    return {"on": bool(r.get("on")), "id": tok(r.get("id")), "key": tok(r.get("key")), "page": page}


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
