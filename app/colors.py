"""Couleurs des LED : blancs calcules (avec le lime), apercu a l'ecran, teinte.
Memes formules que web/js/color.js."""
import functools
import math

from .config import parse_layout

# Modele colorimetrique des LED : chromaticite CIE 1931 (x, y) et flux relatif a pleine puissance.
# Valeurs typiques de LED de theatre (rouge 625 nm, vert 525 nm, bleu 460 nm, lime a phosphore) :
# ce ne sont pas des mesures des ColorSource, la correction vert / rose sert a ajuster a l'oeil.
EMITTERS = {"r": (0.700, 0.299, 0.28), "g": (0.170, 0.700, 0.60), "b": (0.145, 0.045, 0.07),
            "l": (0.410, 0.550, 1.00), "w": (0.330, 0.340, 1.00), "a": (0.570, 0.425, 0.45),
            "u": (0.170, 0.010, 0.01)}


def _xyz(x, y, Y):
    return (x / y * Y, Y, (1 - x - y) / y * Y)


def _planck_xy(T):
    """Point du corps noir a T kelvins (approximation de Kim et al., 2002)."""
    if T <= 4000:
        x = -0.2661239e9 / T ** 3 - 0.2343589e6 / T ** 2 + 0.8776956e3 / T + 0.179910
    else:
        x = -3.0258469e9 / T ** 3 + 2.1070379e6 / T ** 2 + 0.2226347e3 / T + 0.240390
    if T <= 2222:
        y = -1.1063814 * x ** 3 - 1.34811020 * x ** 2 + 2.18555832 * x - 0.20219683
    elif T <= 4000:
        y = -0.9549476 * x ** 3 - 1.37418593 * x ** 2 + 2.09137015 * x - 0.16748867
    else:
        y = 3.0817580 * x ** 3 - 5.87338670 * x ** 2 + 3.75112997 * x - 0.37001483
    return x, y


def _white_xy(T, duv):
    """Blanc vise : T kelvins, decale de duv perpendiculairement au corps noir (+ vert, - rose)."""
    def uv(x, y):
        d = -2 * x + 12 * y + 3
        return 4 * x / d, 6 * y / d
    u0, v0 = uv(*_planck_xy(T))
    u1, v1 = uv(*_planck_xy(T + 10))
    n = math.hypot(u1 - u0, v1 - v0)
    nu, nv = -(v1 - v0) / n, (u1 - u0) / n
    if nv < 0:
        nu, nv = -nu, -nv
    u, v = u0 + duv * nu, v0 + duv * nv
    d = 2 * u - 8 * v + 4
    return 3 * u / d, 2 * v / d


def _det3(m):
    return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))


def _solve3(m, b):
    d = _det3(m)
    out = []
    for i in range(3):
        mi = [row[:] for row in m]
        for r in range(3):
            mi[r][i] = b[r]
        out.append(_det3(mi) / d)
    return out


@functools.lru_cache(maxsize=512)
def white_mix(chans, T, duv):
    """Melange des LED (0..1, la plus forte a 1) qui donne le blanc vise avec le plus de lumiere.
    chans : canaux de couleur du projecteur, ex. "rgbl". Avec une LED en plus du rouge, vert, bleu
    (lime, blanc ou ambre), on cherche sa part qui permet le melange le plus lumineux."""
    base = [c for c in "rgb" if c in chans]
    extra = next((c for c in "lwa" if c in chans), None)
    if len(base) < 3:
        return {}
    x, y = _white_xy(T, duv)
    t = _xyz(x, y, 1.0)
    em = {c: _xyz(*EMITTERS[c]) for c in base + ([extra] if extra else [])}
    m = [[em[c][k] for c in base] for k in range(3)]
    u = _solve3(m, t)
    w = _solve3(m, em[extra]) if extra else [0.0, 0.0, 0.0]
    best = None
    steps = 200 if extra else 0
    for i in range(steps + 1):
        d = i / steps if steps else 0.0
        lo, hi, ok = 0.0, float("inf"), True
        for ui, wi in zip(u, w):          # chaque LED de base : 0 <= s*ui - d*wi <= 1
            if abs(ui) < 1e-12:
                ok = ok and 0 <= -d * wi <= 1
                continue
            a, b = d * wi / ui, (1 + d * wi) / ui
            lo, hi = (max(lo, a), min(hi, b)) if ui > 0 else (max(lo, b), min(hi, a))
        if ok and lo <= hi and (best is None or hi > best[0]):
            best = (hi, d, [hi * ui - d * wi for ui, wi in zip(u, w)])
    if best is None:
        return {}
    s, d, rgb = best
    out = dict(zip(base, rgb))
    if extra:
        out[extra] = d
    top = max(out.values()) or 1.0
    return {c: max(0.0, v / top) for c, v in out.items()}


def display_rgb(st):
    """Couleur a montrer a l'ecran pour des valeurs de LED (0..255) : somme des LED en XYZ, puis sRGB."""
    X = Y = Z = 0.0
    for c, e in EMITTERS.items():
        v = float(st.get(c, 0) or 0) / 255.0
        if v > 0:
            ex = _xyz(*e)
            X, Y, Z = X + v * ex[0], Y + v * ex[1], Z + v * ex[2]
    if Y <= 0:
        return [0, 0, 0]
    lin = [3.2406 * X - 1.5372 * Y - 0.4986 * Z, -0.9689 * X + 1.8758 * Y + 0.0415 * Z, 0.0557 * X - 0.2040 * Y + 1.0570 * Z]
    lin = [max(0.0, v) for v in lin]
    top = max(lin) or 1.0
    gam = lambda v: 12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055
    return [int(round(255 * gam(v / top))) for v in lin]


def hs_to_rgb(h, s):
    s /= 255.0

    def f(n):
        k = (n + h / 60.0) % 6
        return int(round(255 * (1 - s * max(0, min(k, 4 - k, 1)))))
    return [f(5), f(3), f(1)]


def rgb_to_hs(r, g, b):
    mx, mn = max(r, g, b), min(r, g, b)
    d = mx - mn
    h = 0.0
    if d:
        if mx == r:
            h = 60 * (((g - b) / d) % 6)
        elif mx == g:
            h = 60 * ((b - r) / d + 2)
        else:
            h = 60 * ((r - g) / d + 4)
    return int(round(h % 360)), int(round(255 * d / mx)) if mx else 0


def white_values(layout, k, tint=0):
    """Valeurs des LED pour un blanc a k kelvins sur ce projecteur. tint : -100 (plus vert) .. +100 (plus rose)."""
    toks = parse_layout(layout)
    chans = "".join(c.lower() for c in "RGBLWA" if c in toks)
    k = int(round(max(2700, min(6500, k)) / 50.0)) * 50
    tint = int(max(-100, min(100, tint)))
    mix = white_mix(chans, k, -tint * 0.00012)
    out = {c: int(round(mix.get(c, 0) * 255)) for c in "rgbwla"}
    out["h"], out["s"] = rgb_to_hs(*display_rgb(out))
    out["k"], out["tint"] = k, tint
    return out
