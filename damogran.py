#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = []
# ///
"""Damogran - petite console web Art-Net pour spots RGB (dim + couleur).

Lance un serveur web local et envoie l'Art-Net directement (sans MagicQ).
Aucune dependance : Python 3.8+ standard uniquement.

    uv run damogran.py            -> http://localhost:8080 (ce PC seulement)
    uv run damogran.py --lan      -> accessible aussi depuis un telephone sur le meme reseau
    uv run damogran.py --port 9000
(ou « python damogran.py » avec n'importe quel Python 3.8+)
"""
import argparse
import os
import sys
import threading
import webbrowser
from http.server import ThreadingHTTPServer

# Le Python portable de Windows n'ajoute pas le dossier du script aux imports : on le fait ici.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import STATE_PATH, save_json  # noqa: E402
from app.engine import Engine  # noqa: E402
from app.web import Handler  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--lan", action="store_true", help="ecoute sur toutes les interfaces (telephone/tablette)")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    engine = Engine()
    threading.Thread(target=engine.run, daemon=True).start()
    threading.Thread(target=engine.saver, daemon=True).start()
    Handler.engine = engine

    srv = ThreadingHTTPServer(("0.0.0.0" if args.lan else "127.0.0.1", args.port), Handler)
    url = "http://localhost:%d" % args.port
    print("Damogran pret : %s" % url)
    if args.lan:
        for ip in engine.local_ips:
            print("  depuis un telephone : http://%s:%d" % (ip, args.port))
    print("Art-Net -> %s  (Ctrl+C pour quitter)" % engine.config["target_ip"])
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        save_json(STATE_PATH, engine.state)


if __name__ == "__main__":
    main()
