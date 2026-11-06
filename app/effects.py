"""Effets lumiere : calcules a chaque image, ils remplacent l'etat du plateau tant qu'ils tournent.
Memes formules que web/js/color.js (pour animer les apercus)."""
import math

from .colors import hs_to_rgb, white_values

EFFECTS = ("chase", "party", "applause")


def _noise(i, seg):
    x = math.sin(i * 12.9898 + seg * 78.233) * 43758.5453
    return x - math.floor(x)


def effect_values(name, i, n, ph, base, layout):
    """Valeurs du spot i (sur n) pour l'effet, a la phase ph (secondes x vitesse)."""
    if name == "chase":   # un spot apres l'autre, dans l'ordre, avec sa couleur
        p = (ph * 2.0) % n
        d = abs(i - p)
        d = min(d, n - d)
        out = dict(base)
        if not any(base.get(k) for k in ("r", "g", "b", "l", "w")):
            out.update(white_values(layout, 3200))
        out["dim"] = 255 * max(0.0, 1 - d / 1.2)
        return out
    if name == "party":   # arc-en-ciel qui tourne sur les spots
        r, g, b = hs_to_rgb((ph * 36 + i * 360.0 / max(n, 1)) % 360, 255)
        return {"dim": 255 * (0.8 + 0.2 * math.sin(ph * 4 + i)), "r": r, "g": g, "b": b, "l": 0, "w": 0, "a": 0, "u": 0}
    out = white_values(layout, 3200)   # applaudissements : blanc chaud qui scintille
    out["dim"] = 255 * (0.55 + 0.45 * _noise(i, math.floor(ph * 8)))
    return out
