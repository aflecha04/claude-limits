#!/usr/bin/env pythonw
# -*- coding: utf-8 -*-
"""
ClaudeGlass by Flecha - widget de escritorio para el uso de sesion de Claude.

Muestra:
  - el uso de la sesion de 5 horas como barra + %
  - cuanto queda para el reinicio de la sesion
  - boton de refresco y de cierre
  - menu de clic derecho: sessionKey, modo claro/oscuro, diagnostico

Persistencia robusta: la configuracion se busca y se guarda en varias
rutas (LOCALAPPDATA -> APPDATA -> carpeta del .exe -> perfil de usuario),
con escritura atomica y verificacion de relectura.
"""

import os
import re
import sys
import json
import random
import subprocess
import threading
from datetime import datetime, timezone

import tkinter as tk
import tkinter.font as tkfont

try:
    from PIL import Image, ImageChops, ImageDraw, ImageTk
    HAVE_PIL = True
except Exception:
    HAVE_PIL = False


def _dpi_aware():
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


# ─── API ────────────────────────────────────────────────────────────────
API_URL  = 'https://claude.ai/api/organizations/{}/usage'
ORGS_URL = 'https://claude.ai/api/organizations'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36')

REFRESH_MS = 30_000           # auto-refresh cada 30 s
TOPMOST_MS = 600              # re-afirmar siempre-encima

CFG_NAME = 'config.json'
POS_NAME = 'glass-pos.json'


# ─── Rutas de configuracion (cascada con respaldo) ──────────────────────
def _exe_dir():
    """Carpeta del .exe (o del .pyw en desarrollo)."""
    try:
        if getattr(sys, 'frozen', False):
            return os.path.dirname(os.path.abspath(sys.executable))
        return os.path.dirname(os.path.abspath(__file__))
    except Exception:
        return os.getcwd()


def cfg_dirs():
    """Rutas candidatas, por orden de preferencia. Sin duplicados."""
    out, seen = [], set()

    def add(p):
        if not p:
            return
        try:
            p = os.path.abspath(p)
        except Exception:
            return
        k = p.lower()
        if k not in seen:
            seen.add(k)
            out.append(p)

    la = os.environ.get('LOCALAPPDATA')
    if la:
        add(os.path.join(la, 'Claude Usage'))
    ra = os.environ.get('APPDATA')
    if ra:
        add(os.path.join(ra, 'ClaudeGlass'))
    add(_exe_dir())
    add(os.path.join(os.path.expanduser('~'), '.claudeglass'))
    return out


# Estado del ultimo guardado: lista de (ruta, ok, motivo)
SAVE_REPORT = []
LOADED_FROM = None


def _read_json(path):
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError('formato invalido')
    return data


def _atomic_write(path, obj, durable=True):
    """Escribe JSON de forma atomica y verifica releyendo.

    durable=False omite fsync y la relectura: se usa para ajustes cosmeticos
    (tema, tamano), donde os.replace ya garantiza que el archivo nunca queda
    a medias y no merece la pena esperar al disco (OneDrive puede tardar).
    """
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.flush()
        if durable:
            try:
                os.fsync(f.fileno())
            except Exception:
                pass
    os.replace(tmp, path)
    if durable:
        back = _read_json(path)                   # verificacion de relectura
        if back.get('session_key') != obj.get('session_key'):
            raise IOError('verificacion fallida')
    return True


def load_cfg():
    """Lee la primera config valida de la cascada.

    Prioriza cualquier archivo que YA tenga session_key, de modo que si la
    ruta preferente esta vacia o corrupta se recupera desde el respaldo.
    """
    global LOADED_FROM
    first_ok = None
    for d in cfg_dirs():
        p = os.path.join(d, CFG_NAME)
        try:
            data = _read_json(p)
        except Exception:
            continue
        if data.get('session_key'):
            LOADED_FROM = p
            return data
        if first_ok is None:
            first_ok = (p, data)
    if first_ok:
        LOADED_FROM = first_ok[0]
        return first_ok[1]
    LOADED_FROM = None
    return {}


_SAVE_LOCK = threading.Lock()


def save_cfg(cfg, durable=True):
    """Guarda en TODAS las rutas escribibles. Devuelve True si alguna fue bien."""
    global SAVE_REPORT
    with _SAVE_LOCK:
        report = []
        ok_any = False
        for d in cfg_dirs():
            p = os.path.join(d, CFG_NAME)
            try:
                _atomic_write(p, cfg, durable=durable)
                report.append((p, True, ''))
                ok_any = True
            except Exception as e:
                report.append((p, False, str(e)[:80]))
        SAVE_REPORT = report
        return ok_any


def pos_path_for_read():
    for d in cfg_dirs():
        p = os.path.join(d, POS_NAME)
        if os.path.exists(p):
            return p
    return None


def save_pos_file(obj):
    for d in cfg_dirs():
        p = os.path.join(d, POS_NAME)
        try:
            os.makedirs(d, exist_ok=True)
            tmp = p + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(obj, f)
            os.replace(tmp, p)
            return True
        except Exception:
            continue
    return False


def clean_key(raw):
    """Normaliza lo que pega el usuario: quita 'sessionKey=', comillas, ';'."""
    v = (raw or '').strip().strip('"').strip("'")
    m = re.search(r'sessionKey\s*=\s*([^;\s]+)', v)
    if m:
        v = m.group(1)
    return v.rstrip(';').strip()


def key_looks_real(v):
    return bool(v) and v.startswith('sk-ant-') and len(v) > 30


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
        ALPHA=1.0,
    ),
    'light': dict(
        PANEL_BG='#eef1f7', TILE_BD='#dde3ec',
        ACCENT='#c2542f',
        TEXT_ON_FILL='#ffffff',
        MENU_BG='#ffffff', MENU_BD='#e2e8f0', MENU_FG='#0b1220',
        MENU_MUTED='#5b6b82', MENU_HOVER='#fdf0ea', MENU_ACCENT='#c2542f',
        MENU_SEP='#eef1f6',
        TINT='#ffffff', CARD_BD='#dde3ec',
        INK='#0b1220', LABEL='#5b6b82', SUBTLE='#5b6b82',
        TRACK='#dbe3ef', TRACK_SH='#c3cddd', TIME='#3f4a5c', BTN='#5b6b82', BTN_HOV='#0f172a', CLOSE_HOV='#d1344b',
        BAR_START='#c2542f', BAR_END='#96391d',
        ALPHA=1.0,
    ),
}

# valores activos (se rellenan con apply_theme)
TINT = CARD_BD = HILITE = INK = LABEL = SUBTLE = TRACK = TRACK_SH = ''
TIME = BTN = BTN_HOV = CLOSE_HOV = BAR_START = BAR_END = ''
MENU_BG = MENU_BD = MENU_FG = MENU_MUTED = MENU_HOVER = ''
MENU_ACCENT = MENU_SEP = ''
SH_DARK = SH_LIGHT = ACCENT = TEXT_ON_FILL = ''
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

APP_NAME = 'ClaudeGlass by Flecha'
VERSION = '3.1'

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
                           ('#0f8a5c', '#0a5f40', '#0f8a5c', '#ffffff')),
    'violeta': ('Violeta', ('#a78bfa', '#7a4ae2', '#c4b0ff', '#ffffff'),
                           ('#6d3fd6', '#4a2596', '#6d3fd6', '#ffffff')),
    'blanco':  ('Blanco',  ('#e8ecf4', '#aab2c2', '#e8ecf4', '#14171e'),
                           ('#5b6b82', '#33415a', '#33415a', '#ffffff')),
}
ACCENT_NAME = 'coral'


def apply_accent(nombre):
    """Aplica el color elegido encima del tema activo."""
    global ACCENT_NAME, BAR_START, BAR_END, ACCENT, MENU_ACCENT, TEXT_ON_FILL
    ACCENT_NAME = nombre if nombre in ACCENTS else 'coral'
    _, oscuro, claro = ACCENTS[ACCENT_NAME]
    ini, fin, suave, sobre = oscuro if THEME == 'dark' else claro
    BAR_START, BAR_END = ini, fin
    ACCENT = MENU_ACCENT = suave
    TEXT_ON_FILL = sobre


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


# ─── Errores tipados ────────────────────────────────────────────────────
class NoKey(PermissionError):
    """No hay ninguna sessionKey configurada."""


class KeyExpired(PermissionError):
    """Hay clave, pero el servidor la rechaza (401/403)."""


# ─── Datos ──────────────────────────────────────────────────────────────
def _curl(url, cookie):
    r = subprocess.run(
        ['curl', '-s', '-D', '-',
         '-H', f'Cookie: {cookie}',
         '-H', f'User-Agent: {UA}',
         '-H', 'anthropic-client-platform: web_claude_ai',
         url],
        capture_output=True, text=True, timeout=20,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or 'curl error')
    return r.stdout


def _split(raw):
    parts = raw.split('\r\n\r\n', 1)
    if len(parts) < 2:
        parts = raw.split('\n\n', 1)
    headers = parts[0] if len(parts) == 2 else ''
    return headers, parts[-1].strip()


def _status(headers):
    m = re.search(r'HTTP/[\d.]+ (\d+)', headers)
    return int(m.group(1)) if m else 0


def resolve_org(cfg):
    headers, body = _split(_curl(ORGS_URL, f"sessionKey={cfg['session_key']}"))
    if _status(headers) in (401, 403):
        raise KeyExpired('Clave caducada')
    orgs = json.loads(body)
    if isinstance(orgs, list) and orgs:
        cfg['org_id'] = orgs[0]['uuid']
        save_cfg(cfg)
        return cfg['org_id']
    raise RuntimeError('no org')


def fetch_session():
    """Devuelve (pct:int, resets_at:str) de la sesion de 5 h, o lanza error."""
    cfg = load_cfg()
    if not cfg.get('session_key'):
        raise NoKey('Falta sessionKey')
    if not cfg.get('org_id'):
        resolve_org(cfg)

    cookie = f"sessionKey={cfg['session_key']}; lastActiveOrg={cfg['org_id']}"
    headers, body = _split(_curl(API_URL.format(cfg['org_id']), cookie))

    if _status(headers) in (401, 403):
        # NUNCA borrar la clave guardada: solo avisar
        raise KeyExpired('Clave caducada')

    # rotar la sessionKey SOLO si el servidor entrega una clave real y nueva
    km = re.search(r'sessionKey=(sk-ant-[^;\s]+)', headers)
    if km and len(km.group(1)) > 30 and km.group(1) != cfg.get('session_key'):
        cfg['session_key'] = km.group(1)
        save_cfg(cfg)

    data = normalizar_limites(json.loads(body))
    pct, reset = cuota(data, 'five_hour')
    if pct is None:
        raise RuntimeError('sin datos')
    return int(round(pct)), reset, data


def _dic(v):
    """Devuelve v si es un diccionario y {} si no.

    La respuesta de la API es ajena: si algun campo anidado dejara de ser un
    objeto, el widget debe quedarse sin ese dato, no reventar.
    """
    return v if isinstance(v, dict) else {}


def normalizar_limites(data):
    """Traduce el formato NUEVO de /usage al de siempre.

    Claude ya no devuelve solo 'five_hour': manda una lista 'limits' con
    kind = session (las 5 h), weekly_all (el limite semanal) y weekly_scoped
    (semanal de un modelo concreto, p. ej. Fable). Se convierten a campos
    planos para que el resto del widget no se entere del cambio, y si algun
    dia retiran 'five_hour' el widget sigue funcionando.
    """
    if not isinstance(data, dict):
        return {}
    out = dict(data)
    for lim in (data.get('limits') or []):
        if not isinstance(lim, dict):
            continue
        kind = lim.get('kind')
        campo = {'session': 'five_hour', 'weekly_all': 'seven_day'}.get(kind)
        if kind == 'weekly_scoped':
            modelo = _dic(_dic(lim.get('scope')).get('model'))
            nombre = str(modelo.get('display_name') or '').strip()
            if nombre:
                campo = 'seven_day_' + re.sub(r'[^a-z0-9]+', '_',
                                              nombre.lower()).strip('_')
        if campo:
            out[campo] = {'utilization': lim.get('percent'),
                          'resets_at': lim.get('resets_at'),
                          'nombre': _dic(_dic(lim.get('scope')).get('model'))
                          .get('display_name')}
    return out


