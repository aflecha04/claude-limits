# -*- coding: utf-8 -*-
"""Ventanas: sessionKey, cuenta de Claude, diagnostico y arranque."""

import os
import threading
import tkinter as tk

from . import tema as T
from . import config as C
from .tema import mpx, HAVE_PIL
from .canal import APP_NAME, VERSION
from .config import (load_cfg, save_cfg, cfg_dirs, CFG_NAME, _read_json,
                     clean_key, key_looks_real)
from .api import listar_orgs, orgs_con_chat, nombre_org, info_cuenta, KeyExpired
from .config import anadir_cuenta, activar_cuenta, quitar_cuenta
from . import login
from .sistema import (_mi_ruta, autostart_activar, autostart_estado,
                      autostart_vetado, round_corners)


class Dialogos:
    """Ventanas de sessionKey, diagnostico y arranque."""

    # ---- dialogos ------------------------------------------------------
    def _toggle_autostart(self, e=None):
        activo = (autostart_estado() or '').lower() == _mi_ruta().lower()
        ok = autostart_activar(not activo)
        cfg = load_cfg()
        cfg['autostart'] = (not activo)
        save_cfg(cfg, durable=False)
        if not ok:
            self._text_window(
                f'{APP_NAME}  -  arranque',
                'No se ha podido escribir en el registro de Windows.\n\n'
                'Suele ser una restriccion del equipo. Alternativa manual:\n'
                '  1. Windows + R\n'
                '  2. escribe:  shell:startup\n'
                '  3. arrastra el .exe con el BOTON DERECHO y elige\n'
                '     "Crear iconos de acceso directo aqui"')

    def _info_dialog(self, e=None):
        lines = [f'{APP_NAME}  v{VERSION}   ·   tema: {T.THEME}   ·   '
                 f'DPI: {getattr(self, "dpi", 96):.0f}  (escala x{T.UI:.2f})   ·   '
                 f'ventana: {T.W}x{T.H}px',
                 f'Pillow: {"sí" if HAVE_PIL else "NO (render básico)"}',
                 '']
        cfg = load_cfg()
        lines.append('sessionKey: ' + {
            'boveda': 'en la caja fuerte de Windows (Administrador de '
                      'credenciales)',
            'archivo': 'en config.json (la caja fuerte no estaba disponible)',
        }.get(C.CLAVE_EN, 'NO configurada'))
        lines.append(f'Cuenta de Claude: {nombre_org(cfg) or "(sin elegir)"}')
        lines += ['', 'Rutas de configuración (por orden):', '']
        for d in cfg_dirs():
            p = os.path.join(d, CFG_NAME)
            if os.path.exists(p):
                try:
                    has = bool(_read_json(p).get('session_key'))
                    mark = 'OK  (con clave en texto)' if has else 'OK'
                except Exception:
                    mark = 'ILEGIBLE / corrupto'
            else:
                mark = '(no existe)'
            lines.append(f'  {mark}\n     {p}')
        lines.append('')
        lines.append(f'Leído de: {C.LOADED_FROM or "(ninguno)"}')
        lines.append('')
        lines.append(f'Ejecutable: {_mi_ruta()}')
        reg = autostart_estado()
        if not reg:
            lines.append('Arranque con Windows: NO configurado')
        elif reg.lower() == _mi_ruta().lower():
            lines.append('Arranque con Windows: SÍ (registro HKCU\\...\\Run)')
        else:
            lines.append('Arranque con Windows: APUNTA A OTRO ARCHIVO ->')
            lines.append(f'   {reg}')
        if autostart_vetado():
            lines.append('   AVISO: Windows la tiene DESACTIVADA en')
            lines.append('   Administrador de tareas > Inicio de aplicaciones.')
        if C.SAVE_REPORT:
            lines.append('')
            lines.append('Último guardado:')
            for p, ok, why in C.SAVE_REPORT:
                lines.append(f'  {"OK " if ok else "FALLO"} {p}' +
                             (f'  -> {why}' if not ok else ''))
        self._text_window(f'{APP_NAME}  -  diagnóstico', '\n'.join(lines))

    def _text_window(self, title, body):
        previa = getattr(self, '_txtwin', None)
        if previa is not None and previa.winfo_exists():
            previa.destroy()
        w = self._ventana(title, mpx(560))
        self._txtwin = w
        cuerpo = w._cuerpo
        caja = tk.Frame(cuerpo, bg=T.MENU_HOVER)
        caja.pack(fill='both', expand=True, padx=mpx(14), pady=(mpx(8), 0))
        t = tk.Text(caja, width=78, height=17, bg=T.MENU_HOVER, fg=T.MENU_FG,
                    font=('Consolas', -mpx(11)), relief='flat', wrap='none',
                    bd=0, highlightthickness=0, padx=mpx(10), pady=mpx(8),
                    insertbackground=T.MENU_FG)
        t.pack(fill='both', expand=True)
        t.insert('1.0', body)
        t.config(state='disabled')
        bf = tk.Frame(cuerpo, bg=T.MENU_BG)
        bf.pack(pady=mpx(12))
        self._boton(bf, 'Cerrar', w.destroy, primario=True).pack()
        self._place(w, self.root.winfo_x() - mpx(260),
                    self.root.winfo_y() - mpx(320))
        round_corners(w)
        w.focus_force()

    def _key_dialog(self, e=None):
        if getattr(self, '_dlg', None) is not None and self._dlg.winfo_exists():
            self._dlg.lift(); self._dlg.focus_force(); return
        cfg = load_cfg()
        ancho = mpx(430)
        w = self._ventana('Conectar con Claude', ancho)
        self._dlg = w
        cuerpo = w._cuerpo
        w.protocol('WM_DELETE_WINDOW',
                   lambda: (setattr(self, '_dlg', None), w.destroy()))

        tk.Label(cuerpo, text='Pega aquí tu sessionKey de claude.ai',
                 bg=T.MENU_BG, fg=T.MENU_FG, font=(T.FUENTE, -mpx(12)),
                 anchor='w').pack(fill='x', padx=mpx(14), pady=(mpx(6), 0))
        tk.Label(cuerpo,
                 text='En claude.ai: icono a la izquierda de la dirección  ›  '
                      'Cookies  ›  sessionKey',
                 bg=T.MENU_BG, fg=T.MENU_MUTED, font=(T.FUENTE, -mpx(10)),
                 anchor='w', justify='left').pack(fill='x', padx=mpx(14),
                                                  pady=(mpx(2), mpx(10)))

        marco = tk.Frame(cuerpo, bg=T.MENU_HOVER)
        marco.pack(fill='x', padx=mpx(14))
        ent = tk.Entry(marco, show='\u2022', font=('Consolas', -mpx(12)),
                       bg=T.MENU_HOVER, fg=T.MENU_FG, relief='flat', bd=0,
                       highlightthickness=0, insertbackground=T.MENU_ACCENT)
        ent.pack(fill='x', padx=mpx(10), pady=mpx(9))

        msg = tk.Label(cuerpo, text='', bg=T.MENU_BG, fg=T.CLOSE_HOV,
                       font=(T.FUENTE, -mpx(10)), wraplength=ancho - mpx(30),
                       justify='left', anchor='w')
        msg.pack(fill='x', padx=mpx(14), pady=(mpx(6), 0))

        def conectar():
            val = clean_key(ent.get())
            if not key_looks_real(val):
                msg.config(text='Esa clave no parece válida: tiene que empezar '
                                'por "sk-ant-" y ser larga. Cópiala entera.')
                return
            msg.config(text='Comprobando…', fg=T.MENU_MUTED)

            def comprobar():
                try:
                    datos = info_cuenta(val)
                except KeyExpired:
                    datos = 'rechazada'
                except Exception:
                    datos = (None, None)          # sin red: se guarda igual
                self.root.after(0, terminar, datos)

            def terminar(datos):
                if not w.winfo_exists():
                    return
                if datos == 'rechazada':
                    msg.config(text='Claude no acepta esa clave. Vuelve a '
                                    'copiarla o inicia sesión.', fg=T.CLOSE_HOV)
                    return
                if not anadir_cuenta(val, *datos):
                    msg.config(text='No se ha podido guardar en ninguna carpeta.\n'
                                    + '\n'.join(f'{p}: {why}'
                                                for p, _o, why in C.SAVE_REPORT),
                               fg=T.CLOSE_HOV)
                    return
                self._dlg = None
                w.destroy()
                self._cuenta_cambiada()
            threading.Thread(target=comprobar, daemon=True).start()

        bf = tk.Frame(cuerpo, bg=T.MENU_BG)
        bf.pack(pady=(mpx(14), mpx(14)))
        self._boton(bf, 'Cancelar',
                    lambda: (setattr(self, '_dlg', None),
                             w.destroy())).pack(side='left', padx=mpx(5))
        self._boton(bf, 'Conectar', conectar,
                    primario=True).pack(side='left', padx=mpx(5))
        w.bind('<Return>', lambda e: conectar())
        self._place(w, self.root.winfo_x(), self.root.winfo_y() - mpx(190))
        round_corners(w)
        w.focus_force()
        ent.focus_set()

    # ---- cuenta de Claude (organizacion) -------------------------------
    def _org_dialog(self, e=None):
        """Elegir de que organizacion se muestra el consumo.

        Se abre con la lista guardada y la refresca en segundo plano, por si
        la cuenta ha ganado o perdido alguna desde la ultima vez.
        """
        previa = getattr(self, '_orgdlg', None)
        if previa is not None and previa.winfo_exists():
            previa.lift(); previa.focus_force(); return
        w = self._ventana('Organización', mpx(320))
        self._orgdlg = w
        cuerpo = w._cuerpo
        tk.Label(cuerpo, text='¿De qué organización quieres ver el consumo?',
                 bg=T.MENU_BG, fg=T.MENU_MUTED, font=(T.FUENTE, -mpx(11)),
                 anchor='w').pack(fill='x', padx=mpx(14), pady=(mpx(4), mpx(6)))
        lista = tk.Frame(cuerpo, bg=T.MENU_BG)
        lista.pack(fill='x')
        tk.Frame(cuerpo, bg=T.MENU_BG, height=mpx(10)).pack(fill='x')

        def elegir(uuid):
            c = load_cfg()
            c['org_id'] = uuid
            save_cfg(c)
            self._orgdlg = None
            w.destroy()
            self.refresh()

        def pintar(orgs, actual):
            for h in lista.winfo_children():
                h.destroy()
            for uuid, nombre in orgs:
                self._mrow(lista, nombre, lambda u=uuid: elegir(u),
                           punto=(lambda a=(uuid == actual): a))

        cfg = load_cfg()
        pintar(cfg.get('orgs') or [], cfg.get('org_id'))

        def recargar():
            try:
                c = load_cfg()
                orgs = orgs_con_chat(listar_orgs(c))
            except Exception:
                return
            if not orgs:
                return
            c['orgs'] = orgs
            save_cfg(c, durable=False)

            def mostrar():
                if w.winfo_exists():
                    pintar(orgs, c.get('org_id'))
            self.root.after(0, mostrar)
        threading.Thread(target=recargar, daemon=True).start()

        self._place(w, self.root.winfo_x(), self.root.winfo_y() - mpx(160))
        round_corners(w)
        w.focus_force()

    # ---- cuentas -------------------------------------------------------
    def _cuenta_cambiada(self):
        """Tras cambiar de cuenta: fuera los datos de la anterior y a leer."""
        self.usage = {}
        self.pct = None
        self.reset_iso = None
        self.status_msg = None
        self._render_all()
        self.refresh()

    def _cambiar_cuenta(self, cid):
        if activar_cuenta(cid):
            self._cuenta_cambiada()

    def _quitar_cuenta(self, cid):
        cfg = load_cfg()
        c = next((x for x in cfg.get('cuentas') or [] if x.get('id') == cid), {})
        nombre = c.get('email') or c.get('nombre') or 'esta cuenta'
        w = self._ventana('Quitar cuenta', mpx(320))
        cuerpo = w._cuerpo
        tk.Label(cuerpo, text=f'¿Quitar {nombre} del widget?\n'
                              'Podrás volver a añadirla cuando quieras.',
                 bg=T.MENU_BG, fg=T.MENU_FG, font=(T.FUENTE, -mpx(12)),
                 justify='left', anchor='w', wraplength=mpx(290)).pack(
                     fill='x', padx=mpx(14), pady=(mpx(6), 0))

        def si():
            w.destroy()
            era_activa = cid == cfg.get('cuenta_activa')
            quitar_cuenta(cid)
            if era_activa:
                self._cuenta_cambiada()

        bf = tk.Frame(cuerpo, bg=T.MENU_BG)
        bf.pack(pady=mpx(14))
        self._boton(bf, 'Cancelar', w.destroy).pack(side='left', padx=mpx(5))
        self._boton(bf, 'Quitar', si, primario=True).pack(side='left', padx=mpx(5))
        self._place(w, self.root.winfo_x(), self.root.winfo_y() - mpx(150))
        round_corners(w)
        w.focus_force()

    def _login_dialog(self, e=None):
        """Iniciar sesion en Claude en una ventana del navegador.

        La clave se recoge sola al entrar; pegarla a mano queda como plan B.
        """
        previa = getattr(self, '_dlg', None)
        if previa is not None and previa.winfo_exists():
            previa.lift(); previa.focus_force(); return
        w = self._ventana('Iniciar sesión en Claude', mpx(360))
        self._dlg = w
        cuerpo = w._cuerpo
        texto = tk.Label(cuerpo, bg=T.MENU_BG, fg=T.MENU_FG, justify='left',
                         anchor='w', wraplength=mpx(330),
                         font=(T.FUENTE, -mpx(12)),
                         text='Se abrirá una ventana para entrar en Claude con '
                              'la cuenta que quieras. Cuando entres, se cerrará '
                              'sola y el widget quedará conectado.')
        texto.pack(fill='x', padx=mpx(14), pady=(mpx(6), 0))
        estado = {'cancelado': False, 'abierto': False}

        bf = tk.Frame(cuerpo, bg=T.MENU_BG)
        bf.pack(pady=(mpx(14), mpx(4)))
        manual = tk.Label(cuerpo, text='o pega la sessionKey a mano',
                          bg=T.MENU_BG, fg=T.MENU_MUTED, cursor='hand2',
                          font=(T.FUENTE, -mpx(10), 'underline'))
        manual.pack(pady=(0, mpx(12)))

        def cerrar():
            estado['cancelado'] = True
            self._dlg = None
            if w.winfo_exists():
                w.destroy()

        def a_mano(_e=None):
            cerrar()
            self.root.after(1, self._key_dialog)
        manual.bind('<Button-1>', a_mano)

        def fin(resultado):
            if estado['cancelado'] or not w.winfo_exists():
                return
            if isinstance(resultado, tuple):
                anadir_cuenta(*resultado)
                cerrar()
                self._cuenta_cambiada()
                return
            estado['abierto'] = False
            texto.config(text=resultado, fg=T.CLOSE_HOV)
            abrir_b.pack(side='left', padx=mpx(5))

        def trabajar():
            try:
                clave = login.iniciar_sesion(lambda: estado['cancelado'])
                try:
                    nombre, email = info_cuenta(clave)
                except Exception:
                    nombre, email = None, None
                res = (clave, nombre, email)
            except login.Cancelado:
                res = ('Se cerró la ventana sin iniciar sesión. '
                       'Puedes volver a intentarlo.')
            except Exception as ex:
                res = f'No se ha podido abrir el navegador. {ex}'
            self.root.after(0, fin, res)

        def abrir():
            if estado['abierto']:
                return
            estado['abierto'] = True
            abrir_b.pack_forget()
            texto.config(text='Esperando a que inicies sesión en la ventana '
                              'del navegador…', fg=T.MENU_FG)
            threading.Thread(target=trabajar, daemon=True).start()

        self._boton(bf, 'Cancelar', cerrar).pack(side='left', padx=mpx(5))
        abrir_b = self._boton(bf, 'Abrir ventana', abrir, primario=True)
        abrir_b.pack(side='left', padx=mpx(5))
        w.protocol('WM_DELETE_WINDOW', cerrar)
        w.bind('<Return>', lambda e: abrir())
        self._place(w, self.root.winfo_x(), self.root.winfo_y() - mpx(170))
        round_corners(w)
        w.focus_force()

    # ---- color propio --------------------------------------------------
    MUESTRAS = ('#ef4444', '#f97316', '#f59e0b', '#eab308', '#84cc16', '#22c55e',
                '#14b8a6', '#06b6d4', '#3b82f6', '#6366f1', '#a855f7', '#ec4899')

    def _color_dialog(self, e=None):
        """Elegir un color propio: muestras para ir rapido o su codigo
        (#1e90ff), con la papelera para borrarlo. Todo dibujado con el mismo
        estilo del widget; nada que instalar."""
        previa = getattr(self, '_coldlg', None)
        if previa is not None and previa.winfo_exists():
            previa.lift(); previa.focus_force(); return
        w = self._ventana('Color personalizado', mpx(300))
        self._coldlg = w
        cuerpo = w._cuerpo
        propio = T.ACCENTS.get('propio')
        elegido = {'c': propio[1][0] if propio else None}

        # muestras de colores
        rejilla = tk.Frame(cuerpo, bg=T.MENU_BG)
        rejilla.pack(padx=mpx(14), pady=(mpx(6), mpx(4)))
        botones = []
        for i, c in enumerate(self.MUESTRAS):
            b = tk.Label(rejilla, bg=T.MENU_BG, bd=0, cursor='hand2')
            b.grid(row=i // 6, column=i % 6, padx=mpx(2), pady=mpx(2))
            b.bind('<Button-1>', lambda e, c=c: poner(c))
            botones.append((b, c))

        # codigo + muestra + papelera
        fila = tk.Frame(cuerpo, bg=T.MENU_BG)
        fila.pack(fill='x', padx=mpx(18), pady=(mpx(10), 0))
        muestra = tk.Label(fila, bg=T.MENU_BG, bd=0)
        muestra.pack(side='left')
        marco = tk.Frame(fila, bg=T.MENU_HOVER)
        marco.pack(side='left', fill='x', expand=True, padx=(mpx(10), 0))
        ent = tk.Entry(marco, font=('Consolas', -mpx(13)), bg=T.MENU_HOVER,
                       fg=T.MENU_FG, relief='flat', bd=0, highlightthickness=0,
                       insertbackground=T.MENU_FG, width=10)
        ent.pack(fill='x', padx=mpx(10), pady=mpx(7))
        fi = self._fuente_iconos()
        papelera = tk.Label(fila, text=('\uE74D' if fi else '\u2715'),
                            bg=T.MENU_BG, fg=T.MENU_MUTED, cursor='hand2',
                            font=((fi, -mpx(14)) if fi else (T.FUENTE, -mpx(13))),
                            padx=mpx(8))
        if propio:
            papelera.pack(side='left', padx=(mpx(4), 0))
        papelera.bind('<Enter>', lambda e: papelera.configure(fg=T.CLOSE_HOV))
        papelera.bind('<Leave>', lambda e: papelera.configure(fg=T.MENU_MUTED))

        msg = tk.Label(cuerpo, text='', bg=T.MENU_BG, fg=T.CLOSE_HOV,
                       font=(T.FUENTE, -mpx(10)), anchor='w')
        msg.pack(fill='x', padx=mpx(18), pady=(mpx(4), 0))

        def repintar():
            c = elegido['c']
            for b, mc in botones:
                im = self._color_img(mc, mc == c, T.MENU_BG)
                if im is not None:
                    b.configure(image=im)
                    b._img = im
                else:
                    b.configure(text='\u25cf', fg=mc)
            im = (self._color_img(c, False, T.MENU_BG) if c
                  else self._color_mas_img(T.MENU_BG))
            if im is not None:
                muestra.configure(image=im)
                muestra._img = im

        def poner(c):
            elegido['c'] = c
            ent.delete(0, 'end')
            ent.insert(0, c)
            msg.configure(text='')
            repintar()

        def escrito(_e=None):
            elegido['c'] = T.normalizar_hex(ent.get())
            msg.configure(text='')
            repintar()
        ent.bind('<KeyRelease>', escrito)

        def repintar_menu():
            for r in list(getattr(self, '_mrep', [])):      # menu abierto
                try:
                    r()
                except Exception:
                    pass

        def aplicar():
            c = T.normalizar_hex(ent.get())
            if not c:
                msg.configure(text='Ese código no es un color. Prueba algo '
                                   'como #1e90ff.')
                return
            T.set_color_propio(c)
            self._coldlg = None
            w.destroy()
            self._set_accent('propio')
            repintar_menu()

        def borrar(_e=None):
            T.set_color_propio(None)
            self._coldlg = None
            w.destroy()
            if T.ACCENT_NAME == 'propio' or 'propio' not in T.ACCENTS:
                previo = getattr(self, '_accent_previo', None) or 'coral'
                self._set_accent(previo if previo in T.ACCENTS else 'coral')
            repintar_menu()
        papelera.bind('<Button-1>', borrar)

        if elegido['c']:
            poner(elegido['c'])
        else:
            ent.insert(0, '#')
            repintar()

        bf = tk.Frame(cuerpo, bg=T.MENU_BG)
        bf.pack(fill='x', padx=mpx(18), pady=(mpx(10), mpx(16)))
        self._boton(bf, 'Aplicar', aplicar, primario=True).pack(side='right')
        self._boton(bf, 'Cancelar', lambda: (setattr(self, '_coldlg', None),
                                              w.destroy())).pack(
            side='right', padx=(0, mpx(8)))
        w.bind('<Return>', lambda e: aplicar())
        self._place(w, self.root.winfo_x(), self.root.winfo_y() - mpx(230))
        round_corners(w)
        w.focus_force()
        ent.focus_set()
        ent.icursor('end')
