# -*- coding: utf-8 -*-
"""Panel que se despliega al pasar el raton: limite semanal y por modelo."""

import tkinter as tk

from . import tema as T
from .tema import px, _hex, Image, ImageDraw, ImageTk
from .api import (cuota, campos_de_modelo, nombre_de_modelo, countdown,
                  ritmo, PERIODO_SEMANA)
from .sistema import work_area, round_corners


class Panel:
    """Panel flotante con el limite semanal y los modelos."""

    # ---- panel flotante (semanal y modelos) ----------------------------
    HOVER_ABRIR_MS = 450        # tiempo parado encima antes de desplegar
    HOVER_CERRAR_MS = 260       # margen para poder mover el raton al panel

    def _hover_programar_apertura(self, e=None):
        self._hover_cancelar(cerrar=True)
        if getattr(self, '_arrastrando', False):
            return
        self._hover_abrir_id = self.root.after(self.HOVER_ABRIR_MS,
                                               self._panel_mostrar)

    def _hover_programar_cierre(self, e=None):
        self._hover_cancelar(abrir=True)
        self._hover_cerrar_id = self.root.after(self.HOVER_CERRAR_MS,
                                                self._panel_ocultar)

    def _hover_cancelar(self, abrir=False, cerrar=False):
        if abrir or not cerrar:
            i = getattr(self, '_hover_abrir_id', None)
            if i:
                try:
                    self.root.after_cancel(i)
                except Exception:
                    pass
                self._hover_abrir_id = None
        if cerrar or not abrir:
            i = getattr(self, '_hover_cerrar_id', None)
            if i:
                try:
                    self.root.after_cancel(i)
                except Exception:
                    pass
                self._hover_cerrar_id = None

    def _panel_ocultar(self, e=None):
        self._hover_cancelar()
        w = getattr(self, '_panel', None)
        self._panel = None
        if w is not None:
            try:
                w.destroy()
            except Exception:
                pass

    def _panel_maqueta(self, n):
        """Coordenadas de la maqueta, en pixeles logicos. Las comparten el
        fondo (Pillow) y los textos (tkinter), para que encajen exactos."""
        MARGEN, GAP, ALTO = px(14), px(10), px(84)
        ancho = max(T.W, px(290))
        filas = []
        for i in range(n):
            y = MARGEN + i * (ALTO + GAP)
            # y_tit e y_num son CENTROS de linea: asi el titulo y la cuenta
            # atras quedan alineados aunque tengan tamanos distintos.
            filas.append(dict(
                x0=MARGEN, x1=ancho - MARGEN, y0=y, y1=y + ALTO,
                tx0=MARGEN + px(14), tx1=ancho - MARGEN - px(14),
                y_tit=y + px(16), y_num=y + px(38),
                y_bar=y + px(54), alto_bar=px(8), y_prev=y + px(72)))
        return ancho, MARGEN * 2 + n * ALTO + max(0, n - 1) * GAP, filas

    def _panel_img(self, filas):
        """Solo las formas: piezas y barras. El texto lo pone tkinter encima,
        que lo dibuja con el suavizado del sistema en vez de reducirlo
        desde una imagen a 4x."""
        clave = (T.THEME, T.ACCENT_NAME, T.W, T.UI,
                 tuple((round(p, 1), self._ritmo_de(p, r, per)[:2])
                       for _t, p, r, per in filas))
        cache = getattr(self, '_panel_cache', None)
        if cache is None:
            cache = self._panel_cache = {}
        hit = cache.get(clave)
        if hit is not None:
            self._panel_photo = hit[0]
            return hit

        SS = self.SS
        ancho, alto, maqueta = self._panel_maqueta(len(filas))
        img = Image.new('RGBA', (ancho * SS, alto * SS),
                        _hex(T.PANEL_BG or T.TINT) + (255,))
        d = ImageDraw.Draw(img)
        for (_titulo, pct, res, periodo), m in zip(filas, maqueta):
            tiempo, adelantado, _prev = self._ritmo_de(pct, res, periodo)
            d.rounded_rectangle([m['x0'] * SS, m['y0'] * SS,
                                 m['x1'] * SS, m['y1'] * SS],
                                radius=px(12) * SS, fill=T.TINT,
                                outline=T.TILE_BD, width=SS)
            bx0, bx1 = m['tx0'] * SS, m['tx1'] * SS
            by0 = m['y_bar'] * SS
            bh = m['alto_bar'] * SS
            br = bh // 2
            d.rounded_rectangle([bx0, by0, bx1, by0 + bh], radius=br,
                                fill=T.TRACK)
            if pct and pct > 0:
                total = bx1 - bx0
                relleno = max(bh, int(round(total * min(pct, 100) / 100.0)))
                color = T.ROJO if adelantado else T.BAR_START
                d.rounded_rectangle([bx0, by0, bx0 + relleno - 1, by0 + bh - 1],
                                    radius=br, fill=color)
            if tiempo is not None and 0 < tiempo < 100:
                xm = int(bx0 + (bx1 - bx0) * tiempo / 100.0)
                a = max(SS, px(2) * SS // 2 * 2)
                # sobre el relleno, en el color del texto de encima del relleno
                # (con el color blanco, una raya blanca no se veia)
                lleno = pct and xm <= bx0 + (bx1 - bx0) * min(pct, 100) / 100.0
                d.rounded_rectangle([xm - a // 2, by0 - SS * 2, xm + a // 2,
                                     by0 + bh + SS * 2], radius=a // 2,
                                    fill=(('#ffffff' if adelantado else T.TEXT_ON_FILL)
                                          if lleno else T.MENU_FG))

        out = img.resize((ancho, alto), Image.LANCZOS).convert('RGB')
        self._panel_photo = ImageTk.PhotoImage(out)
        if len(cache) > 8:
            cache.clear()
        res = (self._panel_photo, ancho, alto)
        cache[clave] = res
        return res

    @staticmethod
    def _ritmo_de(pct, res, periodo):
        """(tiempo_pct, adelantado, prevision), con valores vacios si no hay."""
        return ritmo(pct, res, periodo) or (None, False, '')

    def _panel_filas(self):
        """[(titulo, pct, resets_at, periodo)] de los limites que NO son
        el de 5 h."""
        u = getattr(self, 'usage', None) or {}
        filas = []
        pct, res = cuota(u, 'seven_day')
        if pct is not None:
            filas.append(('Límite semanal', pct, res, PERIODO_SEMANA))
        for campo in sorted(campos_de_modelo(u)):
            if campo == 'seven_day':
                continue
            pct, res = cuota(u, campo)
            if pct is not None:
                filas.append((nombre_de_modelo(u, campo), pct, res,
                               PERIODO_SEMANA))
        return filas

    def _panel_tarjetas(self):
        """Lo que se ve en el panel: los limites semanales. La sesion de 5 h
        no, que ya esta en la barra (con su rayita de tiempo)."""
        return self._panel_filas()

    def _limite_agotado(self):
        """True si algun limite del panel (semanal o de un modelo) esta al 100 %."""
        try:
            return any(f[1] >= 100 for f in self._panel_filas())
        except Exception:
            return False

    def _panel_mostrar(self, e=None):
        self._hover_cancelar()
        if getattr(self, '_panel', None) is not None or getattr(self, '_menu_win', None):
            return
        if getattr(self, '_arrastrando', False):
            return
        filas = self._panel_tarjetas()
        self._panel_firma_actual = self._panel_firma()

        w = tk.Toplevel(self.root)
        self._panel = w
        w.overrideredirect(True)
        w.attributes('-topmost', True)
        w.configure(bg=(T.TILE_BD or T.CARD_BD))

        if filas:
            foto, pw, ph = self._panel_img(filas)
            c = tk.Canvas(w, width=pw, height=ph, bg=(T.PANEL_BG or T.TINT),
                          highlightthickness=0, bd=0)
            c.pack()
            c.create_image(0, 0, anchor='nw', image=foto)
            _a, _h, maqueta = self._panel_maqueta(len(filas))
            dy_t = self._dy_optico(self.f_ptit)
            dy_n = self._dy_optico(self.f_pnum)
            for (titulo, pct, res, periodo), m in zip(filas, maqueta):
                # un limite agotado lo dice con palabras: 'Agotado' en vez
                # de '100%', y cuando vuelve en vez de solo el tiempo
                agotado = pct >= 100
                c.create_text(m['tx0'], m['y_tit'] + dy_t, text=titulo,
                              anchor='w', fill=T.MENU_MUTED, font=self.f_ptit)
                if res:
                    c.create_text(m['tx1'], m['y_tit'] + dy_t,
                                  text=(f'vuelve en {countdown(res)}'
                                        if agotado else countdown(res)),
                                  anchor='e',
                                  fill=(T.MENU_FG if agotado else T.MENU_MUTED),
                                  font=self.f_pcd)
                c.create_text(m['tx0'], m['y_num'] + dy_n,
                              text=('Agotado' if agotado else f'{pct:.0f}%'),
                              anchor='w', fill=T.MENU_FG, font=self.f_pnum)
                _t, adelantado, prev = self._ritmo_de(pct, res, periodo)
                if prev:
                    c.create_text(m['tx0'], m['y_prev'] + dy_t, text=prev,
                                  anchor='w', font=self.f_ptit,
                                  fill=(T.ROJO if 'se agota' in prev
                                        else T.MENU_MUTED))
            hijos = (c,)
        else:
            pw = max(T.W, px(290))
            marco = tk.Frame(w, bg=T.TINT)
            marco.pack(fill='both', expand=True)
            tk.Label(marco, text='Sin límite semanal', bg=T.TINT, fg=T.INK,
                     font=(T.FUENTE, -px(12), 'bold'), anchor='w').pack(
                         fill='x', padx=px(16), pady=(px(16), 0))
            tk.Label(marco, text='Tu cuenta no informa de cuota semanal,\n'
                               'o aún no se ha podido consultar.',
                     bg=T.TINT, fg=T.SUBTLE, font=(T.FUENTE, -px(11)),
                     justify='left', anchor='w').pack(
                         fill='x', padx=px(16), pady=(2, px(16)))
            hijos = (marco,)
            w.update_idletasks()
            ph = w.winfo_reqheight()

        def marcar(_e=None):
            self._hover_cancelar(abrir=True)
        w.bind('<Enter>', marcar)
        w.bind('<Leave>', self._hover_programar_cierre)
        for h in hijos:
            h.bind('<Enter>', marcar)
            h.bind('<Leave>', self._hover_programar_cierre)

        # Pegado al widget: 8 px por debajo, o por encima si no cabe.
        # Se calcula aqui y se fija tal cual; pasar por _place aplicaria un
        # segundo volteo y el panel acababa lejisimos del widget.
        wx, wy = self.root.winfo_x(), self.root.winfo_y()
        hueco = px(8)
        wa = work_area(wx + T.W // 2, wy) or (0, 0,
                                            w.winfo_screenwidth(),
                                            w.winfo_screenheight())
        l, t, r, b = wa
        y = wy + T.H + hueco
        if y + ph > b:                      # no cabe debajo -> encima
            y = wy - ph - hueco
        y = max(t, min(y, b - ph))
        x = max(l, min(wx, r - pw))         # alineado al borde izq. del widget
        w.geometry(f'{pw}x{ph}+{int(x)}+{int(y)}')
        round_corners(w)

    def _panel_refrescar(self):
        """Redibuja el panel abierto SOLO si cambia algo que se vea.

        Reconstruirlo en cada actualizacion lo haria parpadear a la vista.
        """
        if getattr(self, '_panel', None) is None:
            return
        firma = self._panel_firma()
        if firma == getattr(self, '_panel_firma_actual', None):
            return
        try:
            self._panel_ocultar()
            self._panel_mostrar()
        except Exception:
            pass

    def _panel_firma(self):
        firma = [T.THEME, T.ACCENT_NAME, T.BAR_START, T.UI]
        for t, p, r, per in self._panel_tarjetas():
            tiempo, adelantado, prev = self._ritmo_de(p, r, per)
            firma.append((t, round(p, 1), countdown(r), adelantado, prev,
                          round(tiempo or 0)))
        return tuple(firma)