def cuota(data, campo):
    """(porcentaje 0-100, resets_at) de un limite, o (None, None)."""
    v = (data or {}).get(campo)
    if not isinstance(v, dict):
        return None, None
    n = v.get('utilization')
    if isinstance(n, bool) or n is None:
        return None, None
    try:
        n = float(n)
    except (TypeError, ValueError):
        return None, None
    if n != n or n in (float('inf'), float('-inf')):
        return None, None
    return max(0.0, min(100.0, n)), v.get('resets_at')


def campos_de_modelo(data):
    """Limites semanales por modelo presentes en la respuesta."""
    return [k for k, v in (data or {}).items()
            if k.startswith('seven_day_') and k != 'seven_day_oauth_apps'
            and isinstance(v, dict) and cuota(data, k)[0] is not None]


def nombre_de_modelo(data, campo):
    v = (data or {}).get(campo) or {}
    if isinstance(v, dict) and v.get('nombre'):
        return str(v['nombre'])
    return campo.replace('seven_day_', '').replace('_', ' ').title()


def countdown(iso_str):
    """'4h 38m' / '12m' / 'pronto' hasta el reinicio."""
    if not iso_str:
        return ''
    try:
        target = datetime.fromisoformat(iso_str)
    except (ValueError, TypeError):
        return ''
    secs = (target - datetime.now(timezone.utc)).total_seconds()
    if secs <= 0:
        return 'pronto'
    h = int(secs) // 3600
    m = (int(secs) % 3600) // 60
    if h >= 24:
        return f'{h // 24}d {h % 24}h'
    if h > 0:
        return f'{h}h {m:02d}m'
    return f'{m}m'


def _reset_secs(iso_str):
    try:
        target = datetime.fromisoformat(iso_str)
    except (ValueError, TypeError):
        return 0
    return int((target - datetime.now(timezone.utc)).total_seconds())


def countdown_clock(iso_str):
    """Temporizador '2:53:41' hasta el reinicio."""
    secs = _reset_secs(iso_str)
    if secs <= 0:
        return '0:00:00'
    h = secs // 3600
    m = (secs % 3600) // 60
    s = secs % 60
    return f'{h}:{m:02d}:{s:02d}'


# ─── Instancia unica ────────────────────────────────────────────────────
# Sin esto, dos copias del widget (p. ej. un acceso directo viejo que abre
# la version anterior y otro que abre la nueva) se colocan en la MISMA
# posicion guardada y se turnan para estar encima cada 600 ms: se ve como
# un parpadeo entre el tema claro y el oscuro.
MUTEX_NAME = 'Global\\ClaudeGlassByFlecha_SingleInstance'
_MUTEX = None

EXE_NAMES_ANTIGUOS = ('ClaudeGlass.exe', 'ClaudeGlass_ANTIGUO.exe',
                      'claude_usage.exe', 'ClaudeUsage.exe')


def ya_hay_una_instancia():
    """True si ya corre otra copia de ESTE ejecutable."""
    global _MUTEX
    try:
        import ctypes
        from ctypes import wintypes
        k = ctypes.windll.kernel32
        k.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        k.CreateMutexW.restype = wintypes.HANDLE
        _MUTEX = k.CreateMutexW(None, False, MUTEX_NAME)
        return k.GetLastError() == 183          # ERROR_ALREADY_EXISTS
    except Exception:
        return False


def cerrar_versiones_antiguas():
    """Cierra ejecutables de versiones previas, que no tienen instancia unica.

    Es la otra mitad del arreglo del parpadeo: el mutex evita duplicados de
    esta version, pero la anterior no lo respeta, asi que hay que cerrarla.
    """
    cerradas = []
    mi_exe = os.path.basename(sys.executable).lower() if getattr(sys, 'frozen', False) else ''
    for nombre in EXE_NAMES_ANTIGUOS:
        if nombre.lower() == mi_exe:
            continue
        try:
            r = subprocess.run(['taskkill', '/IM', nombre, '/F'],
                               capture_output=True, text=True, timeout=10,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if r.returncode == 0:
                cerradas.append(nombre)
        except Exception:
            continue
    return cerradas


# ─── Arranque con Windows (registro, sin PowerShell ni COM) ─────────────
# El instalador creaba el acceso directo con New-Object -ComObject de
# PowerShell. En equipos con AppLocker o Constrained Language Mode eso esta
# bloqueado y fallaba en silencio: de ahi el "no se inicia solo". La clave
# de registro HKCU\...\Run no necesita COM, ni PowerShell, ni ser admin.
RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
RUN_VALUE = 'ClaudeGlass by Flecha'
# Windows guarda aparte si el usuario ha DESACTIVADO la entrada en
# Administrador de tareas > Inicio. Mientras ese veto siga ahi, da igual
# cuantas veces reescribamos la clave Run: no arranca y no avisa de nada.
APPROVED_KEY = (r'Software\Microsoft\Windows\CurrentVersion\Explorer'
                r'\StartupApproved\Run')


def _mi_ruta():
    if getattr(sys, 'frozen', False):
        return os.path.abspath(sys.executable)
    return os.path.abspath(__file__)


def autostart_estado():
    """Devuelve la ruta registrada para arrancar con Windows, o None."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            valor, _ = winreg.QueryValueEx(k, RUN_VALUE)
            return valor.strip('"')
    except Exception:
        return None


def autostart_vetado():
    """True si Windows tiene desactivada la entrada de inicio.

    El primer byte vale 2 o 6 cuando esta habilitada; cualquier otra cosa
    (tipicamente 3) significa que alguien la desactivo.
    """
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APPROVED_KEY) as k:
            datos, _ = winreg.QueryValueEx(k, RUN_VALUE)
            return bool(datos) and datos[0] not in (2, 6)
    except Exception:
        return False


def autostart_quitar_veto():
    """Borra el veto. Sin valor, Windows la considera habilitada."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APPROVED_KEY, 0,
                            winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, RUN_VALUE)
        return True
    except Exception:
        return False


def autostart_activar(activar=True):
    try:
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            if activar:
                winreg.SetValueEx(k, RUN_VALUE, 0, winreg.REG_SZ, f'"{_mi_ruta()}"')
                if autostart_vetado():
                    autostart_quitar_veto()
            else:
                try:
                    winreg.DeleteValue(k, RUN_VALUE)
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        return False


def limpiar_accesos_directos_viejos():
    """Borra los .lnk de arranque de versiones anteriores.

    Mientras exista uno, el .exe viejo se abre al iniciar sesion y vuelve el
    parpadeo. El arranque de esta version va por registro, asi que ningun
    acceso directo nuestro deberia quedar en esa carpeta.
    """
    borrados = []
    ap = os.environ.get('APPDATA')
    if not ap:
        return borrados
    carpeta = os.path.join(ap, 'Microsoft', 'Windows', 'Start Menu',
                           'Programs', 'Startup')
    try:
        for nombre in os.listdir(carpeta):
            bajo = nombre.lower()
            if bajo.endswith('.lnk') and ('claudeglass' in bajo.replace(' ', '')
                                          or 'claude usage' in bajo):
                try:
                    os.remove(os.path.join(carpeta, nombre))
                    borrados.append(nombre)
                except Exception:
                    pass
    except Exception:
        pass
    return borrados


# ─── Registro de errores ────────────────────────────────────────────────
def log_error(texto):
    """Deja el fallo por escrito: sin consola, un cierre inesperado no deja rastro."""
    for d in cfg_dirs():
        try:
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, 'error.log'), 'a', encoding='utf-8') as f:
                f.write(f'\n===== {datetime.now().isoformat(timespec="seconds")} '
                        f'v{VERSION} =====\n{texto}\n')
            return True
        except Exception:
            continue
    return False


# ─── Area util del monitor ──────────────────────────────────────────────
def work_area(x, y):
    """Rectangulo util (l, t, r, b) del monitor que contiene el punto (x, y).

    Usa el area de TRABAJO, no la pantalla completa: descuenta la barra de
    tareas. Y busca el monitor correcto, asi que funciona con varias
    pantallas y con la secundaria a la izquierda (coordenadas negativas).
    """
    try:
        import ctypes

        class RECT(ctypes.Structure):
            _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long),
                        ('right', ctypes.c_long), ('bottom', ctypes.c_long)]

        class MONITORINFO(ctypes.Structure):
            _fields_ = [('cbSize', ctypes.c_ulong), ('rcMonitor', RECT),
                        ('rcWork', RECT), ('dwFlags', ctypes.c_ulong)]

        class POINT(ctypes.Structure):
            _fields_ = [('x', ctypes.c_long), ('y', ctypes.c_long)]

        u = ctypes.windll.user32
        mon = u.MonitorFromPoint(POINT(int(x), int(y)), 2)   # NEAREST
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if u.GetMonitorInfoW(mon, ctypes.byref(mi)):
            r = mi.rcWork
            if r.right > r.left and r.bottom > r.top:
                return r.left, r.top, r.right, r.bottom
    except Exception:
        pass
    return None


# ─── Mensajes del modo dormido ─────────────────────────────────────────
# Al llegar al 100 % la barra dice 'Claude duerme'... o, con cierta
# probabilidad, otra cosa. El mensaje se sortea UNA vez por cada periodo de
# descanso (la semilla es la hora de reinicio): no cambia en cada repintado
# ni al reabrir el widget, y el siguiente descanso trae otro sorteo.
MENSAJE_DORMIDO = 'Claude duerme'
PROB_MENSAJE_CLASICO = 0.5          # 50 %: el de siempre; 50 %: uno de estos
MENSAJES_DORMIDO = (
    'Claude está soñando',
    'Zzz…',
    'Recargando neuronas',
    'Claude ha ido a por café',
    'Enfriando circuitos',
    'Claude medita',
    'Siesta obligatoria',
    'Recargando pilas',
    'Fuera de la oficina',
    'Modo avión',
    'Vuelve enseguida',
    'Soñando con tokens',
    'Toca estirar las piernas',
    'Ha salido a tomar el aire',
    'Claude hace yoga',
    'Cerrado por descanso',
)


def mensaje_dormido(semilla):
    """Mensaje del modo dormido para ese periodo de descanso."""
    rnd = random.Random(str(semilla))
    if rnd.random() < PROB_MENSAJE_CLASICO:
        return MENSAJE_DORMIDO
    return rnd.choice(MENSAJES_DORMIDO)


# ─── Pantallas conectadas ───────────────────────────────────────────────
# Con portatil + monitores externos, desenchufar y volver a enchufar cambia
# el mapa de pantallas. Windows reubica las ventanas normales, pero con una
# ventana sin marco como esta a veces la deja en coordenadas donde ya no hay
# ninguna pantalla: sigue abierta, pero no se ve. Por eso el widget vigila
# el mapa de pantallas y recuerda una posicion para cada configuracion.
def monitores():
    """Rectangulos (l, t, r, b) de cada pantalla conectada; [] fuera de Windows."""
    try:
        import ctypes

        class RECT(ctypes.Structure):
            _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long),
                        ('right', ctypes.c_long), ('bottom', ctypes.c_long)]

        res = []
        PROC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p,
                                  ctypes.c_void_p, ctypes.POINTER(RECT),
                                  ctypes.c_ssize_t)

        def _cb(_hmon, _hdc, lprc, _data):
            r = lprc.contents
            if r.right > r.left and r.bottom > r.top:
                res.append((r.left, r.top, r.right, r.bottom))
            return 1

        cb = PROC(_cb)
        ctypes.windll.user32.EnumDisplayMonitors(None, None, cb, 0)
        return sorted(res)
    except Exception:
        return []


