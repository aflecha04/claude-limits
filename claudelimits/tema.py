# -*- coding: utf-8 -*-
"""Colores, acentos y escala del widget.

Los valores activos son variables de este modulo que apply_theme,
apply_accent y apply_scale reescriben. El resto del codigo los lee como
T.MENU_BG, T.W... (import tema as T) para ver siempre el valor vigente.
"""

try:
    from PIL import Image, ImageChops, ImageDraw, ImageTk
    HAVE_PIL = True
except Exception:
    Image = ImageChops = ImageDraw = ImageTk = None
    HAVE_PIL = False

# ─── Temas ──────────────────────────────────────────────────────────────
THEMES = {
    # Acento coral de Claude. Los valores salen de medir, no de tantear:
    # contraste WCAG para texto e iconos, y diferencia de luminosidad
    # percibida L* para superficies (WCAG comprime los tonos oscuros y
    # da 1,2:1 a dos grises que a la vista se distinguen de sobra).
    'dark': dict(
        PANEL_BG='#20242d', TILE_BD='#3a4050',
        ACCENT='#ff9166',
        TEXT_ON_FILL='#ffffff',
        MENU_BG='#242832', MENU_BD='#242832', MENU_FG='#f5f6f8',
        MENU_MUTED='#a3aab8', MENU_HOVER='#30353f', MENU_ACCENT='#ff9166',
        MENU_SEP='#1e222a',
        TINT='#272b36', CARD_BD='#272b36',
        INK='#f5f6f8', LABEL='#a3aab8', SUBTLE='#a3aab8',
        TRACK='#14171e', TRACK_SH='#0d1016', TIME='#cbd0db', BTN='#a3aab8', BTN_HOV='#ffffff', CLOSE_HOV='#ff6b7d',
        BAR_START='#e2683f', BAR_END='#b8492a',
        ROJO='#e5484d',
        ALPHA=1.0,
    ),
    'light': dict(
        PANEL_BG='#eef1f7', TILE_BD='#dde3ec',
        ACCENT='#c2542f',
        TEXT_ON_FILL='#ffffff',
        MENU_BG='#fbfbfc', MENU_BD='#e2e8f0', MENU_FG='#1f2733',
        MENU_MUTED='#5b6b82', MENU_HOVER='#eceef2', MENU_ACCENT='#c2542f',
        MENU_SEP='#eef1f6',
        TINT='#f9fafb', CARD_BD='#dde3ec',
        INK='#1f2733', LABEL='#5b6b82', SUBTLE='#5b6b82',
        TRACK='#dbe3ef', TRACK_SH='#c3cddd', TIME='#3f4a5c', BTN='#5b6b82', BTN_HOV='#0f172a', CLOSE_HOV='#d1344b',
        BAR_START='#c2542f', BAR_END='#96391d',
        ROJO='#d1344b',
        ALPHA=1.0,
    ),
}

# valores activos (se rellenan con apply_theme)
TINT = CARD_BD = HILITE = INK = LABEL = SUBTLE = TRACK = TRACK_SH = ''
TIME = BTN = BTN_HOV = CLOSE_HOV = BAR_START = BAR_END = ''
MENU_BG = MENU_BD = MENU_FG = MENU_MUTED = MENU_HOVER = ''
MENU_ACCENT = MENU_SEP = ''
SH_DARK = SH_LIGHT = ACCENT = TEXT_ON_FILL = TEXT_ON_ACCENT = ROJO = ''
PANEL_BG = TILE_BD = ''
ALPHA = 0.93
THEME = 'dark'


def apply_theme(name, acento=None):
    global THEME
    THEME = name if name in THEMES else 'dark'
    globals().update(THEMES[THEME])
    try:
        apply_accent(acento or ACCENT_NAME)
    except NameError:
        pass                      # en el arranque aun no existe la tabla


apply_theme('dark')


# ─── Color de acento ────────────────────────────────────────────────────
# El acento va aparte del tema: cada color trae su version para fondo
# oscuro y para fondo claro, porque el mismo tono no vale para los dos.
# Cada pareja (inicio, fin) esta elegida para que el numero en blanco se
# lea sobre el relleno y el final de la barra siga destacando del carril.
ACCENTS = {
    'coral':   ('Coral',   ('#e2683f', '#b8492a', '#ff9166', '#ffffff'),
                           ('#c2542f', '#96391d', '#c2542f', '#ffffff')),
    'naranja': ('Naranja', ('#f08a2f', '#c2610f', '#ffab55', '#ffffff'),
                           ('#c26a10', '#8f4a06', '#c26a10', '#ffffff')),
    'azul':    ('Azul',    ('#4b9dff', '#1f5fd0', '#7cb8ff', '#ffffff'),
                           ('#2f6fd0', '#1b4795', '#2f6fd0', '#ffffff')),
    'verde':   ('Verde',   ('#34c98a', '#0f8055', '#5fe0a6', '#ffffff'),
                           ('#0c7a51', '#0a5f40', '#0c7a51', '#ffffff')),
    'violeta': ('Violeta', ('#a78bfa', '#7a4ae2', '#c4b0ff', '#ffffff'),
                           ('#6d3fd6', '#4a2596', '#6d3fd6', '#ffffff')),
    'blanco':  ('Blanco',  ('#e8ecf4', '#aab2c2', '#e8ecf4', '#14171e'),
                           ('#5b6b82', '#33415a', '#33415a', '#ffffff')),
}
ACCENT_NAME = 'coral'


