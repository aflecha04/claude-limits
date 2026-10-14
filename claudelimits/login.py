# -*- coding: utf-8 -*-
"""Iniciar sesion en Claude sin copiar la clave a mano.

Abre una ventana de Edge (o Chrome) con un perfil propio del widget, en la
pagina de inicio de sesion de claude.ai. Cuando la persona entra, el widget
lee la cookie sessionKey de esa ventana y la cierra. Nada se instala: se
usa el navegador que ya trae Windows y su "puerto de depuracion", el mismo
canal que usan las herramientas de desarrollo.

El perfil del navegador es solo del widget (no ve las pestanas, cuentas ni
contrasenas del navegador normal) y se vacia de cookies antes de cada
inicio de sesion, para poder entrar con otra cuenta.
"""

import os
import json
import time
import base64
import shutil
import socket
import struct
import subprocess
import urllib.request

from .canal import PRUEBA

LOGIN_URL = 'https://claude.ai/login'
ESPERA_MAX = 15 * 60            # segundos que se espera a que inicie sesion


class Cancelado(Exception):
    """Se cerro la ventana del navegador sin iniciar sesion."""


# Navegadores que entienden el puerto de depuracion (todos los basados en
# Chromium). Firefox no: si es el principal, se usa Edge, que viene con Windows.
CHROMIUM = ('chrome.exe', 'msedge.exe', 'brave.exe', 'opera.exe',
            'launcher.exe', 'vivaldi.exe', 'arc.exe', 'chromium.exe')


