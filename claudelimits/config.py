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
        # verificacion de relectura: el archivo dice exactamente lo guardado
        if _read_json(path) != json.loads(json.dumps(obj)):
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


# ─── Cuentas ────────────────────────────────────────────────────────────
# Se pueden guardar varias cuentas de Claude y elegir cual se muestra. En
# el archivo va la lista (nombre, correo, organizacion) y cual esta activa;
# la clave de cada una va a la caja fuerte con su propio nombre.
#
# Para el resto del widget nada cambia: load_cfg() devuelve la cuenta activa
# "aplanada" (session_key, org_id, orgs en el primer nivel, como siempre) y
# save_cfg() los vuelve a meter en su cuenta.
CAMPOS_DE_CUENTA = ('session_key', 'org_id', 'orgs')


def _boveda_de(cid):
    return f'{BOVEDA_CLAVE}/{cid}'


def _nuevo_id():
    import uuid
    return uuid.uuid4().hex[:12]


def _activa(datos):
    cuentas = datos.get('cuentas') or []
    for c in cuentas:
        if c.get('id') == datos.get('cuenta_activa'):
            return c
    return cuentas[0] if cuentas else None


def load_cfg():
    """Lee la config y le anade los datos de la cuenta activa.

    Si viene de una version con una sola cuenta (o con la clave en texto
    plano) la pasa al formato nuevo y la clave a la caja fuerte.
    """
    global LOADED_FROM, CLAVE_EN
    LOADED_FROM, data = _leer_cascada(cfg_dirs())
    data = dict(data)
    if not isinstance(data.get('cuentas'), list):
        data['cuentas'] = []
        clave = data.get('session_key') or boveda.leer(BOVEDA_CLAVE)
        if clave:
            data['session_key'] = clave
            if save_cfg(data) and not _BOVEDA_FALLA:
                boveda.borrar(BOVEDA_CLAVE)       # la de la 3.2 sin cuentas
            LOADED_FROM, data = _leer_cascada(cfg_dirs())
            data = dict(data)
    data['cuentas'] = [dict(c) for c in data.get('cuentas') or []
                       if isinstance(c, dict) and c.get('id')]
    activa = _activa(data)
    CLAVE_EN = None
    if activa is not None:
        data['cuenta_activa'] = activa['id']
        clave = boveda.leer(_boveda_de(activa['id']))
        CLAVE_EN = 'boveda' if clave else None
        if not clave and activa.get('session_key'):
            clave, CLAVE_EN = activa['session_key'], 'archivo'
        if clave:
            data['session_key'] = clave
        for k in ('org_id', 'orgs'):
            if activa.get(k):
                data[k] = activa[k]
    return data


_SAVE_LOCK = threading.Lock()


def save_cfg(cfg, durable=True):
    """Guarda en TODAS las rutas escribibles. Devuelve True si alguna fue bien.

    Los datos de la cuenta activa vuelven a su sitio en la lista. La clave
    va a la caja fuerte; si fallara, se queda en el archivo como antes.
    Un campo de cuenta ausente no se toca; presente y vacio, se borra.
    """
    global SAVE_REPORT, _BOVEDA_FALLA
    with _SAVE_LOCK:
        datos = dict(cfg)
        cuenta = {k: datos.pop(k) for k in CAMPOS_DE_CUENTA if k in datos}
        cuentas = [dict(c) for c in datos.get('cuentas') or []
                   if isinstance(c, dict) and c.get('id')]
        datos['cuentas'] = cuentas
        activa = _activa(datos)
        if activa is None and cuenta.get('session_key'):
            activa = {'id': 'principal'}
            cuentas.append(activa)
        if activa is not None:
            datos['cuenta_activa'] = activa['id']
            for k in ('org_id', 'orgs'):
                if k in cuenta:
                    if cuenta[k]:
                        activa[k] = cuenta[k]
                    else:
                        activa.pop(k, None)
            clave = cuenta.get('session_key')
            if clave:
                activa.pop('session_key', None)
                if not boveda.guardar(_boveda_de(activa['id']), clave):
                    _BOVEDA_FALLA = True
                    activa['session_key'] = clave     # plan B: en el archivo
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


def _sin_cuenta_aplanada(cfg):
    for k in CAMPOS_DE_CUENTA:
        cfg.pop(k, None)
    return cfg


def anadir_cuenta(clave, nombre=None, email=None):
    """Guarda una cuenta nueva (o renueva la clave de una que ya estaba, si
    coincide el correo) y la deja activa."""
    cfg = _sin_cuenta_aplanada(load_cfg())
    cuenta = None
    if email:
        cuenta = next((c for c in cfg['cuentas']
                       if (c.get('email') or '').lower() == email.lower()), None)
    if cuenta is None:
        cuenta = {'id': _nuevo_id()}
        cfg['cuentas'].append(cuenta)
    if nombre:
        cuenta['nombre'] = nombre
    if email:
        cuenta['email'] = email
    cfg['cuenta_activa'] = cuenta['id']
    cfg['session_key'] = clave
    if cuenta.get('org_id') is None:
        cfg['org_id'] = None                    # que se elija de nuevo
    return save_cfg(cfg)


def activar_cuenta(cid):
    cfg = _sin_cuenta_aplanada(load_cfg())
    if any(c['id'] == cid for c in cfg['cuentas']):
        cfg['cuenta_activa'] = cid
        return save_cfg(cfg)
    return False


def quitar_cuenta(cid):
    """Olvida una cuenta: la quita de la lista y borra su clave."""
    cfg = _sin_cuenta_aplanada(load_cfg())
    cfg['cuentas'] = [c for c in cfg['cuentas'] if c['id'] != cid]
    boveda.borrar(_boveda_de(cid))
    if cfg.get('cuenta_activa') == cid:
        cfg['cuenta_activa'] = (cfg['cuentas'][0]['id']
                                if cfg['cuentas'] else None)
    return save_cfg(cfg)


def poner_datos_cuenta(nombre, email):
    """Nombre y correo de la cuenta activa (se averiguan al conectar)."""
    cfg = _sin_cuenta_aplanada(load_cfg())
    activa = _activa(cfg)
    if activa is None:
        return False
    # si ya habia otra cuenta con ese correo, es la misma: se queda una
    for c in list(cfg['cuentas']):
        if (c is not activa and email
                and (c.get('email') or '').lower() == email.lower()):
            cfg['cuentas'].remove(c)
            boveda.borrar(_boveda_de(c['id']))
    activa['nombre'], activa['email'] = nombre, email
    return save_cfg(cfg, durable=False)


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
