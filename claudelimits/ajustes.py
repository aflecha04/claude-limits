# -*- coding: utf-8 -*-
"""Tamano, color y tema del widget."""

import threading
import tkinter as tk

from . import tema as T
from .tema import apply_theme, apply_accent, apply_scale, px, mpx
from .config import load_cfg, save_cfg
from .sistema import round_corners


_GUARDAR_LOCK = threading.Lock()


class Ajustes:
    """Tamano, color y tema."""

    # ---- tamano ---------------------------------------------------------
    def _set_scale(self, factor, save=True):
        self.user_scale = max(0.7, min(2.0, float(factor)))
        self._relayout()
        if save:
            self._guardar_apariencia()

    def _relayout(self):
        """Recalcula geometria, fuentes y render tras cambiar el tamano."""
        # el panel desplegado se queda con el tamano y el sitio de antes
        self._panel_ocultar()
        apply_scale(self.dpi / 96.0 * self.user_scale)

        self.f_pct.config(size=-px(13))
        self.f_sub.config(size=-px(13))
        self.f_msg.config(size=-px(11))
        self.f_pnum.config(size=-px(18))
        self.f_ptit.config(size=-px(12))
        self.f_pcd.config(size=-px(12))
        self.f_icon.config(size=-px(10 if self._fuente_iconos() else 14))

        cy = T.H // 2
        self._geometria_barra()

        self.cv.config(width=T.W, height=T.H)
        x, y = self.root.winfo_x(), self.root.winfo_y()
        try:                                  # no dejarlo fuera de pantalla
            sw = self.root.winfo_screenwidth()
            x = min(x, sw - T.W - 8)
        except Exception:
            pass
        self.root.geometry(f'{T.W}x{T.H}+{max(0, x)}+{max(0, y)}')

        self.cv.coords(self.id_close, T.W - T.PAD, cy)
        self._render_all()

    def _size_dialog(self, e=None):
        dlg = getattr(self, '_szdlg', None)
        if dlg is not None and dlg.winfo_exists():
            dlg.lift(); dlg.focus_force(); return
        ancho = mpx(260)
        w = self._ventana('Tamaño', ancho)
        self._szdlg = w
        cuerpo = w._cuerpo

        valor = tk.Label(cuerpo, text=f'{int(round(self.user_scale * 100))} %',
                         bg=T.MENU_BG, fg=T.MENU_ACCENT,
                         font=(T.FUENTE, -mpx(30), 'bold'))
        valor.pack(pady=(mpx(6), mpx(2)))

        # deslizador dibujado a mano: el de Tk trae su propio aspecto y
        # rompia la coherencia con el resto
        cw, ch = ancho - mpx(36), mpx(30)
        lienzo = tk.Canvas(cuerpo, width=cw, height=ch, bg=T.MENU_BG,
                           highlightthickness=0, bd=0, cursor='hand2')
        lienzo.pack(padx=mpx(18), pady=(0, mpx(2)))
        MIN, MAX = 70, 200
        r = mpx(7)

        def pinta():
            v = int(round(self.user_scale * 100))
            lienzo.delete('all')
            cy = ch // 2
            grueso = mpx(6)
            # El canal va en el color del carril del widget, no en el de los
            # separadores del menu: aquel apenas se distingue del fondo del
            # dialogo y el deslizador parecia cortado a media altura.
            lienzo.create_line(r, cy, cw - r, cy, fill=T.TRACK,
                               width=grueso, capstyle='round')
            t = (v - MIN) / (MAX - MIN)
            x = r + t * (cw - 2 * r)
            if x > r + 1:
                lienzo.create_line(r, cy, x, cy, fill=T.MENU_ACCENT,
                                   width=grueso, capstyle='round')
            # tirador: aro del color del dialogo para separarlo del canal
            lienzo.create_oval(x - r - mpx(2), cy - r - mpx(2),
                               x + r + mpx(2), cy + r + mpx(2),
                               fill=T.MENU_BG, outline='')
            lienzo.create_oval(x - r, cy - r, x + r, cy + r,
                               fill=T.MENU_ACCENT, outline='')
            valor.config(text=f'{v} %')

        def mueve(ev):
            t = min(1.0, max(0.0, (ev.x - r) / max(1, cw - 2 * r)))
            v = int(round((MIN + t * (MAX - MIN)) / 5.0)) * 5
            if v != int(round(self.user_scale * 100)):
                self._set_scale(v / 100.0, save=False)
            pinta()

        lienzo.bind('<Button-1>', mueve)
        lienzo.bind('<B1-Motion>', mueve)
        pinta()

        ext = tk.Frame(cuerpo, bg=T.MENU_BG)
        ext.pack(fill='x', padx=mpx(18))
        tk.Label(ext, text='70 %', bg=T.MENU_BG, fg=T.MENU_MUTED,
                 font=(T.FUENTE, -mpx(10))).pack(side='left')
        tk.Label(ext, text='200 %', bg=T.MENU_BG, fg=T.MENU_MUTED,
                 font=(T.FUENTE, -mpx(10))).pack(side='right')

        def guardar():
            self._guardar_apariencia()

        def hecho():
            guardar()
            self._szdlg = None
            w.destroy()

        def restablecer():
            self._set_scale(1.0, save=False)
            pinta()

        bf = tk.Frame(cuerpo, bg=T.MENU_BG)
        bf.pack(pady=(mpx(14), mpx(14)))
        self._boton(bf, 'Restablecer', restablecer).pack(side='left', padx=mpx(5))
        self._boton(bf, 'Hecho', hecho, primario=True).pack(side='left', padx=mpx(5))
        w.protocol('WM_DELETE_WINDOW', hecho)
        self._place(w, self.root.winfo_x(), self.root.winfo_y() - mpx(200))
        round_corners(w)
        w.focus_force()

    def _set_accent(self, nombre):
        # para la papelera del color propio: volver al que habia antes
        if nombre == 'propio' and T.ACCENT_NAME != 'propio':
            self._accent_previo = T.ACCENT_NAME
        apply_accent(nombre)
        self.cv.itemconfig(self.id_close, fill=T.BTN)
        self._repintar_ventanas()
        self._render_all()
        self.root.update_idletasks()

        self._guardar_apariencia()

    def _repintar_ventanas(self):
        """Tras cambiar tema o color, las ventanas abiertas siguen con la
        paleta vieja. El panel se cierra (se redibuja solo al volver a pasar
        el raton) y el dialogo de tamano se vuelve a abrir con los colores
        nuevos, conservando el valor."""
        self._panel_ocultar()
        sz = getattr(self, '_szdlg', None)
        if sz is not None and sz.winfo_exists():
            self._szdlg = None
            sz.destroy()
            self.root.after(1, self._size_dialog)

    def _set_theme(self, name):
        # 1) repintar YA, sin tocar el disco
        apply_theme(name)
        self.root.attributes('-alpha', T.ALPHA)
        self.root.configure(bg=T.TINT)
        self.cv.configure(bg=T.TINT)
        self._bg = T.TINT
        self.cv.itemconfig(self.id_close, fill=T.BTN)
        # rehacer el hook para que el color de hover sea el del tema nuevo
        self._hook(self.id_close, T.CLOSE_HOV, self.close)
        self._repintar_ventanas()
        # el menu se dibuja al abrirlo, asi que no hay nada que reconstruir
        self._render_all()
        self.root.update_idletasks()

        # 2) y ahora, ya con el widget repintado, persistir en segundo plano
        self._guardar_apariencia()

    def _guardar_apariencia(self):
        """Guarda tema, color y tamano tal como estan AHORA.

        Antes cada cambio guardaba solo su valor en un hilo aparte: con varios
        cambios seguidos los hilos podian terminar en otro orden y quedaba
        guardado uno anterior. Ahora se guardan los tres juntos, en orden.
        """
        def _persist():
            with _GUARDAR_LOCK:
                cfg = load_cfg()
                cfg['theme'] = T.THEME
                cfg['accent'] = T.ACCENT_NAME
                propio = T.ACCENTS.get('propio')
                if propio:
                    cfg['accent_hex'] = propio[1][0]
                else:
                    cfg.pop('accent_hex', None)
                cfg['scale'] = round(self.user_scale, 3)
                save_cfg(cfg, durable=False)
        threading.Thread(target=_persist, daemon=True).start()
