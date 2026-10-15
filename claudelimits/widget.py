# -*- coding: utf-8 -*-
"""El widget: une las piezas (panel, menu, dibujo...) y lleva los datos y
los temporizadores."""

import threading
import tkinter as tk
import tkinter.font as tkfont

from . import tema as T
from . import actualizaciones
from .tema import apply_theme, apply_scale, px
from .canal import APP_NAME
from .config import load_cfg, save_cfg
from .api import (fetch_session, NoKey, KeyExpired, countdown,
                  countdown_clock, _reset_secs, REFRESH_MS, TOPMOST_MS)
from .sistema import (_dpi_aware, round_corners, asegurar_fuera_de_barra,
                      log_error)
from .panel import Panel
from .menu import Menu
from .ajustes import Ajustes
from .dibujo import Dibujo
from .dialogos import Dialogos
from .posicion import Posicion


class Glass(Panel, Menu, Ajustes, Dibujo, Dialogos, Posicion):
    """El widget."""

class Glass(Panel, Menu, Ajustes, Dibujo, Dialogos, Posicion):
    def __init__(self):
        _dpi_aware()

        cfg = load_cfg()
        T.set_color_propio(cfg.get('accent_hex'))
        apply_theme(cfg.get('theme', 'dark'), cfg.get('accent', 'coral'))

        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.overrideredirect(True)
        T.elegir_fuente(self.root)
        self.root.attributes('-topmost', True)

        # escala segun el DPI real de la pantalla (125%, 150%, 175%...)
        try:
            dpi = self.root.winfo_fpixels('1i')
        except Exception:
            dpi = 96.0
        self.root.tk.call('tk', 'scaling', 1.0)   # fuentes en px, sin sorpresas
        self.dpi = dpi or 96.0
        T.DPI_UI = self.dpi / 96.0
        # escala del usuario (barrita del menu), sobre la escala del sistema
        try:
            self.user_scale = float(cfg.get('scale', 1.0))
        except Exception:
            self.user_scale = 1.0
        # A partir de esta version el tamano de fabrica es Normal (100 %).
        # Se reajusta una sola vez a quien viniera con otro valor guardado.
        if not cfg.get('size_normalizado_v31'):
            self.user_scale = 1.0
            try:
                cfg['scale'] = 1.0
                cfg['size_normalizado_v31'] = True
                save_cfg(cfg, durable=False)
            except Exception:
                pass
        self.user_scale = max(0.7, min(2.0, self.user_scale))
        apply_scale(self.dpi / 96.0 * self.user_scale)

        x, y = self._load_pos()
        self.root.geometry(f'{T.W}x{T.H}+{x}+{y}')

        self.acrylic = False
        self.root.attributes('-alpha', T.ALPHA)
        self.root.configure(bg=T.TINT)
        self._bg = T.TINT
        round_corners(self.root)

        self.cv = tk.Canvas(self.root, width=T.W, height=T.H,
                            bg=T.TINT, highlightthickness=0, bd=0)
        self.cv.pack(fill='both', expand=True)

        # fuentes: tamano NEGATIVO = pixeles, para que no las escale el DPI
        # Escala tipografica: la cifra manda, la unidad acompana y el
        # rotulo se aparta. Las cifras en familia ancha, los textos en Segoe UI.
        self.f_pct   = tkfont.Font(family=T.FUENTE, size=-px(13), weight='bold')
        self.f_sub   = tkfont.Font(family=T.FUENTE, size=-px(13))
        self.f_msg   = tkfont.Font(family=T.FUENTE, size=-px(11), weight='bold')
        self.f_pnum  = tkfont.Font(family=T.FUENTE, size=-px(18), weight='bold')
        self.f_ptit  = tkfont.Font(family=T.FUENTE, size=-px(12))
        self.f_pcd   = tkfont.Font(family=T.FUENTE, size=-px(12))
        # la X con la fuente de iconos de Windows, hecha para tamanos
        # pequenos; la de simbolos de antes salia fina y difusa
        fi = self._fuente_iconos()
        self._x_glifo = '' if fi else '✕'
        self.f_icon = tkfont.Font(family=(fi or 'Segoe UI Symbol'),
                                  size=-px(10 if fi else 14))

        self.pct = None
        self.reset_iso = None
        self.state = 'Cargando...'
        self.key_state = 'ok'        # ok | nokey | expired | offline
        self.status_msg = None       # texto dentro de la barra si hay aviso
        self._auto_prompted = False
        self._save_warned = False
        self.usage = {}
        self._panel = None
        self._txtwin = None
        self._szdlg = None
        self._orgdlg = None
        self._mrep = []              # repintado del menu (ver menu.py)
        self.nueva_version = None    # (version, url_exe, url_pagina)
        self._dlg = None
        self._menu_win = None
        self._arrastrando = False
        self._hover_abrir_id = None
        self._hover_cerrar_id = None

        self._build()               # crea tambien el menu contextual
        self._bind_drag()

        self._sleeping = False
        self.refresh()
        self._tick_topmost()
        self._tick_pantallas()
        self._tick_countdown()
        self._tick_clock()
        self.root.after(actualizaciones.PRIMERA_MS, self._tick_actualizaciones)

        # primer arranque sin clave -> pedirla UNA vez
        if not cfg.get('session_key'):
            self._auto_prompted = True
            self.root.after(400, self._login_dialog)

    # ---- layout -------------------------------------------------------
    def _build(self):
        c = self.cv
        cy = T.H // 2
        self._geometria_barra()
        self._cd = ''

        self._shape_id = c.create_image(0, 0, anchor='nw', tags='shape')

        self.id_close = c.create_text(T.W - T.PAD, cy, text=self._x_glifo, anchor='e',
                                      fill=T.BTN, font=self.f_icon)


        self._hook(self.id_close, T.CLOSE_HOV, self.close)

        self._render_all()

    # ---- datos --------------------------------------------------------
    def refresh(self):
        self._cargando = True
        self._draw_labels()          # el contador se atenua mientras consulta
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        try:
            pct, reset_iso, data = fetch_session()
            self.root.after(0, self._apply, pct, reset_iso, None, data)
        except NoKey:
            self.root.after(0, self._apply, None, None, 'nokey', None)
        except KeyExpired:
            self.root.after(0, self._apply, None, None, 'expired', None)
        except Exception:
            self.root.after(0, self._apply, None, None, 'offline', None)

    def _apply(self, pct, reset_iso, err, data=None):
        self._cargando = False
        if err:
            self.key_state = err
            self.pct = None
            self.reset_iso = None
            self.usage = {}
            if err == 'nokey':
                self.status_msg = 'Inicia sesión'
                self._cd = 'clic dcho'
                # abrir el dialogo solo la primera vez, nunca en bucle
                if not self._auto_prompted:
                    self._auto_prompted = True
                    self.root.after(300, self._login_dialog)
            elif err == 'expired':
                self.status_msg = 'Clave caducada'
                self._cd = 'clic dcho'
            else:
                self.status_msg = 'Sin conexión'
                self._cd = ''
            self._render_all()
            return
        self.key_state = 'ok'
        self.status_msg = None
        self.usage = data or {}
        self.pct = pct
        self.reset_iso = reset_iso
        self._update_sub()
        self._panel_refrescar()

    def _update_sub(self):
        self._sleeping = self.pct is not None and self.pct >= 100
        if self.reset_iso:
            self._cd = (countdown_clock(self.reset_iso) if self._sleeping
                        else countdown(self.reset_iso))
        else:
            self._cd = ''
        self._render_all()
        if self.reset_iso and _reset_secs(self.reset_iso) <= 0:
            self.refresh()

    def _tick_clock(self):
        if self.pct is not None and self.pct >= 100:
            self._update_sub()
        self.root.after(1000, self._tick_clock)

    # ---- temporizadores ------------------------------------------------
    def _tick_topmost(self):
        try:
            self.root.attributes('-topmost', True)
            corregido = (asegurar_fuera_de_barra(self.root)
                         if self.root.winfo_ismapped() else None)
            if corregido is not None and not getattr(self, '_barra_avisado', False):
                # se apunta una vez, para saber que lo provoca
                self._barra_avisado = True
                log_error('BARRA DE TAREAS (no es un fallo, ya corregido)\n'
                          f'  la ventana habia perdido la marca: estilo {corregido:#x}')
            # el widget se reafirma encima cada 600 ms; el menu y los dialogos
            # abiertos tienen que subir con el, o quedarian tapados
            for attr in ('_menu_win', '_panel', '_dlg', '_szdlg', '_txtwin',
                         '_orgdlg', '_coldlg'):
                w = getattr(self, attr, None)
                if w is not None and w.winfo_exists():
                    w.lift()
                    w.attributes('-topmost', True)
        except Exception:
            pass
        self.root.after(TOPMOST_MS, self._tick_topmost)

    def _tick_countdown(self):
        if self.pct is not None:
            self._update_sub()
        self.root.after(30_000, self._tick_countdown)
        self._since = getattr(self, '_since', 0) + 30_000
        if self._since >= REFRESH_MS:
            self._since = 0
            self.refresh()

    # ---- arrastre + posicion -------------------------------------------
    def _bind_drag(self):
        for w in (self.cv, self.root):
            w.bind('<Button-1>', self._drag_start)
            w.bind('<B1-Motion>', self._drag_move)
            w.bind('<ButtonRelease-1>', self._drag_end)
            w.bind('<Button-3>', self._popup)      # clic dcho: menu
            w.bind('<Enter>', self._hover_programar_apertura)
            w.bind('<Leave>', self._hover_programar_cierre)

    # ---- version nueva ------------------------------------------------
    def _tick_actualizaciones(self):
        def mirar():
            nueva = actualizaciones.comprobar()
            self.root.after(0, lambda: setattr(self, 'nueva_version', nueva))
        threading.Thread(target=mirar, daemon=True).start()
        self.root.after(actualizaciones.COMPROBAR_MS, self._tick_actualizaciones)

    def _instalar_actualizacion(self):
        nueva = self.nueva_version
        if not nueva:
            return
        version, url_exe, pagina = nueva
        self.status_msg = 'Descargando…'
        self._render_all()

        def bajar():
            ok = False
            try:
                ok = actualizaciones.instalar(url_exe)
            except Exception as ex:
                log_error(f'ACTUALIZACION FALLIDA\n  {ex}')
            self.root.after(0, terminar, ok)

        def terminar(ok):
            if ok:
                self.close()               # el .bat la sustituye y la reabre
                return
            self.status_msg = None
            self._render_all()
            self._text_window(
                f'{APP_NAME}  -  actualizar',
                f'No se ha podido instalar la versión {version} sola.\n\n'
                'Descárgala a mano desde:\n'
                f'  {pagina or actualizaciones.ULTIMA_URL}')
        threading.Thread(target=bajar, daemon=True).start()

    def close(self, e=None):
        self._panel_ocultar()
        self._save_pos()
        self.root.destroy()

    def run(self):
        self.root.mainloop()
