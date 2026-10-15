# -*- coding: utf-8 -*-
"""Menu de clic derecho y piezas comunes de las ventanas."""

import tkinter as tk
import tkinter.font as tkfont

from . import tema as T
from .tema import mpx, _mix, ACCENTS, HAVE_PIL, Image, ImageDraw, ImageTk
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
        w, h = mpx(30), mpx(16)

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
        d_ = mpx(34)

        def dib(d, SS):
            d.ellipse([0, 0, d_ * SS - 1, d_ * SS - 1], fill=T.MENU_ACCENT)
        return self._img_cache(('av', T.MENU_ACCENT), dib, d_, d_, fondo)

    def _color_img(self, color, activo, fondo):
        d_ = mpx(22)

        def dib(d, SS):
            n = d_ * SS
            if activo:
                d.ellipse([0, 0, n - 1, n - 1], outline=T.MENU_FG,
                          width=int(SS * 1.6))
            m = int(n * 0.22)
            d.ellipse([m, m, n - 1 - m, n - 1 - m], fill=color)
        return self._img_cache(('col', color, activo, T.MENU_FG), dib,
                               d_, d_, fondo)

    def _rol(self, w, **roles):
        """Pinta 'w' con colores del tema por NOMBRE (bg='MENU_BG'...) y lo
        apunta para repintarlo al cambiar de tema o color sin rehacerlo."""
        def aplicar(w=w, roles=roles):
            if w.winfo_exists():
                w.configure(**{k: getattr(T, v) for k, v in roles.items()})
        aplicar()
        self._mrep.append(aplicar)
        return w

    def _color_mas_img(self, fondo):
        """Circulo vacio con un '+': hueco para el color propio."""
        d_ = mpx(22)

        def dib(d, SS):
            n = d_ * SS
            m = int(n * 0.2)
            d.ellipse([m, m, n - 1 - m, n - 1 - m], outline=T.MENU_MUTED,
                      width=int(SS * 1.2))
            c, l = n // 2, int(n * 0.16)
            d.line([(c - l, c), (c + l, c)], fill=T.MENU_MUTED, width=int(SS * 1.2))
            d.line([(c, c - l), (c, c + l)], fill=T.MENU_MUTED, width=int(SS * 1.2))
        return self._img_cache(('mas', T.MENU_MUTED), dib, d_, d_, fondo)

    def _mrow(self, parent, text, cmd, mark='', muted=False, bold=False,
              punto=None, icono=None, detalle=None, quitar=None,
              acento=False):
        """Fila del menu: icono, texto, y a la derecha un detalle, una marca
        o un interruptor ('punto': funcion que dice si esta encendido).
        'quitar' anade una X que solo aparece al pasar el raton."""
        f = tk.Frame(parent, cursor='hand2')
        f.pack(fill='x', padx=mpx(6))
        partes = [f]
        color = 'MENU_ACCENT' if acento else 'MENU_MUTED' if muted else 'MENU_FG'
        fi = self._fuente_iconos()
        li = None
        if icono and fi:
            li = tk.Label(f, text=self.ICONOS.get(icono, icono),
                          font=(fi, -mpx(13)), width=2)
            li.pack(side='left', padx=(mpx(8), 0))
            partes.append(li)
        lt = tk.Label(f, text=text, anchor='w',
                      font=(T.FUENTE, -mpx(12), 'bold' if (bold or acento)
                            else 'normal'))
        lt.pack(side='left', padx=(mpx(6) if (icono and fi) else mpx(12), 0),
                pady=mpx(7))
        partes.append(lt)

        lq = None
        if quitar is not None:
            lq = tk.Label(f, text=(self.ICONOS['quitar'] if fi else '✕'),
                          font=((fi, -mpx(10)) if fi else (T.FUENTE, -mpx(11))))
            lq.pack(side='right', padx=(0, mpx(10)))
            lq.bind('<Button-1>', lambda e: (self._close_menu(),
                                             self.root.after(1, quitar),
                                             'break')[-1])

        lm = None
        if punto is not None:
            lm = tk.Label(f, bd=0, highlightthickness=0)
        elif mark or detalle:
            lm = tk.Label(f, text=(mark or detalle), font=(T.FUENTE, -mpx(11)))
        if lm is not None:
            lm.pack(side='right', padx=(0, mpx(12) if lq is None else mpx(4)))
            partes.append(lm)

        def pintar(bg):
            for p in partes:
                p.configure(bg=bg)
            if lq is not None:
                lq.configure(bg=bg, fg=(T.MENU_MUTED if bg != T.MENU_BG
                                        else T.MENU_BG))
            # el interruptor lleva su fondo dentro de la imagen
            if punto is not None and lm is not None:
                im = self._interruptor_img(punto(), bg)
                if im is not None:
                    lm.configure(image=im)
                    lm._img = im
                else:
                    lm.configure(text=('●' if punto() else '○'),
                                 fg=(T.MENU_ACCENT if punto() else T.MENU_MUTED))

        def colores():
            if not f.winfo_exists():
                return
            pintar(T.MENU_BG)
            if li is not None:
                li.configure(fg=(T.MENU_ACCENT if acento else T.MENU_MUTED))
            lt.configure(fg=getattr(T, color))
            if lm is not None and punto is None:
                lm.configure(fg=(T.MENU_ACCENT if mark else T.MENU_MUTED))
        colores()
        self._mrep.append(colores)

        def clic(_e=None):
            if punto is not None:          # interruptor: el menu sigue abierto
                self._y_reabrir(cmd)
                return
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
        self._rol(tk.Frame(parent, height=1), bg='MENU_SEP').pack(
            fill='x', padx=mpx(14), pady=mpx(6))

    def _mseccion(self, parent, texto):
        self._rol(tk.Label(parent, text=texto.upper(), anchor='w',
                           font=(T.FUENTE, -mpx(9), 'bold')),
                  bg='MENU_BG', fg='MENU_MUTED').pack(
                      fill='x', padx=mpx(18), pady=(mpx(2), mpx(3)))

    def _mlinea(self, parent, etiqueta):
        """Fila 'Etiqueta ........ control'. Devuelve el hueco del control."""
        f = self._rol(tk.Frame(parent), bg='MENU_BG')
        f.pack(fill='x', padx=(mpx(18), mpx(14)), pady=mpx(4))
        self._rol(tk.Label(f, text=etiqueta, font=(T.FUENTE, -mpx(12))),
                  bg='MENU_BG', fg='MENU_FG').pack(side='left')
        hueco = self._rol(tk.Frame(f), bg='MENU_BG')
        hueco.pack(side='right')
        return hueco

    def _mchips(self, parent, opciones, activo, accion):
        """Control segmentado: una pastilla hundida con la opcion activa
        en relieve, como los selectores de Windows 11. 'activo' es una
        funcion: al cambiar algo, solo se repintan sus pastillas."""
        caja = tk.Frame(parent, padx=mpx(2), pady=mpx(2))
        caja.pack(side='right')
        chips = []
        for etiqueta, valor in opciones:
            chip = tk.Label(caja, text=etiqueta, padx=mpx(8), pady=mpx(3),
                            cursor='hand2')
            chip.pack(side='left')
            chip.bind('<Enter>', lambda e, c=chip, v=valor: v != activo()
                      and c.configure(fg=T.MENU_FG))
            chip.bind('<Leave>', lambda e, c=chip, v=valor: v != activo()
                      and c.configure(fg=T.MENU_MUTED))
            chip.bind('<Button-1>', lambda e, v=valor: self._y_reabrir(
                lambda: accion(v), reabrir=(v != 'barra')))
            chips.append((chip, valor))

        def pintar():
            if not caja.winfo_exists():
                return
            caja.configure(bg=T.TRACK)
            actual = activo()
            for chip, valor in chips:
                act = valor == actual
                chip.configure(bg=(T.MENU_HOVER if act else T.TRACK),
                               fg=(T.MENU_FG if act else T.MENU_MUTED),
                               font=(T.FUENTE, -mpx(11),
                                     'bold' if act else 'normal'))
        pintar()
        self._mrep.append(pintar)
        return caja

    def _mcolores(self, parent):
        """Los colores, como circulos limpios; el elegido lleva un aro."""
        fila = tk.Frame(parent)
        fila.pack(side='right')
        puntos = []
        claves = [k for k in ACCENTS if k != 'propio'] + ['propio']
        for clave in claves:
            punto = tk.Label(fila, bd=0, cursor='hand2')
            punto.pack(side='left', padx=(mpx(1), 0))
            if clave == 'propio':
                # el ultimo es el color propio: si ya hay uno guardado, el
                # primer clic lo elige; si no lo hay, o ya esta elegido, el
                # clic abre la ventanita para escribir su codigo
                punto.bind('<Button-1>', lambda e: (
                    self._y_reabrir(lambda: self._set_accent('propio'))
                    if ('propio' in ACCENTS and T.ACCENT_NAME != 'propio')
                    else self._color_dialog()))
            else:
                punto.bind('<Button-1>', lambda e, k=clave: self._y_reabrir(
                    lambda: self._set_accent(k)))
            puntos.append((punto, clave))

        def pintar():
            if not fila.winfo_exists():
                return
            fila.configure(bg=T.MENU_BG)
            for punto, clave in puntos:
                if clave == 'propio' and 'propio' not in ACCENTS:
                    im = self._color_mas_img(T.MENU_BG)
                    if im is not None:
                        punto.configure(image=im, bg=T.MENU_BG)
                        punto._img = im
                    else:
                        punto.configure(text='+', fg=T.MENU_MUTED, bg=T.MENU_BG)
                    continue
                _n, oscuro, claro = ACCENTS[clave]
                muestra = (oscuro if T.THEME == 'dark' else claro)[0]
                im = self._color_img(muestra, clave == T.ACCENT_NAME, T.MENU_BG)
                if im is not None:
                    punto.configure(image=im, bg=T.MENU_BG)
                    punto._img = im
                else:
                    punto.configure(text='●', fg=muestra, bg=T.MENU_BG)
        pintar()
        self._mrep.append(pintar)
        return fila

    def _y_reabrir(self, accion, reabrir=True):
        """Aplica un ajuste y deja el menu abierto con el cambio a la vista:
        asi se pueden tocar varias cosas seguidas (tema, color, tamano...).

        No se rehace nada: cada pieza del menu sabe repintarse (colores,
        opcion marcada, interruptor) y solo se cambia eso. Medido: rehacer
        el menu entero tardaba medio segundo en cada clic.
        """
        m = getattr(self, '_menu_win', None)
        vivo = m is not None and m.winfo_exists()
        if not (reabrir and vivo):
            self._close_menu()
            self.root.after(1, accion)
            return

        def hacer():
            # mientras cambia, perder el foco no cierra el menu
            self._menu_ocupado = True
            try:
                accion()
                if m.winfo_exists():
                    for repintar in list(getattr(self, '_mrep', [])):
                        try:
                            repintar()
                        except Exception:
                            pass
                    # cambiar el tema toca la ventana del widget y Windows le
                    # pasa el foco: se le devuelve al menu
                    try:
                        m.focus_force()
                    except Exception:
                        pass
            finally:
                self.root.after(200, lambda: setattr(self, '_menu_ocupado', False))
        self.root.after(1, hacer)

    def _mcabecera(self, parent, cfg):
        """Cuenta activa arriba del todo: inicial, nombre y correo."""
        activa = next((c for c in cfg.get('cuentas') or []
                       if c.get('id') == cfg.get('cuenta_activa')), None)
        hd = self._rol(tk.Frame(parent), bg='MENU_BG')
        hd.pack(fill='x', padx=mpx(14), pady=(mpx(12), mpx(6)))
        if activa is not None:
            nombre = activa.get('nombre') or 'Tu cuenta'
            correo = activa.get('email') or ''
        else:
            nombre, correo = 'Sin cuenta', 'Inicia sesión para empezar'
        av = tk.Label(hd, bd=0, compound='center',
                      text=(nombre[:1].upper() if activa else '?'),
                      font=(T.FUENTE, -mpx(14), 'bold'))
        av.pack(side='left')

        def avatar():
            if not av.winfo_exists():
                return
            av.configure(bg=T.MENU_BG, fg=T.TEXT_ON_FILL)
            im = self._avatar_img(nombre[:1], T.MENU_BG)
            if im is not None:
                av.configure(image=im)
                av._img = im
        avatar()
        self._mrep.append(avatar)
        txt = self._rol(tk.Frame(hd), bg='MENU_BG')
        txt.pack(side='left', fill='x', expand=True, padx=(mpx(10), 0))
        fila = self._rol(tk.Frame(txt), bg='MENU_BG')
        fila.pack(fill='x')
        self._rol(tk.Label(fila, text=nombre, anchor='w',
                           font=(T.FUENTE, -mpx(13), 'bold')),
                  bg='MENU_BG', fg='MENU_FG').pack(side='left')
        self._rol(tk.Label(fila, text=(f'PRUEBA {VERSION}' if PRUEBA else f'v{VERSION}'),
                           font=(T.FUENTE, -mpx(9), 'bold' if PRUEBA else 'normal')),
                  bg='MENU_BG', fg=('MENU_ACCENT' if PRUEBA else 'MENU_MUTED')).pack(
                      side='right')
        self._rol(tk.Label(txt, text=correo, anchor='w', font=(T.FUENTE, -mpx(11))),
                  bg='MENU_BG', fg='MENU_MUTED').pack(fill='x')

    def _popup(self, e=None):
        self._panel_ocultar()
        self._close_menu()
        m = tk.Toplevel(self.root)
        self._menu_win = m
        m.overrideredirect(True)
        m.attributes('-topmost', True)
        self._menu_llenar(m)
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
                _w.bind('<FocusOut>', self._menu_sin_foco)
        self.root.after(250, _arm)
        return 'break'

    def _menu_sin_foco(self, e=None):
        """Cierra el menu solo si el foco se ha ido de verdad (a otro
        programa o al resto del escritorio), no por un cambio interno."""
        m = getattr(self, '_menu_win', None)
        if m is None or getattr(self, '_menu_ocupado', False):
            return

        def comprobar():
            if (getattr(self, '_menu_win', None) is not m or not m.winfo_exists()
                    or getattr(self, '_menu_ocupado', False)):
                return
            try:
                f = m.focus_get()
            except Exception:
                f = None
            if f is not None:
                # el foco sigue en el widget (en el menu o en la barra, a la
                # que a veces se lo pasa Windows al repintar): no se cierra.
                # Un clic en la barra ya cierra el menu por su cuenta.
                return
            self._close_menu()             # se ha ido a otro programa
        self.root.after(120, comprobar)

    def _menu_llenar(self, m):
        """Contenido del menu. Tamano fijo: no crece con el del widget."""
        cfg = load_cfg()
        self._mrep = []                     # piezas que saben repintarse
        self._rol(m, bg='MENU_BD')
        body = self._rol(tk.Frame(m, width=mpx(290)), bg='MENU_BG')
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
                # todas iguales: se distinguen por el correo, sin suponer
                # nada por su dominio
                self._mrow(body, c.get('email') or c.get('nombre') or 'Cuenta',
                           (lambda cid=c['id']: self._cambiar_cuenta(cid)),
                           icono=('ok' if activa else ' '), bold=activa,
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
                     lambda: T.THEME, self._set_theme)
        self._mcolores(self._mlinea(body, 'Color'))
        self._mchips(self._mlinea(body, 'Tamaño'),
                     [('80', 80), ('100', 100), ('125', 125), ('150', 150),
                      ('⋯', 'barra')],
                     lambda: int(round(self.user_scale * 100)),
                     lambda v: (self._size_dialog() if v == 'barra'
                                else self._set_scale(v / 100.0)))

        self._msep(body)
        self._mrow(body, 'Actualizar ahora', self.refresh, icono='actualizar')
        self._mrow(body, 'Iniciar con Windows', self._toggle_autostart,
                   icono='arranque',
                   punto=lambda: ((autostart_estado() or '').lower()
                                  == _mi_ruta().lower()))
        self._mrow(body, 'Diagnóstico', self._info_dialog, icono='diagnostico',
                   muted=True)
        self._mrow(body, 'Cerrar', self.close, icono='cerrar', muted=True)
        self._rol(tk.Frame(body, height=mpx(6)), bg='MENU_BG').pack(fill='x')

        # ancho fijo: que no baile segun el nombre de la cuenta. Solo se
        # cambia el tamano; la posicion se queda donde estaba.
        m.update_idletasks()
        ancho = max(mpx(290), body.winfo_reqwidth() + 2)
        m.geometry(f'{ancho}x{body.winfo_reqheight() + 2}')

    # ---- piezas comunes de las ventanas --------------------------------
    def _ventana(self, titulo, ancho):
        """Ventana sin marco de Windows, con el mismo lenguaje que el menu."""
        w = tk.Toplevel(self.root)
        w.overrideredirect(True)
        w.attributes('-topmost', True)
        w.configure(bg=T.MENU_BD)
        cuerpo = tk.Frame(w, bg=T.MENU_BG)
        cuerpo.pack(fill='both', expand=True, padx=1, pady=1)

        cab = tk.Frame(cuerpo, bg=T.MENU_BG)
        cab.pack(fill='x', padx=(mpx(18), mpx(12)), pady=(mpx(14), mpx(4)))
        tk.Label(cab, text=titulo, bg=T.MENU_BG, fg=T.MENU_FG,
                 font=(T.FUENTE, -mpx(14), 'bold')).pack(side='left')
        fi = self._fuente_iconos()
        cerrar = tk.Label(cab, text=('\uE8BB' if fi else '\u2715'),
                          bg=T.MENU_BG, fg=T.MENU_MUTED, cursor='hand2',
                          font=((fi, -mpx(10)) if fi else (T.FUENTE, -mpx(12))),
                          padx=mpx(6), pady=mpx(4))
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

    def _campo(self, parent, ancho, fuente, centrado=False):
        """Caja de texto con las esquinas redondeadas (fondo dibujado con
        Pillow y el cuadro de texto encima). Devuelve (contenedor, entrada)."""
        f = tkfont.Font(font=fuente)
        alto = f.metrics('linespace') + mpx(16)
        fondo = parent.cget('bg')

        def dib(d, SS):
            d.rounded_rectangle([0, 0, ancho * SS - 1, alto * SS - 1],
                                radius=mpx(8) * SS, fill=T.MENU_HOVER)
        im = self._img_cache(('campo', T.MENU_HOVER), dib, ancho, alto, fondo)
        caja = tk.Frame(parent, width=ancho, height=alto, bg=fondo)
        caja.pack_propagate(False)
        if im is not None:
            fondo_l = tk.Label(caja, image=im, bd=0, bg=fondo)
            fondo_l._img = im
            fondo_l.place(x=0, y=0, relwidth=1, relheight=1)
        else:
            caja.configure(bg=T.MENU_HOVER)
        ent = tk.Entry(caja, font=fuente, bg=T.MENU_HOVER, fg=T.MENU_FG,
                       relief='flat', bd=0, highlightthickness=0,
                       insertbackground=T.MENU_FG,
                       justify=('center' if centrado else 'left'))
        ent.place(x=mpx(10), rely=0.5, anchor='w', width=ancho - mpx(20))
        caja._fuente = f
        return caja, ent

    def _boton(self, parent, texto, cmd, primario=False):
        """Boton con las esquinas redondeadas (dibujado con Pillow), como los
        de Windows 11. Sin Pillow, un rectangulo plano como antes."""
        fuente = tkfont.Font(family=T.FUENTE, size=-mpx(12),
                             weight=('bold' if primario else 'normal'))
        normal = T.MENU_ACCENT if primario else T.MENU_HOVER
        encima = _mix(normal, T.MENU_FG, 0.12)
        texto_c = T.TEXT_ON_FILL if primario else T.MENU_FG
        bw, bh = fuente.measure(texto) + mpx(34), mpx(32)
        fondo = parent.cget('bg')

        def imagen(color):
            def dib(d, SS):
                d.rounded_rectangle([0, 0, bw * SS - 1, bh * SS - 1],
                                    radius=mpx(8) * SS, fill=color)
            return self._img_cache(('btn', color, bw), dib, bw, bh, fondo)

        im = imagen(normal)
        if im is not None:
            b = tk.Label(parent, text=texto, image=im, compound='center', bd=0,
                         bg=fondo, fg=texto_c, font=fuente, cursor='hand2')
            b._img = im

            def pinta(color):
                nueva = imagen(color)
                b.configure(image=nueva)
                b._img = nueva
            b.bind('<Enter>', lambda e: pinta(encima))
            b.bind('<Leave>', lambda e: pinta(normal))
        else:
            b = tk.Label(parent, text=texto, cursor='hand2', bg=normal,
                         fg=texto_c, font=fuente, padx=mpx(16), pady=mpx(7))
        b._fuente = fuente
        b.bind('<Button-1>', lambda e: cmd())
        return b