def firma_monitores(mons):
    """Huella de una configuracion de pantallas: '0,0,1920,1080|1920,0,...'"""
    return '|'.join(','.join(str(v) for v in m) for m in mons)


def se_ve(x, y, w, h, mons):
    """True si en ALGUNA pantalla asoma lo bastante del widget para agarrarlo:
    al menos la mitad de su alto y 60 px de ancho.

    Mirar pantalla a pantalla importa: con dos monitores de distinto alto el
    rectangulo que los envuelve tiene huecos donde no hay pantalla ninguna, y
    la comprobacion antigua (contra ese rectangulo) daba por buena una
    posicion invisible.
    """
    for l, t, r, b in mons:
        ancho = min(x + w, r) - max(x, l)
        alto = min(y + h, b) - max(y, t)
        if ancho >= min(60, w) and alto >= h // 2:
            return True
    return False


def encajar(x, y, w, h):
    """Lleva (x, y) dentro del area util de la pantalla mas cercana."""
    wa = work_area(x + w // 2, y + h // 2)
    if not wa:
        return x, y
    l, t, r, b = wa
    m = 8
    x = min(max(x, l + m), max(l + m, r - w - m))
    y = min(max(y, t + m), max(t + m, b - h - m))
    return x, y


# ─── Esquinas redondeadas ───────────────────────────────────────────────
def round_corners(root):
    try:
        import ctypes
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        pref = ctypes.c_int(2)                 # DWMWCP_ROUND
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 33, ctypes.byref(pref), ctypes.sizeof(pref))
    except Exception:
        pass


# ─── Fuera de la barra de tareas ────────────────────────────────────────
# Tk marca la ventana sin marco como 'ventana de herramientas'
# (WS_EX_TOOLWINDOW), y eso es lo que la deja fuera de la barra de tareas.
# Pero hay situaciones (enchufar/desenchufar pantallas, cambios de escala,
# el Explorador reconstruyendo la barra) en las que la ventana acaba sin esa
# marca y aparece una pestana con el widget.
#
# Aqui se comprueba la marca y, solo si falta, se repone. OJO: nunca con
# withdraw()/deiconify() de Tk, que fue justo lo que CREO el problema la
# primera vez (Tk rehace la ventana y la registra como aplicacion). Se hace
# con la API de Windows directamente, sin que Tk se entere.
_GWL_EXSTYLE = -20
_WS_EX_TOOLWINDOW = 0x00000080
_WS_EX_APPWINDOW = 0x00040000


def _ventana_nativa(widget):
    """HWND de la ventana de verdad (el marco que ve Windows, no el hijo de Tk)."""
    import ctypes
    return ctypes.windll.user32.GetAncestor(widget.winfo_id(), 2)   # GA_ROOT


def asegurar_fuera_de_barra(widget):
    """Repone la marca de ventana de herramientas si se ha perdido.

    Devuelve None si todo estaba bien (lo normal: no toca nada), o el
    estilo que tenia antes de corregirlo, para dejarlo apuntado.
    """
    try:
        import ctypes
        u = ctypes.windll.user32
        if ctypes.sizeof(ctypes.c_void_p) == 8:
            leer, escribir = u.GetWindowLongPtrW, u.SetWindowLongPtrW
        else:
            leer, escribir = u.GetWindowLongW, u.SetWindowLongW
        leer.restype = ctypes.c_ssize_t
        leer.argtypes = [ctypes.c_void_p, ctypes.c_int]
        escribir.restype = ctypes.c_ssize_t
        escribir.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
        hwnd = _ventana_nativa(widget)
        if not hwnd:
            return None
        antes = leer(hwnd, _GWL_EXSTYLE)
        bien = (antes | _WS_EX_TOOLWINDOW) & ~_WS_EX_APPWINDOW
        if bien == antes:
            return None
        escribir(hwnd, _GWL_EXSTYLE, bien)
        # El Explorador solo revisa la pestana al ocultar/mostrar la ventana.
        # ShowWindow directo: Tk no rehace nada y no roba el foco.
        u.ShowWindow(hwnd, 0)             # SW_HIDE
        u.ShowWindow(hwnd, 4)             # SW_SHOWNOACTIVATE
        return antes
    except Exception:
        return None


