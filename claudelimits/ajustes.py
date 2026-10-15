# -*- coding: utf-8 -*-
"""Tamano, color y tema del widget."""

import threading
import tkinter as tk

from . import tema as T
from .tema import (apply_theme, apply_accent, apply_scale, px, mpx,
                   Image, ImageDraw, ImageTk)
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
        ancho = mpx(280)
        w = self._ventana('Tamaño', ancho)
        self._szdlg = w
        cuerpo = w._cuerpo
        MIN, MAX = 70, 200

        # El numero grande: un clic y se puede escribir a mano
        hueco = tk.Frame(cuerpo, bg=T.MENU_BG, height=mpx(52))
        hueco.pack(fill='x', pady=(mpx(4), 0))
        hueco.pack_propagate(False)
        fuente_num = (T.FUENTE, -mpx(30), 'bold')
        valor = tk.Label(hueco, bg=T.MENU_BG, fg=T.MENU_FG, font=fuente_num,
                         cursor='xterm')
        valor.pack(expand=True)
        pista = tk.Label(cuerpo, text='Pulsa el número para editar',
                         bg=T.MENU_BG, fg=T.MENU_MUTED, font=(T.FUENTE, -mpx(10)))
        pista.pack(pady=(0, mpx(6)))

        # Deslizador dibujado con Pillow (bordes suaves). El de antes iba con
        # el lienzo de Tk, que dibuja los circulos con dientes de sierra.
        cw, ch = ancho - mpx(40), mpx(28)
        lienzo = tk.Canvas(cuerpo, width=cw, height=ch, bg=T.MENU_BG,
                           highlightthickness=0, bd=0, cursor='hand2')
        lienzo.pack(padx=mpx(20))
        r = mpx(9)

        def actual():
            return int(round(self.user_scale * 100))

        def pinta():
            v = actual()
            valor.config(text=f'{v} %')
            SS = 4
            img = Image.new('RGB', (cw * SS, ch * SS), T.MENU_BG)
            d = ImageDraw.Draw(img)
            cy, g = ch * SS // 2, mpx(6) * SS
            x0, x1 = r * SS, (cw - r) * SS
            d.rounded_rectangle([x0 - g // 2, cy - g // 2, x1 + g // 2, cy + g // 2],
                                radius=g // 2, fill=T.TRACK)
            x = x0 + (x1 - x0) * (v - MIN) / (MAX - MIN)
            d.rounded_rectangle([x0 - g // 2, cy - g // 2, x + g // 2, cy + g // 2],
                                radius=g // 2, fill=T.MENU_ACCENT)
            ro = r * SS
            d.ellipse([x - ro, cy - ro, x + ro, cy + ro], fill=T.MENU_ACCENT)
            ri = int(ro * 0.42)
            d.ellipse([x - ri, cy - ri, x + ri, cy + ri], fill=T.TEXT_ON_FILL)
            foto = ImageTk.PhotoImage(img.resize((cw, ch), Image.LANCZOS))
            lienzo.delete('all')
            lienzo.create_image(0, 0, anchor='nw', image=foto)
            lienzo._foto = foto

        def poner(v):
            v = max(MIN, min(MAX, int(v)))
            if v != actual():
                self._set_scale(v / 100.0, save=False)
            pinta()

        def mueve(ev):
            t = min(1.0, max(0.0, (ev.x - r) / max(1, cw - 2 * r)))
            poner(int(round((MIN + t * (MAX - MIN)) / 5.0)) * 5)

        lienzo.bind('<Button-1>', mueve)
        lienzo.bind('<B1-Motion>', mueve)

        # escribir el numero
        edicion = {}

        def editar(_e=None):
            if edicion:
                return
            valor.pack_forget()
            caja, ent = self._campo(hueco, mpx(120), fuente_num, centrado=True)
            caja.pack(expand=True)
            ent.insert(0, str(actual()))
            ent.select_range(0, 'end')
            ent.focus_set()
            edicion['caja'] = caja

            def cerrar(aplicar=True):
                if not edicion:
                    return
                texto = ''.join(ch_ for ch_ in ent.get() if ch_.isdigit())
                edicion.clear()
                caja.destroy()
                valor.pack(expand=True)
                if aplicar and texto:
                    poner(texto)
                    if int(texto) < MIN or int(texto) > MAX:
                        pista.config(text=f'Entre {MIN} y {MAX} %', fg=T.CLOSE_HOV)
                        w.after(2500, lambda: pista.winfo_exists() and pista.config(
                            text='Pulsa el número para editar', fg=T.MENU_MUTED))
                else:
                    pinta()
            ent.bind('<Return>', lambda e: (cerrar(True), 'break')[1])
            ent.bind('<Escape>', lambda e: (cerrar(False), 'break')[1])
            ent.bind('<FocusOut>', lambda e: cerrar(True))
        valor.bind('<Button-1>', editar)
        pinta()

        ext = tk.Frame(cuerpo, bg=T.MENU_BG)
        ext.pack(fill='x', padx=mpx(20), pady=(mpx(2), 0))
        tk.Label(ext, text=f'{MIN} %', bg=T.MENU_BG, fg=T.MENU_MUTED,
                 font=(T.FUENTE, -mpx(10))).pack(side='left')
        tk.Label(ext, text=f'{MAX} %', bg=T.MENU_BG, fg=T.MENU_MUTED,
                 font=(T.FUENTE, -mpx(10))).pack(side='right')

        def hecho():
            self._guardar_apariencia()
            self._szdlg = None
            w.destroy()

        def restablecer():
            poner(100)

        bf = tk.Frame(cuerpo, bg=T.MENU_BG)
        bf.pack(fill='x', padx=mpx(20), pady=(mpx(16), mpx(16)))
        self._boton(bf, 'Hecho', hecho, primario=True).pack(side='right')
        self._boton(bf, 'Restablecer', restablecer).pack(side='right',
                                                         padx=(0, mpx(8)))
        w.protocol('WM_DELETE_WINDOW', hecho)
        self._place(w, self.root.winfo_x(), self.root.winfo_y() - mpx(230))
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
