# -*- coding: utf-8 -*-
"""Consulta del consumo en claude.ai y lectura de la respuesta."""

import re
import json
import subprocess
from datetime import datetime, timezone

from .config import load_cfg, save_cfg

# ─── API ────────────────────────────────────────────────────────────────
API_URL  = 'https://claude.ai/api/organizations/{}/usage'
ORGS_URL = 'https://claude.ai/api/organizations'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36')

REFRESH_MS = 30_000           # auto-refresh cada 30 s
TOPMOST_MS = 600              # re-afirmar siempre-encima


# ─── Errores tipados ────────────────────────────────────────────────────
class NoKey(PermissionError):
    """No hay ninguna sessionKey configurada."""


class KeyExpired(PermissionError):
    """Hay clave, pero el servidor la rechaza (401/403)."""


# ─── Datos ──────────────────────────────────────────────────────────────
def _curl(url, cookie=None, extra=()):
    cabeceras = ['-H', f'User-Agent: {UA}']
    if cookie:
        cabeceras += ['-H', f'Cookie: {cookie}',
                      '-H', 'anthropic-client-platform: web_claude_ai']
    r = subprocess.run(
        ['curl', '-s', '-D', '-', *cabeceras, *extra, url],
        capture_output=True, timeout=20,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode('utf-8', 'replace').strip()
                           or 'curl error')
    # en UTF-8 siempre: con la codificacion de Windows los nombres con
    # tildes o comillas tipograficas salian rotos ('teamâ€˜s')
    return r.stdout.decode('utf-8', 'replace')


def _split(raw):
    parts = raw.split('\r\n\r\n', 1)
    if len(parts) < 2:
        parts = raw.split('\n\n', 1)
    headers = parts[0] if len(parts) == 2 else ''
    return headers, parts[-1].strip()


def _status(headers):
    m = re.search(r'HTTP/[\d.]+ (\d+)', headers)
    return int(m.group(1)) if m else 0


def listar_orgs(cfg):
    """[(uuid, nombre, sirve_para_chat)] de las organizaciones de la cuenta.

    Una cuenta puede tener varias: la personal, la del equipo (Team o
    Enterprise) y alguna solo de API, que no tiene consumo de chat.
    """
    headers, body = _split(_curl(ORGS_URL, f"sessionKey={cfg['session_key']}"))
    if _status(headers) in (401, 403):
        raise KeyExpired('Clave caducada')
    orgs = json.loads(body)
    out = []
    for o in (orgs if isinstance(orgs, list) else []):
        if not isinstance(o, dict) or not o.get('uuid'):
            continue
        caps = o.get('capabilities') or []
        chat = not caps or 'chat' in caps
        out.append((str(o['uuid']), str(o.get('name') or 'Sin nombre'), chat))
    return out


def resolve_org(cfg):
    """Elige organizacion si aun no hay una y la guarda.

    Antes se cogia siempre la PRIMERA de la lista: con una cuenta personal y
    otra de empresa podia mostrar el consumo de la que no era, sin que se
    notara. Ahora se prefiere la primera que tenga chat, y desde el menu se
    puede elegir otra (cfg['orgs'] guarda la lista para ofrecerla).
    """
    orgs = listar_orgs(cfg)
    if not orgs:
        raise RuntimeError('no org')
    cfg['orgs'] = [[u, n] for u, n, _c in orgs]
    con_chat = [u for u, _n, c in orgs if c]
    cfg['org_id'] = (con_chat or [orgs[0][0]])[0]
    save_cfg(cfg)
    return cfg['org_id']


def nombre_org(cfg):
    """Nombre de la organizacion elegida, si se conoce."""
    for par in cfg.get('orgs') or []:
        try:
            if par[0] == cfg.get('org_id'):
                return str(par[1])
        except Exception:
            continue
    return None


def fetch_session():
    """Devuelve (pct:int, resets_at:str) de la sesion de 5 h, o lanza error."""
    cfg = load_cfg()
    if not cfg.get('session_key'):
        raise NoKey('Falta sessionKey')
    if not cfg.get('org_id'):
        resolve_org(cfg)
    elif not cfg.get('orgs'):
        # viene de una version que no guardaba la lista: se rellena una vez
        # para poder ofrecer el cambio de cuenta en el menu
        try:
            cfg['orgs'] = [[u, n] for u, n, _c in listar_orgs(cfg)]
            save_cfg(cfg)
        except KeyExpired:
            raise
        except Exception:
            pass

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
