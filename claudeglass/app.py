# -*- coding: utf-8 -*-
"""Arranque del widget."""

import sys

from .canal import PRUEBA
from .config import load_cfg, importar_de_version_normal
from .sistema import (ya_hay_una_instancia, cerrar_versiones_antiguas,
                      limpiar_accesos_directos_viejos, autostart_estado,
                      autostart_activar, autostart_vetado,
                      autostart_quitar_veto, _mi_ruta, log_error)
from .widget import Glass


def main():
    # 1) una sola copia viva: si ya hay otra, esta se retira sin ruido
    if ya_hay_una_instancia():
        return 0

    cerradas, borrados = [], []
    if PRUEBA:
        # la copia de prueba no toca nada de la normal: solo copia, la
        # primera vez, sus ajustes y su sessionKey
        try:
            importar_de_version_normal()
        except Exception:
            pass
    else:
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
    #    ha cambiado de sitio desde la ultima vez. La de prueba no arranca
    #    sola salvo que se active desde su menu.
    try:
        cfg = load_cfg()
        if cfg.get('autostart', not PRUEBA):
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


def arrancar():
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:
        import traceback
        log_error(traceback.format_exc())
        raise
