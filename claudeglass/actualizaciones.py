# -*- coding: utf-8 -*-
"""Aviso de version nueva e instalacion con un clic.

Cada version se publica en GitHub como 'release' con el .exe adjunto. El
widget mira de vez en cuando si la ultima es mas nueva que la suya y, si
lo es, lo dice en el menu. Al aceptar descarga el .exe y lo cambia por el
actual con un pequeno .bat (un programa abierto no puede sobrescribirse
a si mismo), que despues lo vuelve a abrir.

Si no hay internet o el repositorio no es accesible, no pasa nada: el
widget simplemente no avisa.
"""

import os
import re
import json
import subprocess
import tempfile

from .api import _curl, _split, _status
from .canal import VERSION
from .sistema import _mi_ruta

REPO = 'aflecha04/claudeglass'
ULTIMA_URL = f'https://api.github.com/repos/{REPO}/releases/latest'
COMPROBAR_MS = 6 * 3600 * 1000          # cada 6 horas
PRIMERA_MS = 15_000                     # la primera, poco despues de abrir


def _tupla(v):
    """'v3.10' -> (3, 10). Lo que no sea numero se ignora."""
    return tuple(int(n) for n in re.findall(r'\d+', str(v or ''))[:3])


def es_mas_nueva(remota, local=VERSION):
    a, b = _tupla(remota), _tupla(local)
    return bool(a) and a > b


def leer_ultima(datos):
    """(version, url_exe, url_pagina) de la respuesta de GitHub, o None."""
    if not isinstance(datos, dict) or datos.get('draft') or datos.get('prerelease'):
        return None
    version = str(datos.get('tag_name') or '').lstrip('vV')
    if not version:
        return None
    exe = None
    for a in datos.get('assets') or []:
        nombre = str((a or {}).get('name') or '').lower()
        if nombre.endswith('.exe') and 'prueba' not in nombre:
            exe = a.get('browser_download_url')
            break
    return version, exe, datos.get('html_url')


def comprobar():
    """(version, url_exe, url_pagina) si hay una version mas nueva; si no, None."""
    try:
        headers, body = _split(_curl(
            ULTIMA_URL, extra=('-H', 'Accept: application/vnd.github+json')))
        if _status(headers) != 200:
            return None
        ultima = leer_ultima(json.loads(body))
    except Exception:
        return None
    if ultima and es_mas_nueva(ultima[0]):
        return ultima
    return None


def instalar(url_exe):
    """Descarga el .exe nuevo y deja lanzado el cambio.

    Devuelve True si todo esta listo: entonces el widget debe cerrarse para
    que el .bat pueda sustituir el ejecutable y volver a abrirlo.
    """
    destino = _mi_ruta()
    if not url_exe or not destino.lower().endswith('.exe'):
        return False
    carpeta = os.path.join(tempfile.gettempdir(), 'ClaudeGlassUpdate')
    os.makedirs(carpeta, exist_ok=True)
    nuevo = os.path.join(carpeta, 'nuevo.exe')
    r = subprocess.run(['curl', '-s', '-L', '-o', nuevo, url_exe],
                       capture_output=True, timeout=300,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    # un .exe de verdad pesa varios MB y empieza por 'MZ'
    try:
        with open(nuevo, 'rb') as f:
            cabeza = f.read(2)
        ok = (r.returncode == 0 and cabeza == b'MZ'
              and os.path.getsize(nuevo) > 1_000_000)
    except Exception:
        ok = False
    if not ok:
        return False
    bat = os.path.join(carpeta, 'actualizar.bat')
    with open(bat, 'w', encoding='mbcs', errors='replace') as f:
        f.write('@echo off\r\n'
                'ping -n 3 127.0.0.1 >nul\r\n'
                f'copy /Y "{nuevo}" "{destino}" >nul\r\n'
                f'start "" "{destino}"\r\n')
    subprocess.Popen(['cmd', '/c', bat],
                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return True
