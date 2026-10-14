# -*- coding: utf-8 -*-
"""Configuracion del widget.

Persistencia robusta: la configuracion se busca y se guarda en varias
rutas (LOCALAPPDATA -> APPDATA -> carpeta del .exe -> perfil de usuario),
con escritura atomica y verificacion de relectura.

La sessionKey NO va en esos archivos: se guarda en la caja fuerte de
Windows (boveda.py). Solo si la caja fuerte fallara se queda en el
archivo, como en las versiones anteriores, para no dejar a nadie sin
widget.
"""

import os
import re
import sys
import json
import threading

from . import boveda
from .canal import PRUEBA, BOVEDA_CLAVE

CFG_NAME = 'config.json'
POS_NAME = 'glass-pos.json'


# ─── Rutas de configuracion (cascada con respaldo) ──────────────────────
def _exe_dir():
    """Carpeta del .exe (o del .pyw en desarrollo)."""
    try:
        if getattr(sys, 'frozen', False):
            return os.path.dirname(os.path.abspath(sys.executable))
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    except Exception:
        return os.getcwd()


def _sin_duplicados(rutas):
    out, seen = [], set()
    for p in rutas:
        if not p:
            continue
        try:
            p = os.path.abspath(p)
        except Exception:
            continue
        k = p.lower()
        if k not in seen:
            seen.add(k)
            out.append(p)
    return out


def cfg_dirs_normal():
    """Rutas de la version normal, por orden de preferencia."""
    la = os.environ.get('LOCALAPPDATA')
    ra = os.environ.get('APPDATA')
    return _sin_duplicados([
        la and os.path.join(la, 'Claude Usage'),
        ra and os.path.join(ra, 'ClaudeGlass'),
        # la carpeta del .exe normal (desde la copia de prueba, la de
        # instalacion de siempre, que es donde vive el .exe normal)
        (la and os.path.join(la, 'ClaudeGlass')) if PRUEBA else _exe_dir(),
        os.path.join(os.path.expanduser('~'), '.claudeglass'),
    ])


def cfg_dirs():
    """Rutas candidatas de ESTE canal. La copia de prueba tiene las suyas
    y nunca escribe en las de la version normal."""
    if not PRUEBA:
        return cfg_dirs_normal()
    la = os.environ.get('LOCALAPPDATA')
    ra = os.environ.get('APPDATA')
    return _sin_duplicados([
        la and os.path.join(la, 'ClaudeGlass PRUEBA', 'datos'),
        ra and os.path.join(ra, 'ClaudeGlass PRUEBA'),
    ])


# Estado del ultimo guardado: lista de (ruta, ok, motivo)
SAVE_REPORT = []
LOADED_FROM = None
# Donde esta la sessionKey: 'boveda', 'archivo' o None
CLAVE_EN = None
# Si la caja fuerte falla una vez, no se reintenta en cada lectura
_BOVEDA_FALLA = False


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


def _leer_cascada(dirs):
    """(ruta, datos) de la primera config valida; prioriza la que tenga
    session_key, por si quedara alguna de una version anterior."""
    first_ok = None
    for d in dirs:
        p = os.path.join(d, CFG_NAME)
        try:
            data = _read_json(p)
        except Exception:
            continue
        if data.get('session_key'):
            return p, data
        if first_ok is None:
            first_ok = (p, data)
    return first_ok or (None, {})


def load_cfg():
    """Lee la config y le anade la sessionKey de la caja fuerte.

    Si encuentra una clave en texto plano (de una version anterior) la
    mueve a la caja fuerte y la borra de los archivos.
    """
    global LOADED_FROM, CLAVE_EN
    LOADED_FROM, data = _leer_cascada(cfg_dirs())
    data = dict(data)
    en_boveda = boveda.leer(BOVEDA_CLAVE)
    en_archivo = data.get('session_key')
    if en_archivo and en_archivo != en_boveda and not _BOVEDA_FALLA:
        # migracion: save_cfg la manda a la caja fuerte y limpia los archivos
        save_cfg(data)
        en_boveda = boveda.leer(BOVEDA_CLAVE)
    if en_boveda:
        data['session_key'] = en_boveda
        CLAVE_EN = 'boveda'
    elif data.get('session_key'):
        CLAVE_EN = 'archivo'
    else:
        CLAVE_EN = None
    return data


_SAVE_LOCK = threading.Lock()


def save_cfg(cfg, durable=True):
    """Guarda en TODAS las rutas escribibles. Devuelve True si alguna fue bien.

    La sessionKey va a la caja fuerte; los archivos se escriben sin ella.
    Si la caja fuerte falla, se queda en el archivo como antes.
    """
    global SAVE_REPORT, _BOVEDA_FALLA
    with _SAVE_LOCK:
        datos = dict(cfg)
        clave = datos.pop('session_key', None)
        if clave and not boveda.guardar(BOVEDA_CLAVE, clave):
            _BOVEDA_FALLA = True
            datos['session_key'] = clave          # plan B: en el archivo
        report = []
        ok_any = False
        for d in cfg_dirs():
            p = os.path.join(d, CFG_NAME)
            try:
                _atomic_write(p, datos, durable=durable)
                report.append((p, True, ''))
                ok_any = True
            except Exception as e:
                report.append((p, False, str(e)[:80]))
        SAVE_REPORT = report
        return ok_any


AJUSTES_IMPORTABLES = ('theme', 'accent', 'scale', 'org_id', 'orgs',
                       'size_normalizado_v31')


def importar_de_version_normal():
    """Solo en la copia de prueba, la primera vez: copia los ajustes y la
    sessionKey de la version normal para no tener que configurar nada.

    Lee las rutas de la version normal pero NO escribe en ellas.
    """
    if not PRUEBA:
        return False
    if _leer_cascada(cfg_dirs())[0] is not None:
        return False                              # ya tiene la suya
    _ruta, viejo = _leer_cascada(cfg_dirs_normal())
    nuevo = {k: viejo[k] for k in AJUSTES_IMPORTABLES if k in viejo}
    clave = (boveda.leer('ClaudeGlass by Flecha/sessionKey')
             or viejo.get('session_key'))
    if clave:
        nuevo['session_key'] = clave
    return save_cfg(nuevo)


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