def apply_accent(nombre):
    """Aplica el color elegido encima del tema activo."""
    global ACCENT_NAME, BAR_START, BAR_END, ACCENT, MENU_ACCENT, TEXT_ON_FILL
    global TEXT_ON_ACCENT
    ACCENT_NAME = nombre if nombre in ACCENTS else 'coral'
    _, oscuro, claro = ACCENTS[ACCENT_NAME]
    ini, fin, suave, sobre = oscuro if THEME == 'dark' else claro
    # Relleno liso, de un solo color: el degradado oscurecia el final de la
    # barra y le quitaba limpieza (mas aun en el tema claro).
    BAR_START = BAR_END = ini
    ACCENT = MENU_ACCENT = suave
    # El texto que va encima de un color (la cifra sobre el relleno, el de un
    # boton) se elige por contraste: blanco o casi negro, el que mejor se
    # lea. Antes era siempre blanco y con el verde, el naranja o el azul en
    # tema oscuro apenas se leia (contraste 2:1; lo minimo es 4,5:1).
    TEXT_ON_FILL = texto_sobre(ini)
    TEXT_ON_ACCENT = texto_sobre(suave)


def texto_sobre(color):
    """Blanco o casi negro: el que mas contraste tenga sobre 'color'."""
    try:
        return ('#ffffff' if contraste(color, '#ffffff') >= contraste(color, '#14171e')
                else '#14171e')
    except Exception:
        return '#ffffff'


# ─── Color personalizado ────────────────────────────────────────────────
# Un color propio a partir de su codigo (#rrggbb). Sus versiones para fondo
# oscuro y claro se calculan solas, con el mismo criterio de contraste que
# los de fabrica: la cifra en blanco o en negro segun se lea mejor.
def normalizar_hex(texto):
    """'#1E90FF', '1e90ff' o '#19f' -> '#1e90ff'; None si no es un color."""
    t = (texto or '').strip().lstrip('#').lower()
    if len(t) == 3:
        t = ''.join(c * 2 for c in t)
    if len(t) != 6 or any(c not in '0123456789abcdef' for c in t):
        return None
    return '#' + t


def _luminancia(c):
    def lin(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = _hex(c)
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contraste(a, b):
    la, lb = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _sobre(c):
    return '#ffffff' if contraste(c, '#ffffff') >= contraste(c, '#14171e') else '#14171e'


def _destaca(c, fondos, hacia, minimo=3.0, cifra=False):
    """Aclara u oscurece 'c' hasta que destaque sobre todos los 'fondos' (y,
    con cifra=True, hasta que la cifra encima se lea a 4,5:1)."""
    for _ in range(30):
        ok = all(contraste(c, f) >= minimo for f in fondos)
        if ok and (not cifra or contraste(c, texto_sobre(c)) >= 4.5):
            break
        c = _mix(c, hacia, 0.08)
    return c


def set_color_propio(hexa):
    """Anade (o cambia) el color 'propio' en la lista de colores.

    Se respeta el color elegido, pero si no se viera bien (un casi negro en
    el tema oscuro, un amarillo palido en el claro) se aclara u oscurece lo
    justo para que la barra destaque y la cifra se lea.
    """
    c = normalizar_hex(hexa)
    if not c:
        ACCENTS.pop('propio', None)
        return None
    # tema oscuro: que destaque sobre el carril y la tarjeta oscuros
    osc = _destaca(c, (THEMES['dark']['TRACK'], THEMES['dark']['TINT']),
                   '#ffffff', cifra=True)
    osc_menu = _destaca(osc, (THEMES['dark']['MENU_BG'],), '#ffffff', 4.5)
    oscuro = (osc, osc, osc_menu, texto_sobre(osc))
    # tema claro: que destaque sobre el carril y el fondo claros
    cla = _destaca(c, (THEMES['light']['TRACK'], THEMES['light']['TINT']),
                   '#000000', cifra=True)
    claro = (cla, cla, cla, texto_sobre(cla))
    ACCENTS['propio'] = ('Personalizado', oscuro, claro)
    return c


# ─── Escalado DPI ───────────────────────────────────────────────────────
# Medidas de diseno a 96 ppp. Se multiplican por UI segun el DPI real, para
# que la tarjeta (dibujada con Pillow en pixeles) y el texto de tkinter
# (que crece con el DPI) mantengan siempre la misma proporcion.
BASE_W, BASE_H, BASE_PAD = 300, 38, 12

UI = 1.0
W, H = BASE_W, BASE_H
PAD = BASE_PAD


def apply_scale(ui):
    global UI, W, H, PAD
    UI = max(0.6, min(3.0, float(ui)))
    W = int(round(BASE_W * UI))
    H = int(round(BASE_H * UI))
    PAD = int(round(BASE_PAD * UI))


# Escala solo del sistema (DPI), sin el tamano elegido por el usuario: la
# usan el menu y las ventanas, que tienen tamano fijo. El tamano elegido
# solo agranda el widget; si agrandara el menu, este se salia de la pantalla.
DPI_UI = 1.0


def mpx(v):
    """Medida de diseno -> pixeles reales, para menu y ventanas."""
    return int(round(v * DPI_UI))


def px(v):
    """Medida de diseno -> pixeles reales."""
    return int(round(v * UI))


def _hex(c):
    c = c.lstrip('#')
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _mix(c1, c2, t):
    a, b = _hex(c1), _hex(c2)
    return '#%02x%02x%02x' % tuple(int(round(a[i] + (b[i] - a[i]) * t))
                                   for i in range(3))


# ─── Tipografia ─────────────────────────────────────────────────────────
# Segoe UI Variable es la letra de Windows 11, dibujada para verse nitida
# en tamanos pequenos. En Windows 10 no existe y se usa Segoe UI.
FUENTE = 'Segoe UI'


def elegir_fuente(root):
    global FUENTE
    try:
        import tkinter.font as tkfont
        if 'Segoe UI Variable Text' in tkfont.families(root):
            FUENTE = 'Segoe UI Variable Text'
    except Exception:
        pass
