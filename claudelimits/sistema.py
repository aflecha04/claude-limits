# -*- coding: utf-8 -*-
"""Todo lo que habla con Windows: instancia unica, arranque con el
sistema, registro de errores, pantallas y ventana."""

import os
import sys
import subprocess
from datetime import datetime

from .canal import VERSION, MUTEX_NAME, RUN_VALUE, RUN_VALUE_ANTIGUO
from .config import cfg_dirs

def _dpi_aware():
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


# ─── Instancia unica ────────────────────────────────────────────────────
# Sin esto, dos copias del widget (p. ej. un acceso directo viejo que abre
# la version anterior y otro que abre la nueva) se colocan en la MISMA
# posicion guardada y se turnan para estar encima cada 600 ms: se ve como
# un parpadeo entre el tema claro y el oscuro.
_MUTEX = None

EXE_NAMES_ANTIGUOS = ('ClaudeGlass by Flecha.exe', 'ClaudeGlass.exe',
                      'ClaudeGlass_ANTIGUO.exe',
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
# Windows guarda aparte si el usuario ha DESACTIVADO la entrada en
# Administrador de tareas > Inicio. Mientras ese veto siga ahi, da igual
# cuantas veces reescribamos la clave Run: no arranca y no avisa de nada.
APPROVED_KEY = (r'Software\Microsoft\Windows\CurrentVersion\Explorer'
                r'\StartupApproved\Run')


def _mi_ruta():
    if getattr(sys, 'frozen', False):
        return os.path.abspath(sys.executable)
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'claude_glass.pyw')


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


def autostart_quitar_antiguo():
    """Quita la entrada de arranque con el nombre antiguo (ClaudeGlass)."""
    if RUN_VALUE_ANTIGUO == RUN_VALUE:
        return False
    try:
        import winreg
        for clave in (RUN_KEY, APPROVED_KEY):
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, clave, 0,
                                    winreg.KEY_SET_VALUE) as k:
                    winreg.DeleteValue(k, RUN_VALUE_ANTIGUO)
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


_FAMILIA = ('claudeglass', 'claude limits')


def tapado(widget):
    """True si alguna ventana de OTRO programa esta por encima y tapa a esta.

    Antes el widget se volvia a poner delante cada 600 ms pasara lo que
    pasara. Eso hacia que Windows lo recolocara y repintara sin parar, y si
    habia otra copia del widget al lado (la version de siempre), las dos se
    quitaban el primer puesto por turnos: vibraba y parpadeaba, sobre todo
    con el menu o el panel abiertos. Ahora solo se pone delante si algo lo
    tapa de verdad, y nunca se pelea con sus propias ventanas ni con otra
    copia del widget.
    """
    try:
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        hwnd = _ventana_nativa(widget)
        if not hwnd:
            return False
        mio = wintypes.RECT()
        u.GetWindowRect(hwnd, ctypes.byref(mio))
        propio = os.getpid()
        pid = wintypes.DWORD()
        otro = wintypes.RECT()
        titulo = ctypes.create_unicode_buffer(64)
        oculto = ctypes.c_int()
        h = u.GetWindow(hwnd, 3)                      # GW_HWNDPREV: la de encima
        vistas = 0
        while h and vistas < 400:
            vistas += 1
            if u.IsWindowVisible(h):
                u.GetWindowRect(h, ctypes.byref(otro))
                if (otro.left < mio.right and otro.right > mio.left
                        and otro.top < mio.bottom and otro.bottom > mio.top):
                    u.GetWindowThreadProcessId(h, ctypes.byref(pid))
                    u.GetWindowTextW(h, titulo, 64)
                    try:
                        ctypes.windll.dwmapi.DwmGetWindowAttribute(
                            h, 14, ctypes.byref(oculto), ctypes.sizeof(oculto))
                    except Exception:
                        oculto.value = 0
                    if (pid.value != propio and not oculto.value
                            and not titulo.value.lower().startswith(_FAMILIA)):
                        return True
            h = u.GetWindow(h, 3)
        return False
    except Exception:
        return False


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