def _navegador_principal():
    """Ruta del navegador predeterminado de Windows, o None."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r'Software\Microsoft\Windows\Shell\Associations'
                            r'\UrlAssociations\https\UserChoice') as k:
            progid, _ = winreg.QueryValueEx(k, 'ProgId')
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,
                            progid + r'\shell\open\command') as k:
            orden, _ = winreg.QueryValueEx(k, '')
        m = orden.split('"')[1] if orden.startswith('"') else orden.split(' ')[0]
        if os.path.exists(m) and os.path.basename(m).lower() in CHROMIUM:
            return m
    except Exception:
        pass
    return None


def _navegador():
    principal = _navegador_principal()
    if principal:
        return principal
    candidatos = []
    for base in (os.environ.get('PROGRAMFILES(X86)'), os.environ.get('PROGRAMFILES'),
                 os.environ.get('LOCALAPPDATA')):
        if base:
            candidatos += [os.path.join(base, 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
                           os.path.join(base, 'Google', 'Chrome', 'Application', 'chrome.exe')]
    for p in candidatos:
        if os.path.exists(p):
            return p
    return None


def _perfil(exe):
    """Perfil propio del widget, uno por navegador: Chrome no arranca con
    una carpeta de perfil creada por Edge."""
    la = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
    return os.path.join(la, 'ClaudeGlass PRUEBA' if PRUEBA else 'ClaudeGlass',
                        'navegador', os.path.splitext(os.path.basename(exe))[0])


def _puerto_libre():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


# ─── WebSocket minimo (solo lo que necesita el protocolo de depuracion) ──
class _WS:
    def __init__(self, url):
        hostport, ruta = url[len('ws://'):].split('/', 1)
        host, port = hostport.split(':')
        self.s = socket.create_connection((host, int(port)), timeout=10)
        clave = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f'GET /{ruta} HTTP/1.1\r\nHost: {hostport}\r\n'
                        'Upgrade: websocket\r\nConnection: Upgrade\r\n'
                        f'Sec-WebSocket-Key: {clave}\r\n'
                        'Sec-WebSocket-Version: 13\r\n\r\n').encode())
        resp = b''
        while b'\r\n\r\n' not in resp:
            trozo = self.s.recv(4096)
            if not trozo:
                raise ConnectionError('sin respuesta')
            resp += trozo
        if b' 101 ' not in resp.split(b'\r\n', 1)[0]:
            raise ConnectionError('websocket rechazado')
        self._resto = resp.split(b'\r\n\r\n', 1)[1]
        self._n = 0

    def _leer(self, n):
        while len(self._resto) < n:
            trozo = self.s.recv(65536)
            if not trozo:
                raise ConnectionError('cerrado')
            self._resto += trozo
        out, self._resto = self._resto[:n], self._resto[n:]
        return out

    def _enviar(self, texto):
        datos = texto.encode()
        cab = bytearray([0x81])
        n = len(datos)
        if n < 126:
            cab.append(0x80 | n)
        elif n < 65536:
            cab.append(0x80 | 126)
            cab += struct.pack('>H', n)
        else:
            cab.append(0x80 | 127)
            cab += struct.pack('>Q', n)
        mascara = os.urandom(4)
        self.s.sendall(bytes(cab) + mascara +
                       bytes(b ^ mascara[i % 4] for i, b in enumerate(datos)))

    def _mensaje(self):
        partes = b''
        while True:
            b1, b2 = self._leer(2)
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack('>H', self._leer(2))[0]
            elif n == 127:
                n = struct.unpack('>Q', self._leer(8))[0]
            datos = self._leer(n)
            if b1 & 0x0F == 8:
                raise ConnectionError('cerrado')
            partes += datos
            if b1 & 0x80:
                return partes.decode('utf-8', 'replace')

    def llamar(self, metodo, **params):
        self._n += 1
        self._enviar(json.dumps({'id': self._n, 'method': metodo, 'params': params}))
        while True:
            m = json.loads(self._mensaje())
            if m.get('id') == self._n:
                return m.get('result') or {}

    def cerrar(self):
        try:
            self.s.close()
        except Exception:
            pass


def _json(puerto, ruta):
    with urllib.request.urlopen(f'http://127.0.0.1:{puerto}{ruta}', timeout=3) as r:
        return json.loads(r.read().decode())


def _cerrar_restos(perfil):
    """Cierra cualquier proceso del navegador que siga usando el perfil del
    widget (por ejemplo, si se corto a medias). Nunca toca el navegador
    normal: se filtra por la carpeta de perfil en la linea de comandos."""
    filtro = perfil.replace("'", "''")
    try:
        subprocess.run(
            ['powershell', '-NoProfile', '-Command',
             "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine "
             f"-like '*{filtro}*' }} | ForEach-Object {{ Stop-Process -Id "
             "$_.ProcessId -Force -ErrorAction SilentlyContinue }"],
            capture_output=True, timeout=20,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except Exception:
        pass


def iniciar_sesion(cancelar=lambda: False):
    """Abre la ventana de inicio de sesion y espera. Devuelve la sessionKey.

    Lanza Cancelado si se cierra la ventana (o cancelar() devuelve True), y
    RuntimeError si no hay navegador con el que hacerlo.
    """
    exe = _navegador()
    if not exe:
        raise RuntimeError('No encuentro Edge ni Chrome en este equipo.')
    perfil = _perfil(exe)
    # perfil nuevo en cada inicio de sesion: sin cookies de la cuenta
    # anterior, y la ventana se abre directamente en Claude (sin pasar por
    # una pestana en blanco)
    _cerrar_restos(perfil)
    shutil.rmtree(perfil, ignore_errors=True)
    os.makedirs(perfil, exist_ok=True)
    puerto = _puerto_libre()
    proc = subprocess.Popen(
        [exe, f'--remote-debugging-port={puerto}', f'--user-data-dir={perfil}',
         '--no-first-run', '--no-default-browser-check',
         '--window-size=520,760', f'--app={LOGIN_URL}'],
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    navegador = None
    try:
        # 1) esperar a que el navegador abra su puerto
        limite = time.time() + 40
        while True:
            if cancelar():
                raise Cancelado()
            try:
                version = _json(puerto, '/json/version')
                break
            except Exception:
                if time.time() > limite:
                    raise RuntimeError('El navegador no ha respondido.')
                time.sleep(0.3)
        navegador = _WS(version['webSocketDebuggerUrl'])

        # 2) esperar a que aparezca la cookie de sesion
        limite = time.time() + ESPERA_MAX
        while time.time() < limite:
            if cancelar():
                raise Cancelado()
            try:
                galletas = navegador.llamar('Storage.getCookies').get('cookies') or []
            except Exception:
                raise Cancelado()            # han cerrado la ventana
            for g in galletas:
                if (g.get('name') == 'sessionKey'
                        and 'claude.ai' in (g.get('domain') or '')
                        and str(g.get('value', '')).startswith('sk-ant-')):
                    return g['value']
            time.sleep(1.5)
        raise Cancelado()
    finally:
        if navegador is not None:
            try:
                navegador.llamar('Browser.close')
            except Exception:
                pass
            navegador.cerrar()
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
        _cerrar_restos(perfil)
