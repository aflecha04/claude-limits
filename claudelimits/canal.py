# -*- coding: utf-8 -*-
"""Version y canal del widget: NORMAL o PRUEBA.

La copia de PRUEBA convive con la normal sin tocarla: otro nombre, otra
carpeta de datos, otra entrada en la caja fuerte de Windows y otra marca
de instancia unica. Asi se puede probar una version nueva y, si no
convence, borrarla y seguir con la de siempre como si nada.

El canal se decide por el nombre del ejecutable ('... PRUEBA.exe') o, en
desarrollo, con el argumento --prueba.
"""

import os
import sys

VERSION = '3.2'


def _es_prueba():
    if '--prueba' in sys.argv:
        return True
    if getattr(sys, 'frozen', False):
        return 'prueba' in os.path.basename(sys.executable).lower()
    return False


PRUEBA = _es_prueba()

APP_NAME = 'Claude Limits PRUEBA' if PRUEBA else 'Claude Limits'

# Nombre interno (carpetas de datos, caja fuerte, instancia unica). Es el
# de cuando el widget se llamaba ClaudeGlass: se conserva para que, al
# cambiar de nombre, nadie pierda sus cuentas ni sus ajustes.
ID_INTERNO = 'ClaudeGlass PRUEBA' if PRUEBA else 'ClaudeGlass by Flecha'

# Nombre de la entrada en el Administrador de credenciales de Windows
BOVEDA_CLAVE = f'{ID_INTERNO}/sessionKey'

# Marca de instancia unica: distinta para que las dos copias puedan abrirse
MUTEX_NAME = ('Global\\ClaudeGlassPrueba_SingleInstance' if PRUEBA
              else 'Global\\ClaudeGlassByFlecha_SingleInstance')

# Entrada del registro para arrancar con Windows
RUN_VALUE = APP_NAME
# La de las versiones anteriores, que hay que quitar para que no se abran
# las dos al encender
RUN_VALUE_ANTIGUO = ID_INTERNO
