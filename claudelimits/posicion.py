# -*- coding: utf-8 -*-
"""Arrastre del widget y posicion recordada para cada juego de pantallas."""

import json

from . import tema as T
from .canal import PRUEBA
import os

from .config import pos_path_for_read, save_pos_file, cfg_dirs_normal, POS_NAME
from .sistema import work_area, monitores, firma_monitores, se_ve, encajar


class Posicion:
    """Arrastre y posicion por pantallas."""

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

    @staticmethod
    def _pos_de_la_normal():
        """Donde tiene el usuario la version normal (solo se lee)."""
        for d in cfg_dirs_normal():
            try:
                with open(os.path.join(d, POS_NAME), encoding='utf-8') as f:
                    v = json.load(f)
                return int(v['x']), int(v['y'])
            except Exception:
                continue
        return None

    def _load_pos(self):
        try:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
        except Exception:
            sw, sh = 1280, 720
        # por defecto: arriba a la derecha de la pantalla PRINCIPAL
        wa = work_area(0, 0)
        default = ((wa[2] - T.W - 24, wa[1] + 24) if wa else (sw - T.W - 24, 24))
        if PRUEBA:
            # la de prueba aparece justo debajo de la normal, no encima
            nx, ny = self._pos_de_la_normal() or default
            default = (nx, ny + T.H + 12)
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
                if se_ve(x, y, T.W, T.H, mons):
                    return x, y
            else:
                vl, vt, vr, vb = self._escritorio_virtual() or (0, 0, sw, sh)
                if (vl - T.W + 60) < x < (vr - 60) and (vt - 5) < y < (vb - 20):
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
                    if guardada and se_ve(guardada[0], guardada[1], T.W, T.H, mons):
                        destino = guardada
                if destino is None and not se_ve(x, y, T.W, T.H, mons):
                    destino = encajar(x, y, T.W, T.H)
                if destino and tuple(destino) != (x, y):
                    self._panel_ocultar()
                    self._close_menu()
                    self.root.geometry(f'+{destino[0]}+{destino[1]}')
                    x, y = destino
                if firma == self._firma and se_ve(x, y, T.W, T.H, mons):
                    self._pos_actual = (x, y)
        except Exception:
            pass
        self.root.after(self.PANTALLAS_MS, self._tick_pantallas)