# ─── Widget ─────────────────────────────────────────────────────────────
class Glass:
    def __init__(self):
        _dpi_aware()

        cfg = load_cfg()
        apply_theme(cfg.get('theme', 'dark'), cfg.get('accent', 'coral'))

        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)

        # escala segun el DPI real de la pantalla (125%, 150%, 175%...)
        try:
            dpi = self.root.winfo_fpixels('1i')
        except Exception:
            dpi = 96.0
        self.root.tk.call('tk', 'scaling', 1.0)   # fuentes en px, sin sorpresas
        self.dpi = dpi or 96.0
        # escala del usuario (barrita del menu), sobre la escala del sistema
        try:
            self.user_scale = float(cfg.get('scale', 1.0))
        except Exception:
            self.user_scale = 1.0
        # A partir de esta version el tamano de fabrica es Normal (100 %).
        # Se reajusta una sola vez a quien viniera con otro valor guardado.
        if not cfg.get('size_normalizado_v31'):
            self.user_scale = 1.0
            try:
                cfg['scale'] = 1.0
                cfg['size_normalizado_v31'] = True
                save_cfg(cfg, durable=False)
            except Exception:
                pass
        self.user_scale = max(0.7, min(2.0, self.user_scale))
        apply_scale(self.dpi / 96.0 * self.user_scale)

        x, y = self._load_pos()
        self.root.geometry(f'{W}x{H}+{x}+{y}')

        self.acrylic = False
        self.root.attributes('-alpha', ALPHA)
        self.root.configure(bg=TINT)
        self._bg = TINT
        round_corners(self.root)

        self.cv = tk.Canvas(self.root, width=W, height=H,
                            bg=TINT, highlightthickness=0, bd=0)
        self.cv.pack(fill='both', expand=True)

        # fuentes: tamano NEGATIVO = pixeles, para que no las escale el DPI
        # Escala tipografica: la cifra manda, la unidad acompana y el
        # rotulo se aparta. Las cifras en familia ancha, los textos en Segoe UI.
        self.f_pct   = tkfont.Font(family='Segoe UI', size=-px(13), weight='bold')
        self.f_sub   = tkfont.Font(family='Segoe UI', size=-px(13))
        self.f_msg   = tkfont.Font(family='Segoe UI', size=-px(11), weight='bold')
        self.f_pnum  = tkfont.Font(family='Segoe UI', size=-px(18), weight='bold')
        self.f_ptit  = tkfont.Font(family='Segoe UI', size=-px(11))
        self.f_pcd   = tkfont.Font(family='Segoe UI', size=-px(11))
        self.f_icon = tkfont.Font(family='Segoe UI Symbol', size=-px(14))

        self.pct = None
        self.reset_iso = None
        self.state = 'Cargando...'
        self.key_state = 'ok'        # ok | nokey | expired | offline
        self.status_msg = None       # texto dentro de la barra si hay aviso
        self._auto_prompted = False
        self._save_warned = False
        self.usage = {}
        self._panel = None
        self._txtwin = None
        self._szdlg = None
        self._dlg = None
        self._menu_win = None
        self._arrastrando = False
        self._hover_abrir_id = None
        self._hover_cerrar_id = None

        self._build()               # crea tambien el menu contextual
        self._bind_drag()

        self._sleeping = False
        self.refresh()
        self._tick_topmost()
        self._tick_pantallas()
        self._tick_countdown()
        self._tick_clock()

        # primer arranque sin clave -> pedirla UNA vez
        if not cfg.get('session_key'):
            self._auto_prompted = True
            self.root.after(400, self._key_dialog)

    # ---- layout -------------------------------------------------------
    def _build(self):
        c = self.cv
        cy = H // 2
        self._geometria_barra()
        self._cd = ''

        self._shape_id = c.create_image(0, 0, anchor='nw', tags='shape')

        self.id_close = c.create_text(W - PAD, cy, text='✕', anchor='e',
                                      fill=BTN, font=self.f_icon)


        self._hook(self.id_close, CLOSE_HOV, self.close)

        self._render_all()

    # ---- menu contextual (dibujado a mano, no el nativo de Windows) ----
    def _close_menu(self, e=None):
        w = getattr(self, '_menu_win', None)
        self._menu_win = None
        if w is not None:
            try:
                w.grab_release()
            except Exception:
                pass
            try:
                w.destroy()
            except Exception:
                pass

    # ---- panel flotante (semanal y modelos) ----------------------------
    HOVER_ABRIR_MS = 450        # tiempo parado encima antes de desplegar
    HOVER_CERRAR_MS = 260       # margen para poder mover el raton al panel

    def _hover_programar_apertura(self, e=None):
        self._hover_cancelar(cerrar=True)
        if getattr(self, '_arrastrando', False):
            return
        self._hover_abrir_id = self.root.after(self.HOVER_ABRIR_MS,
                                               self._panel_mostrar)

    def _hover_programar_cierre(self, e=None):
        self._hover_cancelar(abrir=True)
        self._hover_cerrar_id = self.root.after(self.HOVER_CERRAR_MS,
                                                self._panel_ocultar)

    def _hover_cancelar(self, abrir=False, cerrar=False):
        if abrir or not cerrar:
            i = getattr(self, '_hover_abrir_id', None)
            if i:
                try:
                    self.root.after_cancel(i)
                except Exception:
                    pass
                self._hover_abrir_id = None
        if cerrar or not abrir:
            i = getattr(self, '_hover_cerrar_id', None)
            if i:
                try:
                    self.root.after_cancel(i)
                except Exception:
                    pass
                self._hover_cerrar_id = None

    def _panel_ocultar(self, e=None):
        self._hover_cancelar()
        w = getattr(self, '_panel', None)
        self._panel = None
        if w is not None:
            try:
                w.destroy()
            except Exception:
                pass

    def _panel_maqueta(self, n):
        """Coordenadas de la maqueta, en pixeles logicos. Las comparten el
        fondo (Pillow) y los textos (tkinter), para que encajen exactos."""
        PAD, GAP, ALTO = px(14), px(10), px(68)
        ancho = max(W, px(264))
        filas = []
        for i in range(n):
            y = PAD + i * (ALTO + GAP)
            # y_tit e y_num son CENTROS de linea: asi el titulo y la cuenta
            # atras quedan alineados aunque tengan tamanos distintos.
            filas.append(dict(
                x0=PAD, x1=ancho - PAD, y0=y, y1=y + ALTO,
                tx0=PAD + px(14), tx1=ancho - PAD - px(14),
                y_tit=y + px(16), y_num=y + px(38),
                y_bar=y + px(54), alto_bar=px(8)))
        return ancho, PAD * 2 + n * ALTO + max(0, n - 1) * GAP, filas

    def _panel_img(self, filas):
        """Solo las formas: piezas y barras. El texto lo pone tkinter encima,
        que lo dibuja con el suavizado del sistema en vez de reducirlo
        desde una imagen a 4x."""
        clave = (THEME, ACCENT_NAME, W, UI,
                 tuple(round(p, 1) for _t, p, _r in filas))
        cache = getattr(self, '_panel_cache', None)
        if cache is None:
            cache = self._panel_cache = {}
        hit = cache.get(clave)
        if hit is not None:
            self._panel_photo = hit[0]
            return hit

        SS = self.SS
        ancho, alto, maqueta = self._panel_maqueta(len(filas))
        img = Image.new('RGBA', (ancho * SS, alto * SS),
                        _hex(PANEL_BG or TINT) + (255,))
        d = ImageDraw.Draw(img)
        for (_titulo, pct, _res), m in zip(filas, maqueta):
            d.rounded_rectangle([m['x0'] * SS, m['y0'] * SS,
                                 m['x1'] * SS, m['y1'] * SS],
                                radius=px(12) * SS, fill=TINT,
                                outline=TILE_BD, width=SS)
            bx0, bx1 = m['tx0'] * SS, m['tx1'] * SS
            by0 = m['y_bar'] * SS
            bh = m['alto_bar'] * SS
            br = bh // 2
            d.rounded_rectangle([bx0, by0, bx1, by0 + bh], radius=br,
                                fill=TRACK, outline=TRACK_SH, width=max(1, SS // 2))
            if pct and pct > 0:
                total = bx1 - bx0
                relleno = max(bh, int(round(total * min(pct, 100) / 100.0)))
                cs, ce = BAR_START, BAR_END
                grad = self._grad_strip(cs, ce).resize((relleno, bh),
                                                       Image.BILINEAR)
                mask = Image.new('L', (relleno, bh), 0)
                ImageDraw.Draw(mask).rounded_rectangle(
                    [0, 0, relleno - 1, bh - 1], radius=br, fill=255)
                img.paste(grad, (bx0, by0), mask)

        out = img.resize((ancho, alto), Image.LANCZOS).convert('RGB')
        self._panel_photo = ImageTk.PhotoImage(out)
        if len(cache) > 8:
            cache.clear()
        res = (self._panel_photo, ancho, alto)
        cache[clave] = res
        return res

    def _panel_filas(self):
        """[(titulo, pct, resets_at)] de los limites que NO son el de 5 h."""
        u = getattr(self, 'usage', None) or {}
        filas = []
        pct, res = cuota(u, 'seven_day')
        if pct is not None:
            filas.append(('Límite semanal', pct, res))
        for campo in sorted(campos_de_modelo(u)):
            if campo == 'seven_day':
                continue
            pct, res = cuota(u, campo)
            if pct is not None:
                filas.append((nombre_de_modelo(u, campo), pct, res))
        return filas

    def _limite_agotado(self):
        """True si algun limite del panel (semanal o de un modelo) esta al 100 %."""
        try:
            return any(p >= 100 for _t, p, _r in self._panel_filas())
        except Exception:
            return False

    def _panel_mostrar(self, e=None):
        self._hover_cancelar()
        if getattr(self, '_panel', None) is not None or getattr(self, '_menu_win', None):
            return
        if getattr(self, '_arrastrando', False):
            return
        filas = self._panel_filas()
        self._panel_firma_actual = self._panel_firma()

        w = tk.Toplevel(self.root)
        self._panel = w
        w.overrideredirect(True)
        w.attributes('-topmost', True)
        w.configure(bg=(TILE_BD or CARD_BD))

        if filas:
            foto, pw, ph = self._panel_img(filas)
            c = tk.Canvas(w, width=pw, height=ph, bg=(PANEL_BG or TINT),
                          highlightthickness=0, bd=0)
            c.pack()
            c.create_image(0, 0, anchor='nw', image=foto)
            _a, _h, maqueta = self._panel_maqueta(len(filas))
            dy_t = self._dy_optico(self.f_ptit)
            dy_n = self._dy_optico(self.f_pnum)
            for (titulo, pct, res), m in zip(filas, maqueta):
                # un limite agotado lo dice con palabras: 'Agotado' en vez
                # de '100%', y cuando vuelve en vez de solo el tiempo
                agotado = pct >= 100
                c.create_text(m['tx0'], m['y_tit'] + dy_t, text=titulo,
                              anchor='w', fill=MENU_MUTED, font=self.f_ptit)
                if res:
                    c.create_text(m['tx1'], m['y_tit'] + dy_t,
                                  text=(f'vuelve en {countdown(res)}'
                                        if agotado else countdown(res)),
                                  anchor='e',
                                  fill=(MENU_FG if agotado else MENU_MUTED),
                                  font=self.f_pcd)
                c.create_text(m['tx0'], m['y_num'] + dy_n,
                              text=('Agotado' if agotado else f'{pct:.0f}%'),
                              anchor='w', fill=MENU_FG, font=self.f_pnum)
            hijos = (c,)
        else:
            pw = max(W, px(264))
            marco = tk.Frame(w, bg=TINT)
            marco.pack(fill='both', expand=True)
            tk.Label(marco, text='Sin límite semanal', bg=TINT, fg=INK,
                     font=('Segoe UI', -px(12), 'bold'), anchor='w').pack(
                         fill='x', padx=px(16), pady=(px(16), 0))
            tk.Label(marco, text='Tu cuenta no informa de cuota semanal,\n'
                               'o aún no se ha podido consultar.',
                     bg=TINT, fg=SUBTLE, font=('Segoe UI', -px(11)),
                     justify='left', anchor='w').pack(
                         fill='x', padx=px(16), pady=(2, px(16)))
            hijos = (marco,)
            w.update_idletasks()
            ph = w.winfo_reqheight()

        def marcar(_e=None):
            self._hover_cancelar(abrir=True)
        w.bind('<Enter>', marcar)
        w.bind('<Leave>', self._hover_programar_cierre)
        for h in hijos:
            h.bind('<Enter>', marcar)
            h.bind('<Leave>', self._hover_programar_cierre)

        # Pegado al widget: 8 px por debajo, o por encima si no cabe.
        # Se calcula aqui y se fija tal cual; pasar por _place aplicaria un
        # segundo volteo y el panel acababa lejisimos del widget.
        wx, wy = self.root.winfo_x(), self.root.winfo_y()
        hueco = px(8)
        wa = work_area(wx + W // 2, wy) or (0, 0,
                                            w.winfo_screenwidth(),
                                            w.winfo_screenheight())
        l, t, r, b = wa
        y = wy + H + hueco
        if y + ph > b:                      # no cabe debajo -> encima
            y = wy - ph - hueco
        y = max(t, min(y, b - ph))
        x = max(l, min(wx, r - pw))         # alineado al borde izq. del widget
        w.geometry(f'{pw}x{ph}+{int(x)}+{int(y)}')
        round_corners(w)

    def _panel_refrescar(self):
        """Redibuja el panel abierto SOLO si cambia algo que se vea.

        Reconstruirlo en cada actualizacion lo haria parpadear a la vista.
        """
        if getattr(self, '_panel', None) is None:
            return
        firma = self._panel_firma()
        if firma == getattr(self, '_panel_firma_actual', None):
            return
        try:
            self._panel_ocultar()
            self._panel_mostrar()
        except Exception:
            pass

    def _panel_firma(self):
        return (THEME, ACCENT_NAME, UI) + tuple(
            (t, round(p, 1), countdown(r)) for t, p, r in self._panel_filas())

    def _place(self, win, x, y):
        """Coloca una ventana junto a (x, y) sin que se salga del monitor.

        Si no cabe hacia abajo o hacia la derecha, se abre en sentido
        contrario; y como ultimo recurso se pega al borde del area util.
        """
        try:
            win.update_idletasks()
            w = max(win.winfo_reqwidth(), win.winfo_width())
            h = max(win.winfo_reqheight(), win.winfo_height())
            wa = work_area(x, y)
            if wa:
                l, t, r, b = wa
            else:
                l, t = 0, 0
                r, b = win.winfo_screenwidth(), win.winfo_screenheight()
            x, y = int(x), int(y)
            if x + w > r:                  # no cabe a la derecha -> a la izq.
                x -= w
            if y + h > b:                  # no cabe abajo -> hacia arriba
                y -= h
            x = max(l, min(x, r - w))      # y nunca fuera del area util
            y = max(t, min(y, b - h))
            win.geometry(f'{w}x{h}+{x}+{y}')
        except Exception:
            try:
                win.geometry(f'+{int(x)}+{int(y)}')
            except Exception:
                pass

    def _punto_img(self, activo, fondo):
        """Circulito del interruptor, dibujado con Pillow y cacheado.

        Vacio = apagado, relleno = encendido. El canvas de tkinter dibuja los
        ovalos con el borde dentado; asi sale con el canto limpio.
        """
        d = px(13)
        key = (d, bool(activo), fondo, MENU_ACCENT, MENU_MUTED)
        cache = getattr(self, '_punto_cache', None)
        if cache is None:
            cache = self._punto_cache = {}
        if key in cache:
            return cache[key]
        if not HAVE_PIL:
            return None
        SS = 4
        img = Image.new('RGB', (d * SS, d * SS), fondo)
        g = ImageDraw.Draw(img)
        caja = [SS, SS, d * SS - SS - 1, d * SS - SS - 1]
        if activo:
            g.ellipse(caja, fill=MENU_ACCENT, outline=MENU_ACCENT, width=SS)
        else:
            g.ellipse(caja, fill=fondo, outline=MENU_MUTED, width=int(SS * 1.4))
        foto = ImageTk.PhotoImage(img.resize((d, d), Image.LANCZOS))
        if len(cache) > 16:
            cache.clear()
        cache[key] = foto
        return foto

    def _mrow(self, parent, text, cmd, mark='', muted=False, bold=False,
              punto=None):
        """Fila del menu: solo texto. La columna de iconos que habia antes
        metia ruido y no aportaba nada.

        'punto' (True/False) pinta un interruptor redondo a la derecha, en
        vez del tick, que quedaba desalineado y con los bordes sucios.
        """
        f = tk.Frame(parent, bg=MENU_BG, cursor='hand2')
        f.pack(fill='x')
        lt = tk.Label(f, text=text, bg=MENU_BG,
                      fg=(MENU_MUTED if muted else MENU_FG),
                      font=('Segoe UI', -px(12)), anchor='w')
        lt.pack(side='left', padx=(px(14), 0), pady=px(6))
        if punto is None:
            lm = tk.Label(f, text=mark, bg=MENU_BG, fg=MENU_ACCENT,
                          font=('Segoe UI', -px(11)))
        else:
            lm = tk.Label(f, bg=MENU_BG, bd=0, highlightthickness=0)
            lm._punto = punto
            im = self._punto_img(punto, MENU_BG)
            if im is not None:
                lm.configure(image=im)
                lm._img = im                      # que no se lo lleve el GC
            else:
                lm.configure(text=('●' if punto else '○'),
                             fg=(MENU_ACCENT if punto else MENU_MUTED),
                             font=('Segoe UI', -px(12)))
        lm.pack(side='right', padx=(0, px(14)))
        partes = (f, lt, lm)

        def pintar(bg):
            for p in partes:
                p.configure(bg=bg)
            # el circulito lleva su fondo dentro de la imagen: si no se
            # redibuja, al pasar el raton queda un cuadrado mas oscuro
            if punto is not None:
                im = self._punto_img(punto, bg)
                if im is not None:
                    lm.configure(image=im)
                    lm._img = im

        def entrar(_e=None):
            pintar(MENU_HOVER)

        def salir(_e=None):
            pintar(MENU_BG)

        def clic(_e=None):
            self._close_menu()
            self.root.after(1, cmd)

        for p in partes:
            p.bind('<Enter>', entrar)
            p.bind('<Leave>', salir)
            p.bind('<Button-1>', clic)
        return f

    def _msep(self, parent):
        tk.Frame(parent, bg=MENU_SEP, height=1).pack(
            fill='x', padx=px(12), pady=px(5))

    def _mchips(self, parent, opciones, activo, accion):
        """Fila de pastillas seleccionables. Cuatro tamanos ocupan una linea
        en vez de cuatro, y de un vistazo se ve cual esta puesto."""
        fila = tk.Frame(parent, bg=MENU_BG)
        fila.pack(fill='x', padx=(px(12), px(12)), pady=(px(3), px(2)))
        for etiqueta, valor in opciones:
            act = (valor == activo)
            chip = tk.Label(fila, text=etiqueta, bg=(MENU_HOVER if act else MENU_BG),
                            fg=(MENU_ACCENT if act else MENU_MUTED),
                            font=('Segoe UI', -px(12), 'bold' if act else 'normal'),
                            padx=px(9), pady=px(4), cursor='hand2')
            chip.pack(side='left', padx=(0, px(4)))
            if not act:
                chip.bind('<Enter>', lambda e, c=chip: c.configure(
                    bg=MENU_HOVER, fg=MENU_FG))
                chip.bind('<Leave>', lambda e, c=chip: c.configure(
                    bg=MENU_BG, fg=MENU_MUTED))
            chip.bind('<Button-1>', lambda e, v=valor: (
                self._close_menu(), self.root.after(1, lambda: accion(v))))
        return fila

    def _mcolores(self, parent):
        """Los colores, como puntos. Un texto por color llenaria el menu."""
        fila = tk.Frame(parent, bg=MENU_BG)
        fila.pack(fill='x', padx=px(12), pady=(px(6), px(5)))
        for clave, (nombre, oscuro, claro) in ACCENTS.items():
            muestra = (oscuro if THEME == 'dark' else claro)[0]
            act = (clave == ACCENT_NAME)
            punto = tk.Label(fila, text=('\u25c9' if act else '\u25cf'),
                             bg=MENU_BG, fg=muestra,
                             font=('Segoe UI', -px(24 if act else 20)),
                             padx=px(4), pady=px(2), cursor='hand2')
            punto.pack(side='left')
            punto.bind('<Button-1>', lambda e, k=clave: (
                self._close_menu(),
                self.root.after(1, lambda: self._set_accent(k))))
            punto.bind('<Enter>', lambda e, c=punto: c.configure(bg=MENU_HOVER))
            punto.bind('<Leave>', lambda e, c=punto: c.configure(bg=MENU_BG))
        return fila

    def _popup(self, e=None):
        self._panel_ocultar()
        self._close_menu()
        m = tk.Toplevel(self.root)
        self._menu_win = m
        m.overrideredirect(True)
        m.attributes('-topmost', True)
        m.configure(bg=MENU_BD)
        body = tk.Frame(m, bg=MENU_BG)
        body.pack(fill='both', expand=True, padx=1, pady=1)

        hd = tk.Frame(body, bg=MENU_BG)
        hd.pack(fill='x', padx=px(14), pady=(px(10), px(8)))
        tk.Label(hd, text='ClaudeGlass', bg=MENU_BG, fg=MENU_FG,
                 font=('Segoe UI', -px(14), 'bold')).pack(side='left')
        tk.Label(hd, text=' by Flecha', bg=MENU_BG, fg=MENU_ACCENT,
                 font=('Segoe UI', -px(13), 'italic')).pack(side='left')
        tk.Label(hd, text=f'v{VERSION}', bg=MENU_BG, fg=MENU_MUTED,
                 font=('Segoe UI', -px(10))).pack(side='right')
        self._msep(body)

        self._mrow(body, 'Actualizar', self.refresh)
        self._mrow(body, 'Cambiar sessionKey…', self._key_dialog)

        self._msep(body)
        self._mchips(body, [('Oscuro', 'dark'), ('Claro', 'light')],
                     THEME, self._set_theme)
        self._mcolores(body)
        self._mchips(body, [('80', 80), ('100', 100), ('125', 125),
                            ('150', 150), ('⋯', 'barra')],
                     int(round(self.user_scale * 100)),
                     lambda v: (self._size_dialog() if v == 'barra'
                                else self._set_scale(v / 100.0)))

        self._msep(body)
        arranca = (autostart_estado() or '').lower() == _mi_ruta().lower()
        self._mrow(body, 'Iniciar con Windows', self._toggle_autostart,
                   punto=arranca)
        self._mrow(body, 'Diagnóstico', self._info_dialog, muted=True)
        self._mrow(body, 'Cerrar', self.close, muted=True)
        tk.Frame(body, bg=MENU_BG, height=px(6)).pack(fill='x')

        self._place(m, getattr(e, 'x_root', self.root.winfo_x()),
                    getattr(e, 'y_root', self.root.winfo_y()))
        round_corners(m)

        m.bind('<Escape>', self._close_menu)
        try:
            m.focus_force()
        except Exception:
            pass

        def _arm(_w=m):
            if _w is getattr(self, '_menu_win', None) and _w.winfo_exists():
                _w.bind('<FocusOut>', self._close_menu)
        self.root.after(250, _arm)
        return 'break'

    # ---- piezas comunes de las ventanas --------------------------------
    def _ventana(self, titulo, ancho):
        """Ventana sin marco de Windows, con el mismo lenguaje que el menu.

        Las de antes usaban la barra de titulo del sistema y los controles
        por defecto de Tk, que no se parecen en nada al resto del widget.
        """
        w = tk.Toplevel(self.root)
        w.overrideredirect(True)
        w.attributes('-topmost', True)
        w.configure(bg=MENU_BD)
        cuerpo = tk.Frame(w, bg=MENU_BG)
        cuerpo.pack(fill='both', expand=True, padx=1, pady=1)

        cab = tk.Frame(cuerpo, bg=MENU_BG)
        cab.pack(fill='x', padx=(px(14), px(10)), pady=(px(10), px(2)))
        tk.Label(cab, text=titulo, bg=MENU_BG, fg=MENU_FG,
                 font=('Segoe UI', -px(13), 'bold')).pack(side='left')
        cerrar = tk.Label(cab, text='\u2715', bg=MENU_BG, fg=MENU_MUTED,
                          font=('Segoe UI', -px(12)), cursor='hand2')
        cerrar.pack(side='right')
        cerrar.bind('<Button-1>', lambda e: w.destroy())
        cerrar.bind('<Enter>', lambda e: cerrar.configure(fg=CLOSE_HOV))
        cerrar.bind('<Leave>', lambda e: cerrar.configure(fg=MENU_MUTED))

        # se puede arrastrar por la cabecera, ya que no hay barra de titulo
        def baja(ev):
            w._ox, w._oy = ev.x_root - w.winfo_x(), ev.y_root - w.winfo_y()

        def mueve(ev):
            w.geometry(f'+{ev.x_root - w._ox}+{ev.y_root - w._oy}')
        for z in (cab,) + tuple(cab.winfo_children()[:1]):
            z.bind('<Button-1>', baja)
            z.bind('<B1-Motion>', mueve)

        w.bind('<Escape>', lambda e: w.destroy())
        w._cuerpo = cuerpo
        w._ancho = ancho
        return w

    def _boton(self, parent, texto, cmd, primario=False):
        b = tk.Label(parent, text=texto, cursor='hand2',
                     bg=(MENU_ACCENT if primario else MENU_HOVER),
                     fg=(TEXT_ON_FILL if primario else MENU_FG),
                     font=('Segoe UI', -px(12), 'bold' if primario else 'normal'),
                     padx=px(16), pady=px(7))
        b.bind('<Button-1>', lambda e: cmd())
        if not primario:
            b.bind('<Enter>', lambda e: b.configure(bg=MENU_SEP))
            b.bind('<Leave>', lambda e: b.configure(bg=MENU_HOVER))
        return b

    # ---- tamano ---------------------------------------------------------
    def _set_scale(self, factor, save=True):
        self.user_scale = max(0.7, min(2.0, float(factor)))
        self._relayout()
        if save:
            val = round(self.user_scale, 3)

            def _persist():
                cfg = load_cfg()
                cfg['scale'] = val
                save_cfg(cfg, durable=False)
            threading.Thread(target=_persist, daemon=True).start()

    def _relayout(self):
        """Recalcula geometria, fuentes y render tras cambiar el tamano."""
        # el panel desplegado se queda con el tamano y el sitio de antes
        self._panel_ocultar()
        apply_scale(self.dpi / 96.0 * self.user_scale)

        self.f_pct.config(size=-px(13))
        self.f_sub.config(size=-px(13))
        self.f_msg.config(size=-px(11))
        self.f_pnum.config(size=-px(18))
        self.f_ptit.config(size=-px(11))
        self.f_pcd.config(size=-px(11))
        self.f_icon.config(size=-px(14))

        cy = H // 2
        self._geometria_barra()

        self.cv.config(width=W, height=H)
        x, y = self.root.winfo_x(), self.root.winfo_y()
        try:                                  # no dejarlo fuera de pantalla
            sw = self.root.winfo_screenwidth()
            x = min(x, sw - W - 8)
        except Exception:
            pass
        self.root.geometry(f'{W}x{H}+{max(0, x)}+{max(0, y)}')

        self.cv.coords(self.id_close, W - PAD, cy)
        self._render_all()

    def _size_dialog(self, e=None):
        dlg = getattr(self, '_szdlg', None)
        if dlg is not None and dlg.winfo_exists():
            dlg.lift(); dlg.focus_force(); return
        ancho = px(260)
        w = self._ventana('Tamaño', ancho)
        self._szdlg = w
        cuerpo = w._cuerpo

        valor = tk.Label(cuerpo, text=f'{int(round(self.user_scale * 100))} %',
                         bg=MENU_BG, fg=MENU_ACCENT,
                         font=('Segoe UI', -px(30), 'bold'))
        valor.pack(pady=(px(6), px(2)))

        # deslizador dibujado a mano: el de Tk trae su propio aspecto y
        # rompia la coherencia con el resto
        cw, ch = ancho - px(36), px(30)
        lienzo = tk.Canvas(cuerpo, width=cw, height=ch, bg=MENU_BG,
                           highlightthickness=0, bd=0, cursor='hand2')
        lienzo.pack(padx=px(18), pady=(0, px(2)))
        MIN, MAX = 70, 200
        r = px(7)

        def pinta():
            v = int(round(self.user_scale * 100))
            lienzo.delete('all')
            cy = ch // 2
            grueso = px(6)
            # El canal va en el color del carril del widget, no en el de los
            # separadores del menu: aquel apenas se distingue del fondo del
            # dialogo y el deslizador parecia cortado a media altura.
            lienzo.create_line(r, cy, cw - r, cy, fill=TRACK,
                               width=grueso, capstyle='round')
            t = (v - MIN) / (MAX - MIN)
            x = r + t * (cw - 2 * r)
            if x > r + 1:
                lienzo.create_line(r, cy, x, cy, fill=MENU_ACCENT,
                                   width=grueso, capstyle='round')
            # tirador: aro del color del dialogo para separarlo del canal
            lienzo.create_oval(x - r - px(2), cy - r - px(2),
                               x + r + px(2), cy + r + px(2),
                               fill=MENU_BG, outline='')
            lienzo.create_oval(x - r, cy - r, x + r, cy + r,
                               fill=MENU_ACCENT, outline='')
            valor.config(text=f'{v} %')

        def mueve(ev):
            t = min(1.0, max(0.0, (ev.x - r) / max(1, cw - 2 * r)))
            v = int(round((MIN + t * (MAX - MIN)) / 5.0)) * 5
            if v != int(round(self.user_scale * 100)):
                self._set_scale(v / 100.0, save=False)
            pinta()

        lienzo.bind('<Button-1>', mueve)
        lienzo.bind('<B1-Motion>', mueve)
        pinta()

        ext = tk.Frame(cuerpo, bg=MENU_BG)
        ext.pack(fill='x', padx=px(18))
        tk.Label(ext, text='70 %', bg=MENU_BG, fg=MENU_MUTED,
                 font=('Segoe UI', -px(10))).pack(side='left')
        tk.Label(ext, text='200 %', bg=MENU_BG, fg=MENU_MUTED,
                 font=('Segoe UI', -px(10))).pack(side='right')

        def guardar():
            val = round(self.user_scale, 3)

            def _persist():
                cfg = load_cfg()
                cfg['scale'] = val
                save_cfg(cfg, durable=False)
            threading.Thread(target=_persist, daemon=True).start()

        def hecho():
            guardar()
            self._szdlg = None
            w.destroy()

        def restablecer():
            self._set_scale(1.0, save=False)
            pinta()

        bf = tk.Frame(cuerpo, bg=MENU_BG)
        bf.pack(pady=(px(14), px(14)))
        self._boton(bf, 'Restablecer', restablecer).pack(side='left', padx=px(5))
        self._boton(bf, 'Hecho', hecho, primario=True).pack(side='left', padx=px(5))
        w.protocol('WM_DELETE_WINDOW', hecho)
        self._place(w, self.root.winfo_x(), self.root.winfo_y() - px(200))
        round_corners(w)
        w.focus_force()

    def _set_accent(self, nombre):
        apply_accent(nombre)
        self.cv.itemconfig(self.id_close, fill=BTN)
        self._repintar_ventanas()
        self._render_all()
        self.root.update_idletasks()

        def _persist():
            cfg = load_cfg()
            cfg['accent'] = nombre
            save_cfg(cfg, durable=False)
        threading.Thread(target=_persist, daemon=True).start()

    def _repintar_ventanas(self):
        """Tras cambiar tema o color, las ventanas abiertas siguen con la
        paleta vieja. El panel se cierra (se redibuja solo al volver a pasar
        el raton) y el dialogo de tamano se vuelve a abrir con los colores
        nuevos, conservando el valor."""
        self._panel_ocultar()
        sz = getattr(self, '_szdlg', None)
        if sz is not None and sz.winfo_exists():
            self._szdlg = None
            sz.destroy()
            self.root.after(1, self._size_dialog)

    def _set_theme(self, name):
        # 1) repintar YA, sin tocar el disco
        apply_theme(name)
        self.root.attributes('-alpha', ALPHA)
        self.root.configure(bg=TINT)
        self.cv.configure(bg=TINT)
        self._bg = TINT
        self.cv.itemconfig(self.id_close, fill=BTN)
        # rehacer el hook para que el color de hover sea el del tema nuevo
        self._hook(self.id_close, CLOSE_HOV, self.close)
        self._repintar_ventanas()
        # el menu se dibuja al abrirlo, asi que no hay nada que reconstruir
        self._render_all()
        self.root.update_idletasks()

        # 2) y ahora, ya con el widget repintado, persistir en segundo plano
        def _persist():
            cfg = load_cfg()
            cfg['theme'] = name
            save_cfg(cfg, durable=False)
        threading.Thread(target=_persist, daemon=True).start()

    # ---- rendering ----------------------------------------------------
    def _render_all(self):
        if HAVE_PIL:
            self.cv.itemconfig(self._shape_id, image=self._render_shapes(self.pct))
        else:
            self._draw_bar(self.pct or 0)
            self.cv.delete('pctfb')
            txt = self.status_msg or (f'{self.pct}%' if self.pct is not None else '--')
            self.cv.create_text((self.bar_x0 + self.bar_x1) / 2, H // 2,
                                text=txt, anchor='center', fill=INK,
                                font=self.f_pct, tags='pctfb')
        self._draw_labels()

    SS = 4                           # supersampling para bordes suaves

    def _base_img(self):
        """Fondo estatico (tarjeta + carril vacio) cacheado.

        Solo cambia con el tema, el color o el tamano, no con el porcentaje,
        asi que se dibuja una vez y cada repintado parte de una copia.
        """
        key = (THEME, ACCENT_NAME, W, H, self.bar_x0, self.bar_x1,
               self.bar_y, self.bar_h)
        cache = getattr(self, '_base_cache', None)
        if cache is None:
            cache = self._base_cache = {}
        hit = cache.get(key)
        if hit is not None:
            return hit
        SS = self.SS
        iw, ih = W * SS, H * SS
        img = Image.new('RGBA', (iw, ih), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        # Un solo borde: antes la tarjeta se dibujaba metida un pixel y con
        # contorno propio, asi que junto al canto de la ventana parecian dos
        # marcos concentricos.
        d.rounded_rectangle([0, 0, iw - 1, ih - 1], radius=px(12) * SS,
                            fill=TINT,
                            outline=(CARD_BD if CARD_BD != TINT else None),
                            width=(SS if CARD_BD != TINT else 0))
        x0, x1 = self.bar_x0 * SS, self.bar_x1 * SS
        y0, y1 = self.bar_y * SS, (self.bar_y + self.bar_h) * SS
        rr = (y1 - y0) // 2
        d.rounded_rectangle([x0, y0, x1, y1], radius=rr,
                            fill=TRACK, outline=TRACK_SH, width=SS)
        d.line([(x0 + rr, y0 + SS), (x1 - rr, y0 + SS)],
               fill=TRACK_SH, width=SS)
        if len(cache) > 8:
            cache.clear()
        cache[key] = img
        return img

    @staticmethod
    def _grad_strip(c1, c2):
        """Tira de degradado 256x1, cacheada: interpolar y escalar es mucho
        mas rapido que pintar cientos de lineas verticales."""
        key = (c1, c2)
        hit = Glass._GRAD_CACHE.get(key)
        if hit is not None:
            return hit
        strip = Image.new('RGB', (256, 1))
        pxl = strip.load()
        a, b = _hex(c1), _hex(c2)
        for i in range(256):
            t = i / 255.0
            pxl[i, 0] = tuple(int(round(a[j] + (b[j] - a[j]) * t)) for j in range(3))
        Glass._GRAD_CACHE[key] = strip
        return strip

    _GRAD_CACHE = {}

    def _render_shapes(self, pct):
        SS = self.SS
        img = self._base_img().copy()
        x0 = self.bar_x0 * SS
        y0, y1 = self.bar_y * SS, (self.bar_y + self.bar_h) * SS
        rr = (y1 - y0) // 2
        # Tambien al 100 % se usa el color elegido: antes el modo dormido
        # forzaba un verde fijo e ignoraba el acento del menu. El estado ya
        # lo dicen el rotulo 'Claude duerme' y el reloj de la cuenta atras.
        cs, ce = BAR_START, BAR_END
        fw = x0
        # relleno con degradado, recortado a pastilla redondeada
        if pct and pct > 0:
            fwf = self._fin_relleno(pct)
            fw = int(round(fwf * SS))
            w = max(1, fw - x0)
            h = y1 - y0
            grad = self._grad_strip(cs, ce).resize((w, h), Image.BILINEAR)
            mask = Image.new('L', (w, h), 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1],
                                                   radius=min(rr, w // 2),
                                                   fill=255)
            # Recortado ademas con la forma del CARRIL: con poco porcentaje el
            # relleno es una media luna pegada a la curva izquierda, en vez de
            # una bola del alto de la barra que aparentaba un 10 %.
            carril = Image.new('L', (w, h), 0)
            ImageDraw.Draw(carril).rounded_rectangle(
                [0, 0, self.bar_x1 * SS - x0 - 1, h - 1], radius=rr, fill=255)
            mask = ImageChops.multiply(mask, carril)
            img.paste(grad, (x0, y0), mask)

        # Punto de aviso al final del carril: algun limite semanal o de un
        # modelo esta agotado aunque la sesion de 5 h vaya bien. Sin el, solo
        # te enterabas pasando el raton por encima. No se pinta si la propia
        # sesion esta dormida: ahi la barra ya lo dice todo.
        if self._limite_agotado() and not (pct is not None and pct >= 100):
            d = ImageDraw.Draw(img)
            r = px(3) * SS
            aro = max(2, SS * 3 // 2)
            cx, cy = self.bar_x1 * SS - rr, (y0 + y1) // 2
            d.ellipse([cx - r - aro, cy - r - aro, cx + r + aro, cy + r + aro],
                      fill=TRACK)
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=CLOSE_HOV)

        out = img.resize((W, H), Image.LANCZOS)
        self._shape_img = ImageTk.PhotoImage(out)
        return self._shape_img

    def _hook(self, item, hov, cmd):
        c = self.cv
        c.tag_unbind(item, '<Enter>')
        c.tag_unbind(item, '<Leave>')
        c.tag_unbind(item, '<Button-1>')
        c.tag_bind(item, '<Enter>', lambda e: c.itemconfig(item, fill=hov))
        c.tag_bind(item, '<Leave>', lambda e: c.itemconfig(item, fill=BTN))
        c.tag_bind(item, '<Button-1>', cmd)
        c.tag_bind(item, '<Enter>', lambda e: c.config(cursor='hand2'), add='+')
        c.tag_bind(item, '<Leave>', lambda e: c.config(cursor=''), add='+')

    def _pill(self, x0, y0, x1, y1, color, tag):
        r = (y1 - y0) / 2
        if x1 - x0 < 2 * r:
            x1 = x0 + 2 * r
        c = self.cv
        c.create_oval(x0, y0, x0 + 2 * r, y1, fill=color, outline=color, tags=tag)
        c.create_oval(x1 - 2 * r, y0, x1, y1, fill=color, outline=color, tags=tag)
        c.create_rectangle(x0 + r, y0, x1 - r, y1, fill=color, outline=color, tags=tag)

    def _draw_bar(self, pct, col=None):
        """Fallback sin Pillow."""
        c = self.cv
        c.delete('bar')
        x0, x1 = self.bar_x0, self.bar_x1
        y0, y1 = self.bar_y, self.bar_y + self.bar_h
        cy = (y0 + y1) / 2.0
        r = self.bar_h / 2.0
        self._pill(x0, y0, x1, y1, TRACK_SH, 'bar')
        self._pill(x0 + 1, y0 + 1, x1 - 1, y1 - 1, TRACK, 'bar')
        c.create_line(x0 + r, y0 + 2, x1 - r, y0 + 2, fill=TRACK_SH, tags='bar')
        if pct and pct > 0:
            fw = self._fin_relleno(pct)
            span = fw - x0
            x = int(x0)
            end = int(round(fw))
            while x <= end:
                if x < x0 + r:
                    dx = (x0 + r) - x
                elif x > fw - r:
                    dx = x - (fw - r)
                else:
                    dx = 0.0
                if dx <= r:
                    hh = (r * r - dx * dx) ** 0.5
                    t = min(1.0, max(0.0, (x - x0) / span))
                    c.create_line(x, cy - hh, x, cy + hh + 1,
                                  fill=_mix(BAR_START, BAR_END, t), tags='bar')
                x += 1
        c.tag_lower('card')

    @staticmethod
    def _dy_optico(fuente):
        """Correccion de centrado vertical, medida.

        Tk centra por la caja de la linea (ascendente + descendente). Lo que
        se ve de una cifra va del alto de mayuscula a la linea base, asi que
        el centro optico es:   base - altura_mayuscula / 2.
        Restando donde cae la base en la caja de Tk sale el desplazamiento.
        Con Segoe UI da practicamente cero; la formula lo mantiene correcto
        si cambia la fuente o el tamano.
        """
        try:
            a = fuente.metrics('ascent')
            d = fuente.metrics('descent')
            em = abs(fuente.cget('size'))
            mayuscula = em * 0.70              # altura de mayuscula tipica
            return int(round(mayuscula / 2.0 - (a - d) / 2.0))
        except Exception:
            return 0

    # todos los formatos que puede mostrar la cuenta atras
    CD_MUESTRAS = ('0:00:00', '22h 59m', '7d 23h', 'clic dcho')

    def _geometria_barra(self):
        """La barra ocupa TODO lo que sobra.

        Se reserva para la cuenta atras el ancho de TODOS sus casos posibles,
        no solo el del reloj: asi la barra no cambia de longitud cada vez que
        pasa un minuto y, sobre todo, el texto nunca se queda sin sitio.

        Antes solo se medía '0:00:00' y resulta que '22h 59m' es MAS ancho
        (los dos puntos ocupan la mitad que un digito). Al no caber, el
        contador se dibujaba con la fuente de emergencia, mas pequeña todavia
        que la original: por eso subir el tamaño no cambiaba nada en pantalla.
        """
        hueco_x = px(18)                       # zona del icono de cerrar
        try:
            reserva = max(self.f_sub.measure(s) for s in self.CD_MUESTRAS)
        except Exception:
            reserva = px(62)
        self.cd_der = W - PAD - hueco_x        # el contador acaba aqui
        self.bar_x0 = PAD
        self.bar_x1 = max(PAD + px(60), self.cd_der - reserva - px(10))
        self.bar_h = px(20)
        self.bar_y = H // 2 - self.bar_h // 2
        self.cd_x = self.bar_x1 + px(10)

    ROT_PAD = 12                     # aire a cada lado del rotulo, en px logicos

    def _rotulo(self):
        """(texto, fuente) del rotulo que va dentro de la barra."""
        if self.status_msg:
            return self.status_msg, self.f_msg
        if self.pct is not None and self.pct >= 100:
            texto = mensaje_dormido(self.reset_iso)
            # si en algun tamano no cabe entero en la barra, el de siempre
            try:
                hueco = (self.bar_x1 - self.bar_x0) - 2 * px(self.ROT_PAD)
                if self.f_msg.measure(texto) > hueco:
                    texto = MENSAJE_DORMIDO
            except Exception:
                texto = MENSAJE_DORMIDO
            return texto, self.f_msg
        if self.pct is not None:
            return f'{self.pct}%', self.f_pct
        return '--', self.f_pct

    def _fin_relleno(self, pct):
        """Donde acaba el color: el porcentaje REAL, sin inflar.

        Antes se estiraba hasta que cupiera el rotulo, y un 5 % ocupaba como
        un 25 %. Ahora el largo es fiel; el rotulo no depende de el porque se
        pinta en dos colores (ver _rotulo_sobre_relleno). Solo hay un minimo
        de unos pixeles para que un 1 % no sea invisible.
        """
        x0, x1 = self.bar_x0, self.bar_x1
        if not pct or pct <= 0:
            return float(x0)
        fin = x0 + (x1 - x0) * min(pct, 100) / 100.0
        return float(min(max(fin, x0 + px(4)), x1))

    def _texto_barra(self):
        """(texto, x, color, fuente) del rotulo de la barra.

        Siempre en el mismo sitio, al principio del carril. Esta es la capa
        de ABAJO, en el color del carril; la parte que queda sobre el relleno
        la tapa una copia en el color del relleno (_rotulo_sobre_relleno).
        """
        texto, fuente = self._rotulo()
        return texto, self.bar_x0 + px(self.ROT_PAD), INK, fuente

    def _rotulo_sobre_relleno(self, texto, tx, cy, fuente):
        """Copia del rotulo en TEXT_ON_FILL, recortada exactamente al relleno.

        El canvas de tkinter no sabe recortar un texto, pero un canvas hijo
        si: se coloca justo encima del tramo relleno, muestra la misma imagen
        de fondo desplazada y encima el rotulo en blanco. Lo que asoma fuera
        del relleno es la capa de abajo. Resultado: la cifra cambia de color
        justo en el borde, como en las barras de progreso de Windows y macOS,
        y el relleno puede medir lo que de verdad mide.
        """
        c = self.cv
        x0 = self.bar_x0
        fin = self._fin_relleno(self.pct) if (self.pct and self.pct > 0) else x0
        ancho = int(round(fin)) - x0
        img = getattr(self, '_shape_img', None)
        sub = getattr(self, '_cv_fill', None)
        if not (HAVE_PIL and img is not None and ancho > 0 and fin > tx):
            if sub is not None:
                c.itemconfig(self._cv_fill_id, state='hidden')
            return
        if sub is None:
            sub = self._cv_fill = tk.Canvas(c, highlightthickness=0, bd=0,
                                            bg=TINT, cursor='')
            self._cv_fill_id = c.create_window(0, 0, anchor='nw', window=sub)
        c.coords(self._cv_fill_id, x0, self.bar_y)
        c.itemconfig(self._cv_fill_id, width=ancho, height=self.bar_h,
                     state='normal')
        sub.delete('all')
        sub.create_image(-x0, -self.bar_y, image=img, anchor='nw')
        sub.create_text(tx - x0, cy - self.bar_y, text=texto, anchor='w',
                        fill=TEXT_ON_FILL, font=fuente)

    def _draw_labels(self):
        c = self.cv
        c.delete('lbl')
        texto, tx, col, fuente = self._texto_barra()
        cy = H // 2 + self._dy_optico(fuente)
        c.create_text(tx, cy, text=texto, anchor='w', fill=col, font=fuente,
                      tags='lbl')
        self._rotulo_sobre_relleno(texto, tx, cy, fuente)
        if not self._cd:
            return
        # pegada a la X, alineada por la derecha. Sin fuente de emergencia:
        # el hueco ya se reserva para el caso mas ancho.
        fnt = self.f_sub
        c.create_text(self.cd_der, H // 2 + self._dy_optico(fnt),
                      text=self._cd, anchor='e',
                      fill=(LABEL if getattr(self, '_cargando', False) else TIME),
                      font=fnt, tags='lbl')

    # ---- datos --------------------------------------------------------
    def refresh(self):
        self._cargando = True
        self._draw_labels()          # el contador se atenua mientras consulta
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        try:
            pct, reset_iso, data = fetch_session()
            self.root.after(0, self._apply, pct, reset_iso, None, data)
        except NoKey:
            self.root.after(0, self._apply, None, None, 'nokey', None)
        except KeyExpired:
            self.root.after(0, self._apply, None, None, 'expired', None)
        except Exception:
            self.root.after(0, self._apply, None, None, 'offline', None)

    def _apply(self, pct, reset_iso, err, data=None):
        self._cargando = False
        if err:
            self.key_state = err
            self.pct = None
            self.reset_iso = None
            self.usage = {}
            if err == 'nokey':
                self.status_msg = 'Falta sessionKey'
                self._cd = 'clic dcho'
                # abrir el dialogo solo la primera vez, nunca en bucle
                if not self._auto_prompted:
                    self._auto_prompted = True
                    self.root.after(300, self._key_dialog)
            elif err == 'expired':
                self.status_msg = 'Clave caducada'
                self._cd = 'clic dcho'
            else:
                self.status_msg = 'Sin conexión'
                self._cd = ''
            self._render_all()
            return
        self.key_state = 'ok'
        self.status_msg = None
        self.usage = data or {}
        self.pct = pct
        self.reset_iso = reset_iso
        self._update_sub()
        self._panel_refrescar()

    def _update_sub(self):
        self._sleeping = self.pct is not None and self.pct >= 100
        if self.reset_iso:
            self._cd = (countdown_clock(self.reset_iso) if self._sleeping
                        else countdown(self.reset_iso))
        else:
            self._cd = ''
        self._render_all()
        if self.reset_iso and _reset_secs(self.reset_iso) <= 0:
            self.refresh()

    def _tick_clock(self):
        if self.pct is not None and self.pct >= 100:
            self._update_sub()
        self.root.after(1000, self._tick_clock)

    # ---- temporizadores ------------------------------------------------
    def _tick_topmost(self):
        try:
            self.root.attributes('-topmost', True)
            corregido = (asegurar_fuera_de_barra(self.root)
                         if self.root.winfo_ismapped() else None)
            if corregido is not None and not getattr(self, '_barra_avisado', False):
                # se apunta una vez, para saber que lo provoca
                self._barra_avisado = True
                log_error('BARRA DE TAREAS (no es un fallo, ya corregido)\n'
                          f'  la ventana habia perdido la marca: estilo {corregido:#x}')
            # el widget se reafirma encima cada 600 ms; el menu y los dialogos
            # abiertos tienen que subir con el, o quedarian tapados
            for attr in ('_menu_win', '_panel', '_dlg', '_szdlg', '_txtwin'):
                w = getattr(self, attr, None)
                if w is not None and w.winfo_exists():
                    w.lift()
                    w.attributes('-topmost', True)
        except Exception:
            pass
        self.root.after(TOPMOST_MS, self._tick_topmost)

    def _tick_countdown(self):
        if self.pct is not None:
            self._update_sub()
        self.root.after(30_000, self._tick_countdown)
        self._since = getattr(self, '_since', 0) + 30_000
        if self._since >= REFRESH_MS:
            self._since = 0
            self.refresh()

    # ---- arrastre + posicion -------------------------------------------
    def _bind_drag(self):
        for w in (self.cv, self.root):
            w.bind('<Button-1>', self._drag_start)
            w.bind('<B1-Motion>', self._drag_move)
            w.bind('<ButtonRelease-1>', self._drag_end)
            w.bind('<Button-3>', self._popup)      # clic dcho: menu
            w.bind('<Enter>', self._hover_programar_apertura)
            w.bind('<Leave>', self._hover_programar_cierre)

    # ---- dialogos ------------------------------------------------------
    def _toggle_autostart(self, e=None):
        activo = (autostart_estado() or '').lower() == _mi_ruta().lower()
        ok = autostart_activar(not activo)
        cfg = load_cfg()
        cfg['autostart'] = (not activo)
        save_cfg(cfg, durable=False)
        if not ok:
            self._text_window(
                f'{APP_NAME}  -  arranque',
                'No se ha podido escribir en el registro de Windows.\n\n'
                'Suele ser una restriccion del equipo. Alternativa manual:\n'
                '  1. Windows + R\n'
                '  2. escribe:  shell:startup\n'
                '  3. arrastra el .exe con el BOTON DERECHO y elige\n'
                '     "Crear iconos de acceso directo aqui"')

    def _info_dialog(self, e=None):
        lines = [f'{APP_NAME}  v{VERSION}   ·   tema: {THEME}   ·   '
                 f'DPI: {getattr(self, "dpi", 96):.0f}  (escala x{UI:.2f})   ·   '
                 f'ventana: {W}x{H}px',
                 f'Pillow: {"sí" if HAVE_PIL else "NO (render básico)"}',
                 '',
                 'Rutas de configuración (por orden):', '']
        for d in cfg_dirs():
            p = os.path.join(d, CFG_NAME)
            if os.path.exists(p):
                try:
                    has = bool(_read_json(p).get('session_key'))
                    mark = 'OK  (con clave)' if has else 'OK  (sin clave)'
                except Exception:
                    mark = 'ILEGIBLE / corrupto'
            else:
                mark = '(no existe)'
            lines.append(f'  {mark}\n     {p}')
        lines.append('')
        lines.append(f'Leído de: {LOADED_FROM or "(ninguno)"}')
        lines.append('')
        lines.append(f'Ejecutable: {_mi_ruta()}')
        reg = autostart_estado()
        if not reg:
            lines.append('Arranque con Windows: NO configurado')
        elif reg.lower() == _mi_ruta().lower():
            lines.append('Arranque con Windows: SÍ (registro HKCU\\...\\Run)')
        else:
            lines.append('Arranque con Windows: APUNTA A OTRO ARCHIVO ->')
            lines.append(f'   {reg}')
        if autostart_vetado():
            lines.append('   AVISO: Windows la tiene DESACTIVADA en')
            lines.append('   Administrador de tareas > Inicio de aplicaciones.')
        if SAVE_REPORT:
            lines.append('')
            lines.append('Último guardado:')
            for p, ok, why in SAVE_REPORT:
                lines.append(f'  {"OK " if ok else "FALLO"} {p}' +
                             (f'  -> {why}' if not ok else ''))
        self._text_window(f'{APP_NAME}  -  diagnóstico', '\n'.join(lines))

    def _text_window(self, title, body):
        previa = getattr(self, '_txtwin', None)
        if previa is not None and previa.winfo_exists():
            previa.destroy()
        w = self._ventana(title, px(560))
        self._txtwin = w
        cuerpo = w._cuerpo
        caja = tk.Frame(cuerpo, bg=MENU_HOVER)
        caja.pack(fill='both', expand=True, padx=px(14), pady=(px(8), 0))
        t = tk.Text(caja, width=78, height=17, bg=MENU_HOVER, fg=MENU_FG,
                    font=('Consolas', -px(11)), relief='flat', wrap='none',
                    bd=0, highlightthickness=0, padx=px(10), pady=px(8),
                    insertbackground=MENU_FG)
        t.pack(fill='both', expand=True)
        t.insert('1.0', body)
        t.config(state='disabled')
        bf = tk.Frame(cuerpo, bg=MENU_BG)
        bf.pack(pady=px(12))
        self._boton(bf, 'Cerrar', w.destroy, primario=True).pack()
        self._place(w, self.root.winfo_x() - px(260),
                    self.root.winfo_y() - px(320))
        round_corners(w)
        w.focus_force()

    def _key_dialog(self, e=None):
        if getattr(self, '_dlg', None) is not None and self._dlg.winfo_exists():
            self._dlg.lift(); self._dlg.focus_force(); return
        cfg = load_cfg()
        ancho = px(430)
        w = self._ventana('Conectar con Claude', ancho)
        self._dlg = w
        cuerpo = w._cuerpo
        w.protocol('WM_DELETE_WINDOW',
                   lambda: (setattr(self, '_dlg', None), w.destroy()))

        tk.Label(cuerpo, text='Pega aquí tu sessionKey de claude.ai',
                 bg=MENU_BG, fg=MENU_FG, font=('Segoe UI', -px(12)),
                 anchor='w').pack(fill='x', padx=px(14), pady=(px(6), 0))
        tk.Label(cuerpo,
                 text='En claude.ai: icono a la izquierda de la dirección  ›  '
                      'Cookies  ›  sessionKey',
                 bg=MENU_BG, fg=MENU_MUTED, font=('Segoe UI', -px(10)),
                 anchor='w', justify='left').pack(fill='x', padx=px(14),
                                                  pady=(px(2), px(10)))

        marco = tk.Frame(cuerpo, bg=MENU_HOVER)
        marco.pack(fill='x', padx=px(14))
        ent = tk.Entry(marco, show='\u2022', font=('Consolas', -px(12)),
                       bg=MENU_HOVER, fg=MENU_FG, relief='flat', bd=0,
                       highlightthickness=0, insertbackground=MENU_ACCENT)
        ent.pack(fill='x', padx=px(10), pady=px(9))
        ent.insert(0, cfg.get('session_key', ''))

        msg = tk.Label(cuerpo, text='', bg=MENU_BG, fg=CLOSE_HOV,
                       font=('Segoe UI', -px(10)), wraplength=ancho - px(30),
                       justify='left', anchor='w')
        msg.pack(fill='x', padx=px(14), pady=(px(6), 0))

        def conectar():
            val = clean_key(ent.get())
            if not key_looks_real(val):
                msg.config(text='Esa clave no parece válida: tiene que empezar '
                                'por "sk-ant-" y ser larga. Cópiala entera.')
                return
            c = load_cfg()
            c['session_key'] = val
            c['theme'] = THEME
            c.pop('org_id', None)
            if not save_cfg(c):
                msg.config(text='No se ha podido guardar en ninguna carpeta.\n'
                                + '\n'.join(f'{p}: {why}'
                                            for p, _o, why in SAVE_REPORT))
                return
            self._dlg = None
            w.destroy()
            self.status_msg = None
            self.refresh()

        bf = tk.Frame(cuerpo, bg=MENU_BG)
        bf.pack(pady=(px(14), px(14)))
        self._boton(bf, 'Cancelar',
                    lambda: (setattr(self, '_dlg', None),
                             w.destroy())).pack(side='left', padx=px(5))
        self._boton(bf, 'Conectar', conectar,
                    primario=True).pack(side='left', padx=px(5))
        w.bind('<Return>', lambda e: conectar())
        self._place(w, self.root.winfo_x(), self.root.winfo_y() - px(190))
        round_corners(w)
        w.focus_force()
        ent.focus_set()

    # ---- arrastre ------------------------------------------------------
    def _drag_start(self, e):
        self._arrastrando = False
        self._hover_cancelar()
        self._close_menu()          # si no, el menu se queda flotando atras
        self._ox = e.x_root - self.root.winfo_x()
        self._oy = e.y_root - self.root.winfo_y()

    def _drag_move(self, e):
        if not getattr(self, '_arrastrando', False):
            self._arrastrando = True
            self._panel_ocultar()       # no arrastrar el widget con el panel puesto
        self.root.geometry(f'+{e.x_root - self._ox}+{e.y_root - self._oy}')

    def _drag_end(self, e):
        self._arrastrando = False
        self._save_pos()

    @staticmethod
    def _escritorio_virtual():
        """Rectangulo que abarca TODAS las pantallas, tambien las de la izquierda
        (coordenadas negativas). Con una sola pantalla equivale a la de siempre."""
        try:
            import ctypes
            u = ctypes.windll.user32
            x = u.GetSystemMetrics(76)          # SM_XVIRTUALSCREEN
            y = u.GetSystemMetrics(77)          # SM_YVIRTUALSCREEN
            w = u.GetSystemMetrics(78)          # SM_CXVIRTUALSCREEN
            h = u.GetSystemMetrics(79)          # SM_CYVIRTUALSCREEN
            if w > 0 and h > 0:
                return x, y, x + w, y + h
        except Exception:
            pass
        return None

    MAX_CONFIGS = 8               # configuraciones de pantallas recordadas

    @staticmethod
    def _pos_guardadas():
        p = pos_path_for_read()
        if not p:
            return {}
        try:
            with open(p, encoding='utf-8') as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _xy(v):
        try:
            return int(v[0]), int(v[1])
        except Exception:
            return None

    def _pos_para(self, firma):
        """Posicion recordada para esa configuracion de pantallas, o None."""
        por = self._pos_guardadas().get('por_pantallas')
        if isinstance(por, dict) and firma in por:
            return self._xy(por[firma])
        return None

    def _load_pos(self):
        try:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
        except Exception:
            sw, sh = 1280, 720
        # por defecto: arriba a la derecha de la pantalla PRINCIPAL
        wa = work_area(0, 0)
        default = ((wa[2] - W - 24, wa[1] + 24) if wa else (sw - W - 24, 24))
        mons = monitores()
        d = self._pos_guardadas()
        candidatas = []
        if mons:
            candidatas.append(self._pos_para(firma_monitores(mons)))
        candidatas.append(self._xy((d.get('x'), d.get('y'))))
        for c in candidatas:
            if c is None:
                continue
            x, y = c
            if mons:
                if se_ve(x, y, W, H, mons):
                    return x, y
            else:
                vl, vt, vr, vb = self._escritorio_virtual() or (0, 0, sw, sh)
                if (vl - W + 60) < x < (vr - 60) and (vt - 5) < y < (vb - 20):
                    return x, y
        return default

    def _recordar_pos(self, x, y, firma=None):
        """Guarda la posicion como la ultima y como la de esa configuracion."""
        d = self._pos_guardadas()
        por = d.get('por_pantallas')
        por = dict(por) if isinstance(por, dict) else {}
        if firma is None:
            firma = firma_monitores(monitores())
        if firma:
            por.pop(firma, None)                 # al final = la mas reciente
            por[firma] = [int(x), int(y)]
            while len(por) > self.MAX_CONFIGS:
                por.pop(next(iter(por)))
        save_pos_file({'x': int(x), 'y': int(y), 'por_pantallas': por})

    def _save_pos(self):
        x, y = self.root.winfo_x(), self.root.winfo_y()
        self._pos_actual = (x, y)
        self._recordar_pos(x, y)

    PANTALLAS_MS = 2000

    def _tick_pantallas(self):
        """Vigila enchufar/desenchufar pantallas.

        - Si cambia la configuracion: primero apunta donde estaba el widget
          en la configuracion anterior (aunque no lo hubieras arrastrado
          nunca), y luego lo lleva a donde lo tenias la ultima vez en la
          nueva. En tu mesa vuelve a su sitio del monitor externo; en el
          portatil, al suyo.
        - Si en cualquier momento queda fuera de todas las pantallas, lo
          mete en la mas cercana.
        """
        try:
            mons = monitores()
            if mons and not getattr(self, '_arrastrando', False):
                firma = firma_monitores(mons)
                x, y = self.root.winfo_x(), self.root.winfo_y()
                previa = getattr(self, '_firma', None)
                destino = None
                if previa is None:
                    self._firma = firma                  # primer vistazo
                elif firma != previa:
                    self._firma = firma
                    antes = getattr(self, '_pos_actual', None)
                    if antes:
                        self._recordar_pos(antes[0], antes[1], previa)
                    guardada = self._pos_para(firma)
                    if guardada and se_ve(guardada[0], guardada[1], W, H, mons):
                        destino = guardada
                if destino is None and not se_ve(x, y, W, H, mons):
                    destino = encajar(x, y, W, H)
                if destino and tuple(destino) != (x, y):
                    self._panel_ocultar()
                    self._close_menu()
                    self.root.geometry(f'+{destino[0]}+{destino[1]}')
                    x, y = destino
                if firma == self._firma and se_ve(x, y, W, H, mons):
                    self._pos_actual = (x, y)
        except Exception:
            pass
        self.root.after(self.PANTALLAS_MS, self._tick_pantallas)

    def close(self, e=None):
        self._panel_ocultar()
        self._save_pos()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    # 1) una sola copia viva: si ya hay otra, esta se retira sin ruido
    if ya_hay_una_instancia():
        return 0

    # 2) cerrar ejecutables de versiones anteriores (no respetan el mutex)
    try:
        cerradas = cerrar_versiones_antiguas()
    except Exception:
        cerradas = []

    # 3) quitar accesos directos de arranque antiguos: mientras existan,
    #    al iniciar sesion se abre tambien la version vieja
    try:
        borrados = limpiar_accesos_directos_viejos()
    except Exception:
        borrados = []

    # 4) arranque con Windows por registro, y autorreparado si el .exe
    #    ha cambiado de sitio desde la ultima vez
    try:
        cfg = load_cfg()
        if cfg.get('autostart', True):
            if (autostart_estado() or '').lower() != _mi_ruta().lower():
                autostart_activar(True)
            elif autostart_vetado():
                # la ruta era correcta pero Windows tenia la entrada
                # desactivada: por eso no se abria al encender
                autostart_quitar_veto()
    except Exception:
        pass

    if cerradas or borrados:
        log_error('LIMPIEZA AL ARRANCAR (no es un fallo)\n'
                  f'  procesos antiguos cerrados: {cerradas}\n'
                  f'  accesos directos borrados:  {borrados}')

    Glass().run()
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:
        import traceback
        log_error(traceback.format_exc())
        raise
