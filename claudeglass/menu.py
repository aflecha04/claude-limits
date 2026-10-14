# -*- coding: utf-8 -*-
"""Menu de clic derecho y piezas comunes de las ventanas."""

import tkinter as tk
import tkinter.font as tkfont

from . import tema as T
from .tema import px, ACCENTS, HAVE_PIL, Image, ImageDraw, ImageTk
from .canal import VERSION, PRUEBA
from .config import load_cfg
from .api import nombre_org, nombre_corto_org
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

    # ---- piezas del menu ----------------------------------------------
    # Todas se dibujan a mano con el mismo lenguaje: filas con icono a la
    # izquierda y detalle a la derecha, secciones con titulo pequeno, y los
    # controles (tema, tamano, interruptor, colores) como piezas suaves de
    # Pillow en vez de caracteres sueltos.
    ICONOS = {'actualizar': '', 'anadir': '', 'org': '',
              'arranque': '', 'diagnostico': '',
              'cerrar': '', 'descargar': '', 'quitar': '',
              'ok': '', 'flecha': ''}

    def _fuente_iconos(self):
        """Fuente de iconos de Windows 11 (o la de Windows 10), o None."""
        if not hasattr(self, '_ficonos'):
            try:
                fams = set(tkfont.families(self.root))
            except Exception:
                fams = set()
            self._ficonos = next((f for f in ('Segoe Fluent Icons',
                                              'Segoe MDL2 Assets') if f in fams),
                                 None)
        return self._ficonos

    def _img_cache(self, clave, dibujar, w, h, fondo):
        """Imagen Pillow con supersampling, cacheada por clave."""
        cache = getattr(self, '_mimg_cache', None)
        if cache is None:
            cache = self._mimg_cache = {}
        clave = (clave, w, h, fondo)
        if clave in cache:
            return cache[clave]
        if not HAVE_PIL:
            return None
        SS = 4
        img = Image.new('RGB', (w * SS, h * SS), fondo)
        dibujar(ImageDraw.Draw(img), SS)
        foto = ImageTk.PhotoImage(img.resize((w, h), Image.LANCZOS))
        if len(cache) > 64:
            cache.clear()
        cache[clave] = foto
        return foto

    def _interruptor_img(self, activo, fondo):
        """Interruptor tipo Windows 11: pastilla con bolita."""
        w, h = px(30), px(16)

        def dib(d, SS):
            caja = [SS, SS, w * SS - SS, h * SS - SS]
            r = (h * SS - 2 * SS) // 2
            if activo:
                d.rounded_rectangle(caja, radius=r, fill=T.MENU_ACCENT)
                bola = T.TEXT_ON_FILL
                cx = w * SS - SS - r
            else:
                d.rounded_rectangle(caja, radius=r, fill=fondo,
                                    outline=T.MENU_MUTED, width=int(SS * 1.2))
                bola = T.MENU_MUTED
                cx = SS + r
            rb = r - int(SS * 3.2)
            cy = h * SS // 2
            d.ellipse([cx - rb, cy - rb, cx + rb, cy + rb], fill=bola)
        return self._img_cache(('sw', activo, T.MENU_ACCENT, T.MENU_MUTED,
                                T.TEXT_ON_FILL), dib, w, h, fondo)

    def _avatar_img(self, letra, fondo):
        """Circulo del color elegido con la inicial de la cuenta."""
        d_ = px(34)

        def dib(d, SS):
            d.ellipse([0, 0, d_ * SS - 1, d_ * SS - 1], fill=T.MENU_ACCENT)
        return self._img_cache(('av', T.MENU_ACCENT), dib, d_, d_, fondo)

    def _color_img(self, color, activo, fondo):
        d_ = px(22)

        def dib(d, SS):
            n = d_ * SS
            if activo:
                d.ellipse([0, 0, n - 1, n - 1], outline=T.MENU_FG,
                          width=int(SS * 1.6))
            m = int(n * 0.22)
            d.ellipse([m, m, n - 1 - m, n - 1 - m], fill=color)
        return self._img_cache(('col', color, activo, T.MENU_FG), dib,
                               d_, d_, fondo)

    def _mrow(self, parent, text, cmd, mark='', muted=False, bold=False,
              punto=None, icono=None, detalle=None, quitar=None,
              acento=False):
        """Fila del menu: icono, texto, y a la derecha un detalle, una marca
        o un interruptor ('punto' True/False). 'quitar' anade una X que
        solo aparece al pasar el raton."""
        f = tk.Frame(parent, bg=T.MENU_BG, cursor='hand2')
        f.pack(fill='x', padx=px(6))
        partes = [f]
        color = (T.MENU_ACCENT if acento else
                 T.MENU_MUTED if muted else T.MENU_FG)
        fi = self._fuente_iconos()
        if icono and fi:
            li = tk.Label(f, text=self.ICONOS.get(icono, icono), bg=T.MENU_BG,
                          fg=(T.MENU_ACCENT if acento else T.MENU_MUTED),
                          font=(fi, -px(13)), width=2)
            li.pack(side='left', padx=(px(8), 0))
            partes.append(li)
        lt = tk.Label(f, text=text, bg=T.MENU_BG, fg=color, anchor='w',
                      font=('Segoe UI', -px(12), 'bold' if (bold or acento)
                            else 'normal'))
        lt.pack(side='left', padx=(px(6) if (icono and fi) else px(12), 0),
                pady=px(7))
        partes.append(lt)

        lq = None
        if quitar is not None:
            lq = tk.Label(f, text=(self.ICONOS['quitar'] if fi else '✕'),
                          bg=T.MENU_BG, fg=T.MENU_BG,
                          font=((fi, -px(10)) if fi else ('Segoe UI', -px(11))))
            lq.pack(side='right', padx=(0, px(10)))
            lq.bind('<Button-1>', lambda e: (self._close_menu(),
                                             self.root.after(1, quitar),
                                             'break')[-1])

        lm = None
        if punto is not None:
            lm = tk.Label(f, bg=T.MENU_BG, bd=0, highlightthickness=0)
            im = self._interruptor_img(punto, T.MENU_BG)
            if im is not None:
                lm.configure(image=im)
                lm._img = im
            else:
                lm.configure(text=('●' if punto else '○'),
                             fg=(T.MENU_ACCENT if punto else T.MENU_MUTED))
        elif mark or detalle:
            lm = tk.Label(f, text=(mark or detalle), bg=T.MENU_BG,
                          fg=(T.MENU_ACCENT if mark else T.MENU_MUTED),
                          font=('Segoe UI', -px(11)))
        if lm is not None:
            lm.pack(side='right', padx=(0, px(12) if lq is None else px(4)))
            partes.append(lm)

        def pintar(bg):
            for p in partes:
                p.configure(bg=bg)
            if lq is not None:
                lq.configure(bg=bg, fg=(T.MENU_MUTED if bg != T.MENU_BG
                                        else T.MENU_BG))
            # el interruptor lleva su fondo dentro de la imagen
            if punto is not None and lm is not None:
                im = self._interruptor_img(punto, bg)
                if im is not None:
                    lm.configure(image=im)
                    lm._img = im

        def clic(_e=None):
            self._close_menu()
            self.root.after(1, cmd)

        for p in partes:
            p.bind('<Enter>', lambda e: pintar(T.MENU_HOVER), add='+')
            p.bind('<Leave>', lambda e: pintar(T.MENU_BG), add='+')
            p.bind('<Button-1>', clic)
        if lq is not None:
            lq.bind('<Enter>', lambda e: (pintar(T.MENU_HOVER),
                                          lq.configure(fg=T.CLOSE_HOV)))
            lq.bind('<Leave>', lambda e: pintar(T.MENU_BG))
        return f

    def _msep(self, parent):
        tk.Frame(parent, bg=T.MENU_SEP, height=1).pack(
            fill='x', padx=px(14), pady=px(6))

    def _mseccion(self, parent, texto):
        tk.Label(parent, text=texto.upper(), bg=T.MENU_BG, fg=T.MENU_MUTED,
                 font=('Segoe UI', -px(9), 'bold'), anchor='w').pack(
                     fill='x', padx=px(18), pady=(px(2), px(3)))

    def _mlinea(self, parent, etiqueta):
        """Fila 'Etiqueta ........ control'. Devuelve el hueco del control."""
        f = tk.Frame(parent, bg=T.MENU_BG)
        f.pack(fill='x', padx=(px(18), px(14)), pady=px(4))
        tk.Label(f, text=etiqueta, bg=T.MENU_BG, fg=T.MENU_FG,
                 font=('Segoe UI', -px(12))).pack(side='left')
        hueco = tk.Frame(f, bg=T.MENU_BG)
        hueco.pack(side='right')
        return hueco

    def _mchips(self, parent, opciones, activo, accion):
        """Control segmentado: una pastilla hundida con la opcion activa
        en relieve, como los selectores de Windows 11."""
        caja = tk.Frame(parent, bg=T.TRACK, padx=px(2), pady=px(2))
        caja.pack(side='right')
        for etiqueta, valor in opciones:
            act = (valor == activo)
            fondo = T.MENU_HOVER if act else T.TRACK
            chip = tk.Label(caja, text=etiqueta, bg=fondo,
                            fg=(T.MENU_FG if act else T.MENU_MUTED),
                            font=('Segoe UI', -px(11), 'bold' if act else 'normal'),
                            padx=px(8), pady=px(3), cursor='hand2')
            chip.pack(side='left')
            if not act:
                chip.bind('<Enter>', lambda e, c=chip: c.configure(fg=T.MENU_FG))
                chip.bind('<Leave>', lambda e, c=chip: c.configure(fg=T.MENU_MUTED))
            chip.bind('<Button-1>', lambda e, v=valor: (
                self._close_menu(), self.root.after(1, lambda: accion(v))))
        return caja

    def _mcolores(self, parent):
        """Los colores, como circulos limpios; el elegido lleva un aro."""
        fila = tk.Frame(parent, bg=T.MENU_BG)
        fila.pack(side='right')
        for clave, (nombre, oscuro, claro) in ACCENTS.items():
            muestra = (oscuro if T.THEME == 'dark' else claro)[0]
            act = (clave == T.ACCENT_NAME)
            im = self._color_img(muestra, act, T.MENU_BG)
            if im is not None:
                punto = tk.Label(fila, image=im, bg=T.MENU_BG, bd=0,
                                 cursor='hand2')
                punto._img = im
            else:
                punto = tk.Label(fila, text='●', fg=muestra,
                                 bg=T.MENU_BG, cursor='hand2')
            punto.pack(side='left', padx=(px(1), 0))
            punto.bind('<Button-1>', lambda e, k=clave: (
                self._close_menu(),
                self.root.after(1, lambda: self._set_accent(k))))
        return fila

    def _mcabecera(self, parent, cfg):
        """Cuenta activa arriba del todo: inicial, nombre y correo."""
        activa = next((c for c in cfg.get('cuentas') or []
                       if c.get('id') == cfg.get('cuenta_activa')), None)
        hd = tk.Frame(parent, bg=T.MENU_BG)
        hd.pack(fill='x', padx=px(14), pady=(px(12), px(6)))
        if activa is not None:
            nombre = activa.get('nombre') or 'Tu cuenta'
            correo = activa.get('email') or ''
        else:
            nombre, correo = 'Sin cuenta', 'Inicia sesión para empezar'
        av = tk.Label(hd, bg=T.MENU_BG, bd=0, compound='center',
                      text=(nombre[:1].upper() if activa else '?'),
                      fg=T.TEXT_ON_FILL, font=('Segoe UI', -px(14), 'bold'))
        im = self._avatar_img(nombre[:1], T.MENU_BG)
        if im is not None:
            av.configure(image=im)
            av._img = im
        av.pack(side='left')
        txt = tk.Frame(hd, bg=T.MENU_BG)
        txt.pack(side='left', fill='x', expand=True, padx=(px(10), 0))
        fila = tk.Frame(txt, bg=T.MENU_BG)
        fila.pack(fill='x')
        tk.Label(fila, text=nombre, bg=T.MENU_BG, fg=T.MENU_FG, anchor='w',
                 font=('Segoe UI', -px(13), 'bold')).pack(side='left')
        tk.Label(fila, text=(f'PRUEBA {VERSION}' if PRUEBA else f'v{VERSION}'),
                 bg=T.MENU_BG, fg=(T.MENU_ACCENT if PRUEBA else T.MENU_MUTED),
                 font=('Segoe UI', -px(9), 'bold' if PRUEBA else 'normal')).pack(
                     side='right')
        tk.Label(txt, text=correo, bg=T.MENU_BG, fg=T.MENU_MUTED, anchor='w',
                 font=('Segoe UI', -px(11))).pack(fill='x')

    def _popup(self, e=None):
        self._panel_ocultar()
        self._close_menu()
        cfg = load_cfg()
        m = tk.Toplevel(self.root)
        self._menu_win = m
        m.overrideredirect(True)
        m.attributes('-topmost', True)
        m.configure(bg=T.MENU_BD)
        body = tk.Frame(m, bg=T.MENU_BG, width=px(290))
        body.pack(fill='both', expand=True, padx=1, pady=1)

        self._mcabecera(body, cfg)

        nueva = getattr(self, 'nueva_version', None)
        if nueva:
            self._mrow(body, f'Instalar versión {nueva[0]}',
                       self._instalar_actualizacion, icono='descargar',
                       acento=True)

        # cuentas: con una sola, la cabecera ya dice cual es
        cuentas = cfg.get('cuentas') or []
        self._msep(body)
        if len(cuentas) > 1:
            self._mseccion(body, 'Cuentas')
            for c in cuentas:
                activa = c.get('id') == cfg.get('cuenta_activa')
                self._mrow(body, c.get('nombre') or c.get('email') or 'Cuenta',
                           (lambda cid=c['id']: self._cambiar_cuenta(cid)),
                           icono=('ok' if activa else ' '), bold=activa,
                           detalle=(c.get('email') or '').split('@')[-1],
                           quitar=(lambda cid=c['id']: self._quitar_cuenta(cid)))
        self._mrow(body, ('Añadir otra cuenta' if cuentas else 'Iniciar sesión'),
                   self._login_dialog, icono='anadir')
        if len(cfg.get('orgs') or []) > 1:
            org = nombre_corto_org(nombre_org(cfg)) or 'elegir'
            self._mrow(body, 'Organización', self._org_dialog, icono='org',
                       detalle=(org if len(org) <= 18 else org[:17] + '…'))

        self._msep(body)
        self._mseccion(body, 'Apariencia')
        self._mchips(self._mlinea(body, 'Tema'),
                     [('Oscuro', 'dark'), ('Claro', 'light')],
                     T.THEME, self._set_theme)
        self._mcolores(self._mlinea(body, 'Color'))
        self._mchips(self._mlinea(body, 'Tamaño'),
                     [('80', 80), ('100', 100), ('125', 125), ('150', 150),
                      ('⋯', 'barra')],
                     int(round(self.user_scale * 100)),
                     lambda v: (self._size_dialog() if v == 'barra'
                                else self._set_scale(v / 100.0)))

        self._msep(body)
        self._mrow(body, 'Actualizar ahora', self.refresh, icono='actualizar')
        arranca = (autostart_estado() or '').lower() == _mi_ruta().lower()
        self._mrow(body, 'Iniciar con Windows', self._toggle_autostart,
                   icono='arranque', punto=arranca)
        self._mrow(body, 'Diagnóstico', self._info_dialog, icono='diagnostico',
                   muted=True)
        self._mrow(body, 'Cerrar', self.close, icono='cerrar', muted=True)
        tk.Frame(body, bg=T.MENU_BG, height=px(6)).pack(fill='x')

        # ancho fijo: que no baile segun el nombre de la cuenta
        m.update_idletasks()
        ancho = max(px(290), body.winfo_reqwidth() + 2)
        m.geometry(f'{ancho}x{body.winfo_reqheight() + 2}')

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
