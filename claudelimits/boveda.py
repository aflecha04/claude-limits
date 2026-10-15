# -*- coding: utf-8 -*-
"""Caja fuerte de Windows (Administrador de credenciales).

La sessionKey es el acceso a la cuenta de Claude: no debe quedar en un
config.json en texto plano, y menos copiada en cuatro carpetas (una de
ellas junto al .exe, que es la que se comparte). Windows guarda aqui las
contrasenas de cada usuario cifradas con su sesion, y se puede usar sin
instalar nada: basta con ctypes.

Si en algun equipo la caja fuerte no estuviera disponible, las funciones
devuelven None / False y config.py sigue guardando en archivo, como antes.
"""

import ctypes
from ctypes import wintypes

_CRED_TYPE_GENERIC = 1
_CRED_PERSIST_LOCAL_MACHINE = 2
_ERROR_NOT_FOUND = 1168


class _CREDENTIALW(ctypes.Structure):
    _fields_ = [('Flags', wintypes.DWORD),
                ('Type', wintypes.DWORD),
                ('TargetName', wintypes.LPWSTR),
                ('Comment', wintypes.LPWSTR),
                ('LastWritten', wintypes.FILETIME),
                ('CredentialBlobSize', wintypes.DWORD),
                ('CredentialBlob', ctypes.POINTER(ctypes.c_ubyte)),
                ('Persist', wintypes.DWORD),
                ('AttributeCount', wintypes.DWORD),
                ('Attributes', ctypes.c_void_p),
                ('TargetAlias', wintypes.LPWSTR),
                ('UserName', wintypes.LPWSTR)]


_API = None


def _api():
    """advapi32 con sus firmas, preparado una sola vez (se usa en cada consulta)."""
    global _API
    if _API is not None:
        return _API
    a = ctypes.WinDLL('advapi32', use_last_error=True)
    a.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIALW), wintypes.DWORD]
    a.CredWriteW.restype = wintypes.BOOL
    a.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                            ctypes.POINTER(ctypes.POINTER(_CREDENTIALW))]
    a.CredReadW.restype = wintypes.BOOL
    a.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    a.CredDeleteW.restype = wintypes.BOOL
    a.CredFree.argtypes = [ctypes.c_void_p]
    a.CredFree.restype = None
    _API = a
    return a


def leer(nombre):
    """Valor guardado con ese nombre, o None si no hay (o no se puede)."""
    try:
        a = _api()
        p = ctypes.POINTER(_CREDENTIALW)()
        if not a.CredReadW(nombre, _CRED_TYPE_GENERIC, 0, ctypes.byref(p)):
            return None
        try:
            c = p.contents
            datos = ctypes.string_at(c.CredentialBlob, c.CredentialBlobSize)
            return datos.decode('utf-8') or None
        finally:
            a.CredFree(p)
    except Exception:
        return None


def guardar(nombre, valor):
    """Guarda (o reemplaza) el valor. True si queda guardado y se relee igual."""
    try:
        a = _api()
        datos = valor.encode('utf-8')
        buf = (ctypes.c_ubyte * len(datos)).from_buffer_copy(datos)
        c = _CREDENTIALW()
        c.Type = _CRED_TYPE_GENERIC
        c.TargetName = nombre
        c.CredentialBlobSize = len(datos)
        c.CredentialBlob = ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte))
        c.Persist = _CRED_PERSIST_LOCAL_MACHINE
        c.UserName = 'Claude Limits'
        if not a.CredWriteW(ctypes.byref(c), 0):
            return False
        return leer(nombre) == valor
    except Exception:
        return False


def borrar(nombre):
    try:
        a = _api()
        if a.CredDeleteW(nombre, _CRED_TYPE_GENERIC, 0):
            return True
        return ctypes.get_last_error() == _ERROR_NOT_FOUND
    except Exception:
        return False
