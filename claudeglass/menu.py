# -*- coding: utf-8 -*-
"""Menu de clic derecho y piezas comunes de las ventanas."""

import tkinter as tk

from . import tema as T
from .tema import px, ACCENTS, HAVE_PIL, Image, ImageDraw, ImageTk
from .canal import VERSION, PRUEBA
from .config import load_cfg
from .api import nombre_org
from .sistema import work_area, round_corners, _mi_ruta, autostart_estado


class Menu:
    """Menu de clic derecho y piezas comunes de las ventanas."""

    # ---- menu contextual (dibujado a mano, no el nativo de Windows) ----
    def _close_menu(self, e=None):
        w = getattr(self, '_menu_win', None)
        self._menu_win = None
        if w is not None:
            try:
                w.grab_release()
            except Exception:
                pass
            try:
                w.destroy()
            except Exception:
                pass

    def _place(self, win, x, y):
        """Coloca una ventana junto a (x, y) sin que se salga del monitor.

        Si no cabe hacia abajo o hacia la derecha, se abre en sentido
        contrario; y como ultimo recurso se pega al borde del area util.
        """
        try:
            win.update_idletasks()
            w = max(win.winfo_reqwidth(), win.winfo_width())
            h = max(win.winfo_reqheight(), win.winfo_height())
            wa = work_area(x, y)
            if wa:
                l, t, r, b = wa
            else:
                l, t = 0, 0
                r, b = win.winfo_screenwidth(), win.winfo_screenheight()
            x, y = int(x), int(y)
            if x + w > r:                  # no cabe a la derecha -> a la izq.
                x -= w
            if y + h > b:                  # no cabe abajo -> hacia arriba
                y -= h
            x = max(l, min(x, r - w))      # y nunca fuera del area util
            y = max(t, min(y, b - h))
            win.geometry(f'{w}x{h}+{x}+{y}')
        except Exception:
            try:
                win.geometry(f'+{int(x)}+{int(y)}')
            except Exception:
                pass

    def _punto_img(self, activo, fondo):
        """Circulito del interruptor, dibujado con Pillow y cacheado.

        Vacio = apagado, relleno = encendido. El canvas de tkinter dibuja los
        ovalos con el borde dentado; asi sale con el canto limpio.
        """
        d = px(13)
        key = (d, bool(activo), fondo, T.MENU_ACCENT, T.MENU_MUTED)
        cache = getattr(self, '_punto_cache', None)
        if cache is None:
            cache = self._punto_cache = {}
        if key in cache:
            return cache[key]
        if not HAVE_PIL:
            return None
        SS = 4
        img = Image.new('RGB', (d * SS, d * SS), fondo)
        g = ImageDraw.Draw(img)
        caja = [SS, SS, d * SS - SS - 1, d * SS - SS - 1]
        if activo:
            g.ellipse(caja, fill=T.MENU_ACCENT, outline=T.MENU_ACCENT, width=SS)
        else:
            g.ellipse(caja, fill=fondo, outline=T.MENU_MUTED, width=int(SS * 1.4))
        foto = ImageTk.PhotoImage(img.resize((d, d), Image.LANCZOS))
        if len(cache) > 16:
            cache.clear()
        cache[key] = foto
        return foto

    def _mrow(self, parent, text, cmd, mark='', muted=False, bold=False,
              punto=None):
        """Fila del menu: solo texto. La columna de iconos que habia antes
        metia ruido y no aportaba nada.

        'punto' (True/False) pinta un interruptor redondo a la derecha, en
        vez del tick, que quedaba desalineado y con los bordes sucios.
        """
        f = tk.Frame(parent, bg=T.MENU_BG, cursor='hand2')
        f.pack(fill='x')
        lt = tk.Label(f, text=text, bg=T.MENU_BG,
                      fg=(T.MENU_MUTED if muted else T.MENU_FG),
                      font=('Segoe UI', -px(12)), anchor='w')
        lt.pack(side='left', padx=(px(14), 0), pady=px(6))
        if punto is None:
            lm = tk.Label(f, text=mark, bg=T.MENU_BG, fg=T.MENU_ACCENT,
                          font=('Segoe UI', -px(11)))
        else:
            lm = tk.Label(f, bg=T.MENU_BG, bd=0, highlightthickness=0)
            lm._punto = punto
            im = self._punto_img(punto, T.MENU_BG)
            if im is not None:
                lm.configure(image=im)
                lm._img = im                      # que no se lo lleve el GC
            else:
                lm.configure(text=('●' if punto else '○'),
                             fg=(T.MENU_ACCENT if punto else T.MENU_MUTED),
                             font=('Segoe UI', -px(12)))
        lm.pack(side='right', padx=(0, px(14)))
        partes = (f, lt, lm)

        def pintar(bg):
            for p in partes:
                p.configure(bg=bg)
            # el circulito lleva su fondo dentro de la imagen: si no se
            # redibuja, al pasar el raton queda un cuadrado mas oscuro
            if punto is not None:
                im = self._punto_img(punto, bg)
                if im is not None:
                    lm.configure(image=im)
                    lm._img = im

        def entrar(_e=None):
            pintar(T.MENU_HOVER)

        def salir(_e=None):
            pintar(T.MENU_BG)

        def clic(_e=None):
            self._close_menu()
            self.root.after(1, cmd)

        for p in partes:
            p.bind('<Enter>', entrar)
            p.bind('<Leave>', salir)
            p.bind('<Button-1>', clic)
        return f

    def _msep(self, parent):
        tk.Frame(parent, bg=T.MENU_SEP, height=1).pack(
            fill='x', padx=px(12), pady=px(5))

    def _mchips(self, parent, opciones, activo, accion):
        """Fila de pastillas seleccionables. Cuatro tamanos ocupan una linea
        en vez de cuatro, y de un vistazo se ve cual esta puesto."""
        fila = tk.Frame(parent, bg=T.MENU_BG)
        fila.pack(fill='x', padx=(px(12), px(12)), pady=(px(3), px(2)))
        for etiqueta, valor in opciones:
            act = (valor == activo)
            chip = tk.Label(fila, text=etiqueta, bg=(T.MENU_HOVER if act else T.MENU_BG),
                            fg=(T.MENU_ACCENT if act else T.MENU_MUTED),
                            font=('Segoe UI', -px(12), 'bold' if act else 'normal'),
                            padx=px(9), pady=px(4), cursor='hand2')
            chip.pack(side='left', padx=(0, px(4)))
            if not act:
                chip.bind('<Enter>', lambda e, c=chip: c.configure(
                    bg=T.MENU_HOVER, fg=T.MENU_FG))
                chip.bind('<Leave>', lambda e, c=chip: c.configure(
                    bg=T.MENU_BG, fg=T.MENU_MUTED))
            chip.bind('<Button-1>', lambda e, v=valor: (
                self._close_menu(), self.root.after(1, lambda: accion(v))))
        return fila

    def _mcolores(self, parent):
        """Los colores, como puntos. Un texto por color llenaria el menu."""
        fila = tk.Frame(parent, bg=T.MENU_BG)
        fila.pack(fill='x', padx=px(12), pady=(px(6), px(5)))
        for clave, (nombre, oscuro, claro) in ACCENTS.items():
            muestra = (oscuro if T.THEME == 'dark' else claro)[0]
            act = (clave == T.ACCENT_NAME)
            punto = tk.Label(fila, text=('\u25c9' if act else '\u25cf'),
                             bg=T.MENU_BG, fg=muestra,
                             font=('Segoe UI', -px(24 if act else 20)),
                             padx=px(4), pady=px(2), cursor='hand2')
            punto.pack(side='left')
            punto.bind('<Button-1>', lambda e, k=clave: (
                self._close_menu(),
                self.root.after(1, lambda: self._set_accent(k))))
            punto.bind('<Enter>', lambda e, c=punto: c.configure(bg=T.MENU_HOVER))
            punto.bind('<Leave>', lambda e, c=punto: c.configure(bg=T.MENU_BG))
        return fila

    def _popup(self, e=None):
        self._panel_ocultar()
        self._close_menu()
        m = tk.Toplevel(self.root)
        self._menu_win = m
        m.overrideredirect(True)
        m.attributes('-topmost', True)
        m.configure(bg=T.MENU_BD)
        body = tk.Frame(m, bg=T.MENU_BG)
        body.pack(fill='both', expand=True, padx=1, pady=1)

        hd = tk.Frame(body, bg=T.MENU_BG)
        hd.pack(fill='x', padx=px(14), pady=(px(10), px(8)))
        tk.Label(hd, text='ClaudeGlass', bg=T.MENU_BG, fg=T.MENU_FG,
                 font=('Segoe UI', -px(14), 'bold')).pack(side='left')
        tk.Label(hd, text=(' PRUEBA' if PRUEBA else ' by Flecha'),
                 bg=T.MENU_BG, fg=T.MENU_ACCENT,
                 font=('Segoe UI', -px(13),
                       'bold' if PRUEBA else 'italic')).pack(side='left')
        tk.Label(hd, text=f'v{VERSION}', bg=T.MENU_BG, fg=T.MENU_MUTED,
                 font=('Segoe UI', -px(10))).pack(side='right')
        self._msep(body)

        nueva = getattr(self, 'nueva_version', None)
        if nueva:
            self._mrow(body, f'Instalar versión {nueva[0]}',
                       self._instalar_actualizacion, mark='nueva')
            self._msep(body)

        self._mrow(body, 'Actualizar', self.refresh)
        self._mrow(body, 'Cambiar sessionKey…', self._key_dialog)
        # elegir cuenta solo tiene sentido si hay mas de una
        cfg = load_cfg()
        if len(cfg.get('orgs') or []) > 1:
            self._mrow(body, f'Cuenta: {nombre_org(cfg) or "elegir"}…',
                       self._org_dialog)

        self._msep(body)
        self._mchips(body, [('Oscuro', 'dark'), ('Claro', 'light')],
                     T.THEME, self._set_theme)
        self._mcolores(body)
        self._mchips(body, [('80', 80), ('100', 100), ('125', 125),
                            ('150', 150), ('⋯', 'barra')],
                     int(round(self.user_scale * 100)),
                     lambda v: (self._size_dialog() if v == 'barra'
                                else self._set_scale(v / 100.0)))

        self._msep(body)
        arranca = (autostart_estado() or '').lower() == _mi_ruta().lower()
        self._mrow(body, 'Iniciar con Windows', self._toggle_autostart,
                   punto=arranca)
        self._mrow(body, 'Diagnóstico', self._info_dialog, muted=True)
        self._mrow(body, 'Cerrar', self.close, muted=True)
        tk.Frame(body, bg=T.MENU_BG, height=px(6)).pack(fill='x')

        self._place(m, getattr(e, 'x_root', self.root.winfo_x()),
                    getattr(e, 'y_root', self.root.winfo_y()))
        round_corners(m)

        m.bind('<Escape>', self._close_menu)
        try:
            m.focus_force()
        except Exception:
            pass

        def _arm(_w=m):
            if _w is getattr(self, '_menu_win', None) and _w.winfo_exists():
                _w.bind('<FocusOut>', self._close_menu)
        self.root.after(250, _arm)
        return 'break'

    # ---- piezas comunes de las ventanas --------------------------------
    def _ventana(self, titulo, ancho):
        """Ventana sin marco de Windows, con el mismo lenguaje que el menu.

        Las de antes usaban la barra de titulo del sistema y los controles
        por defecto de Tk, que no se parecen en nada al resto del widget.
        """
        w = tk.Toplevel(self.root)
        w.overrideredirect(True)
        w.attributes('-topmost', True)
        w.configure(bg=T.MENU_BD)
        cuerpo = tk.Frame(w, bg=T.MENU_BG)
        cuerpo.pack(fill='both', expand=True, padx=1, pady=1)

        cab = tk.Frame(cuerpo, bg=T.MENU_BG)
        cab.pack(fill='x', padx=(px(14), px(10)), pady=(px(10), px(2)))
        tk.Label(cab, text=titulo, bg=T.MENU_BG, fg=T.MENU_FG,
                 font=('Segoe UI', -px(13), 'bold')).pack(side='left')
        cerrar = tk.Label(cab, text='\u2715', bg=T.MENU_BG, fg=T.MENU_MUTED,
                          font=('Segoe UI', -px(12)), cursor='hand2')
        cerrar.pack(side='right')
        cerrar.bind('<Button-1>', lambda e: w.destroy())
        cerrar.bind('<Enter>', lambda e: cerrar.configure(fg=T.CLOSE_HOV))
        cerrar.bind('<Leave>', lambda e: cerrar.configure(fg=T.MENU_MUTED))

        # se puede arrastrar por la cabecera, ya que no hay barra de titulo
        def baja(ev):
            w._ox, w._oy = ev.x_root - w.winfo_x(), ev.y_root - w.winfo_y()

        def mueve(ev):
            w.geometry(f'+{ev.x_root - w._ox}+{ev.y_root - w._oy}')
        for z in (cab,) + tuple(cab.winfo_children()[:1]):
            z.bind('<Button-1>', baja)
            z.bind('<B1-Motion>', mueve)

        w.bind('<Escape>', lambda e: w.destroy())
        w._cuerpo = cuerpo
        w._ancho = ancho
        return w

    def _boton(self, parent, texto, cmd, primario=False):
        b = tk.Label(parent, text=texto, cursor='hand2',
                     bg=(T.MENU_ACCENT if primario else T.MENU_HOVER),
                     fg=(T.TEXT_ON_FILL if primario else T.MENU_FG),
                     font=('Segoe UI', -px(12), 'bold' if primario else 'normal'),
                     padx=px(16), pady=px(7))
        b.bind('<Button-1>', lambda e: cmd())
        if not primario:
            b.bind('<Enter>', lambda e: b.configure(bg=T.MENU_SEP))
            b.bind('<Leave>', lambda e: b.configure(bg=T.MENU_HOVER))
        return b
