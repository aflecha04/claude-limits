# -*- coding: utf-8 -*-
"""Pintado de la barra: tarjeta, carril, relleno y rotulos."""

import tkinter as tk

from . import tema as T
from .tema import px, _hex, _mix, HAVE_PIL, Image, ImageChops, ImageDraw, ImageTk
from .mensajes import mensaje_dormido, MENSAJE_DORMIDO


class Dibujo:
    """Pintado de la barra."""

    # ---- rendering ----------------------------------------------------
    def _render_all(self):
        if HAVE_PIL:
            self.cv.itemconfig(self._shape_id, image=self._render_shapes(self.pct))
        else:
            self._draw_bar(self.pct or 0)
            self.cv.delete('pctfb')
            txt = self.status_msg or (f'{self.pct}%' if self.pct is not None else '--')
            self.cv.create_text((self.bar_x0 + self.bar_x1) / 2, T.H // 2,
                                text=txt, anchor='center', fill=T.INK,
                                font=self.f_pct, tags='pctfb')
        self._draw_labels()

    SS = 4                           # supersampling para bordes suaves

    def _base_img(self):
        """Fondo estatico (tarjeta + carril vacio) cacheado.

        Solo cambia con el tema, el color o el tamano, no con el porcentaje,
        asi que se dibuja una vez y cada repintado parte de una copia.
        """
        key = (T.THEME, T.ACCENT_NAME, T.W, T.H, self.bar_x0, self.bar_x1,
               self.bar_y, self.bar_h)
        cache = getattr(self, '_base_cache', None)
        if cache is None:
            cache = self._base_cache = {}
        hit = cache.get(key)
        if hit is not None:
            return hit
        SS = self.SS
        iw, ih = T.W * SS, T.H * SS
        img = Image.new('RGBA', (iw, ih), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        # Un solo borde: antes la tarjeta se dibujaba metida un pixel y con
        # contorno propio, asi que junto al canto de la ventana parecian dos
        # marcos concentricos.
        d.rounded_rectangle([0, 0, iw - 1, ih - 1], radius=px(12) * SS,
                            fill=T.TINT,
                            outline=(T.CARD_BD if T.CARD_BD != T.TINT else None),
                            width=(SS if T.CARD_BD != T.TINT else 0))
        x0, x1 = self.bar_x0 * SS, self.bar_x1 * SS
        y0, y1 = self.bar_y * SS, (self.bar_y + self.bar_h) * SS
        rr = (y1 - y0) // 2
        d.rounded_rectangle([x0, y0, x1, y1], radius=rr,
                            fill=T.TRACK, outline=T.TRACK_SH, width=SS)
        d.line([(x0 + rr, y0 + SS), (x1 - rr, y0 + SS)],
               fill=T.TRACK_SH, width=SS)
        if len(cache) > 8:
            cache.clear()
        cache[key] = img
        return img

    @staticmethod
    def _grad_strip(c1, c2):
        """Tira de degradado 256x1, cacheada: interpolar y escalar es mucho
        mas rapido que pintar cientos de lineas verticales."""
        key = (c1, c2)
        hit = Dibujo._GRAD_CACHE.get(key)
        if hit is not None:
            return hit
        strip = Image.new('RGB', (256, 1))
        pxl = strip.load()
        a, b = _hex(c1), _hex(c2)
        for i in range(256):
            t = i / 255.0
            pxl[i, 0] = tuple(int(round(a[j] + (b[j] - a[j]) * t)) for j in range(3))
        Dibujo._GRAD_CACHE[key] = strip
        return strip

    _GRAD_CACHE = {}

    def _render_shapes(self, pct):
        SS = self.SS
        img = self._base_img().copy()
        x0 = self.bar_x0 * SS
        y0, y1 = self.bar_y * SS, (self.bar_y + self.bar_h) * SS
        rr = (y1 - y0) // 2
        # Tambien al 100 % se usa el color elegido: antes el modo dormido
        # forzaba un verde fijo e ignoraba el acento del menu. El estado ya
        # lo dicen el rotulo 'Claude duerme' y el reloj de la cuenta atras.
        cs, ce = T.BAR_START, T.BAR_END
        fw = x0
        # relleno con degradado, recortado a pastilla redondeada
        if pct and pct > 0:
            fwf = self._fin_relleno(pct)
            fw = int(round(fwf * SS))
            w = max(1, fw - x0)
            h = y1 - y0
            grad = self._grad_strip(cs, ce).resize((w, h), Image.BILINEAR)
            mask = Image.new('L', (w, h), 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1],
                                                   radius=min(rr, w // 2),
                                                   fill=255)
            # Recortado ademas con la forma del CARRIL: con poco porcentaje el
            # relleno es una media luna pegada a la curva izquierda, en vez de
            # una bola del alto de la barra que aparentaba un 10 %.
            carril = Image.new('L', (w, h), 0)
            ImageDraw.Draw(carril).rounded_rectangle(
                [0, 0, self.bar_x1 * SS - x0 - 1, h - 1], radius=rr, fill=255)
            mask = ImageChops.multiply(mask, carril)
            img.paste(grad, (x0, y0), mask)

        # Punto de aviso al final del carril: algun limite semanal o de un
        # modelo esta agotado aunque la sesion de 5 h vaya bien. Sin el, solo
        # te enterabas pasando el raton por encima. No se pinta si la propia
        # sesion esta dormida: ahi la barra ya lo dice todo.
        if self._limite_agotado() and not (pct is not None and pct >= 100):
            d = ImageDraw.Draw(img)
            r = px(3) * SS
            aro = max(2, SS * 3 // 2)
            cx, cy = self.bar_x1 * SS - rr, (y0 + y1) // 2
            d.ellipse([cx - r - aro, cy - r - aro, cx + r + aro, cy + r + aro],
                      fill=T.TRACK)
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=T.CLOSE_HOV)

        out = img.resize((T.W, T.H), Image.LANCZOS)
        self._shape_img = ImageTk.PhotoImage(out)
        return self._shape_img

    def _hook(self, item, hov, cmd):
        c = self.cv
        c.tag_unbind(item, '<Enter>')
        c.tag_unbind(item, '<Leave>')
        c.tag_unbind(item, '<Button-1>')
        c.tag_bind(item, '<Enter>', lambda e: c.itemconfig(item, fill=hov))
        c.tag_bind(item, '<Leave>', lambda e: c.itemconfig(item, fill=T.BTN))
        c.tag_bind(item, '<Button-1>', cmd)
        c.tag_bind(item, '<Enter>', lambda e: c.config(cursor='hand2'), add='+')
        c.tag_bind(item, '<Leave>', lambda e: c.config(cursor=''), add='+')

    def _pill(self, x0, y0, x1, y1, color, tag):
        r = (y1 - y0) / 2
        if x1 - x0 < 2 * r:
            x1 = x0 + 2 * r
        c = self.cv
        c.create_oval(x0, y0, x0 + 2 * r, y1, fill=color, outline=color, tags=tag)
        c.create_oval(x1 - 2 * r, y0, x1, y1, fill=color, outline=color, tags=tag)
        c.create_rectangle(x0 + r, y0, x1 - r, y1, fill=color, outline=color, tags=tag)

    def _draw_bar(self, pct, col=None):
        """Fallback sin Pillow."""
        c = self.cv
        c.delete('bar')
        x0, x1 = self.bar_x0, self.bar_x1
        y0, y1 = self.bar_y, self.bar_y + self.bar_h
        cy = (y0 + y1) / 2.0
        r = self.bar_h / 2.0
        self._pill(x0, y0, x1, y1, T.TRACK_SH, 'bar')
        self._pill(x0 + 1, y0 + 1, x1 - 1, y1 - 1, T.TRACK, 'bar')
        c.create_line(x0 + r, y0 + 2, x1 - r, y0 + 2, fill=T.TRACK_SH, tags='bar')
        if pct and pct > 0:
            fw = self._fin_relleno(pct)
            span = fw - x0
            x = int(x0)
            end = int(round(fw))
            while x <= end:
                if x < x0 + r:
                    dx = (x0 + r) - x
                elif x > fw - r:
                    dx = x - (fw - r)
                else:
                    dx = 0.0
                if dx <= r:
                    hh = (r * r - dx * dx) ** 0.5
                    t = min(1.0, max(0.0, (x - x0) / span))
                    c.create_line(x, cy - hh, x, cy + hh + 1,
                                  fill=_mix(T.BAR_START, T.BAR_END, t), tags='bar')
                x += 1
        c.tag_lower('card')

    @staticmethod
    def _dy_optico(fuente):
        """Correccion de centrado vertical, medida.

        Tk centra por la caja de la linea (ascendente + descendente). Lo que
        se ve de una cifra va del alto de mayuscula a la linea base, asi que
        el centro optico es:   base - altura_mayuscula / 2.
        Restando donde cae la base en la caja de Tk sale el desplazamiento.
        Con Segoe UI da practicamente cero; la formula lo mantiene correcto
        si cambia la fuente o el tamano.
        """
        try:
            a = fuente.metrics('ascent')
            d = fuente.metrics('descent')
            em = abs(fuente.cget('size'))
            mayuscula = em * 0.70              # altura de mayuscula tipica
            return int(round(mayuscula / 2.0 - (a - d) / 2.0))
        except Exception:
            return 0

    # todos los formatos que puede mostrar la cuenta atras
    CD_MUESTRAS = ('0:00:00', '22h 59m', '7d 23h', 'clic dcho')

    def _geometria_barra(self):
        """La barra ocupa TODO lo que sobra.

        Se reserva para la cuenta atras el ancho de TODOS sus casos posibles,
        no solo el del reloj: asi la barra no cambia de longitud cada vez que
        pasa un minuto y, sobre todo, el texto nunca se queda sin sitio.

        Antes solo se medía '0:00:00' y resulta que '22h 59m' es MAS ancho
        (los dos puntos ocupan la mitad que un digito). Al no caber, el
        contador se dibujaba con la fuente de emergencia, mas pequeña todavia
        que la original: por eso subir el tamaño no cambiaba nada en pantalla.
        """
        hueco_x = px(18)                       # zona del icono de cerrar
        try:
            reserva = max(self.f_sub.measure(s) for s in self.CD_MUESTRAS)
        except Exception:
            reserva = px(62)
        self.cd_der = T.W - T.PAD - hueco_x        # el contador acaba aqui
        self.bar_x0 = T.PAD
        self.bar_x1 = max(T.PAD + px(60), self.cd_der - reserva - px(10))
        self.bar_h = px(20)
        self.bar_y = T.H // 2 - self.bar_h // 2
        self.cd_x = self.bar_x1 + px(10)

    ROT_PAD = 12                     # aire a cada lado del rotulo, en px logicos

    def _rotulo(self):
        """(texto, fuente) del rotulo que va dentro de la barra."""
        if self.status_msg:
            return self.status_msg, self.f_msg
        if self.pct is not None and self.pct >= 100:
            texto = mensaje_dormido(self.reset_iso)
            # si en algun tamano no cabe entero en la barra, el de siempre
            try:
                hueco = (self.bar_x1 - self.bar_x0) - 2 * px(self.ROT_PAD)
                if self.f_msg.measure(texto) > hueco:
                    texto = MENSAJE_DORMIDO
            except Exception:
                texto = MENSAJE_DORMIDO
            return texto, self.f_msg
        if self.pct is not None:
            return f'{self.pct}%', self.f_pct
        return '--', self.f_pct

    def _fin_relleno(self, pct):
        """Donde acaba el color: el porcentaje REAL, sin inflar.

        Antes se estiraba hasta que cupiera el rotulo, y un 5 % ocupaba como
        un 25 %. Ahora el largo es fiel; el rotulo no depende de el porque se
        pinta en dos colores (ver _rotulo_sobre_relleno). Solo hay un minimo
        de unos pixeles para que un 1 % no sea invisible.
        """
        x0, x1 = self.bar_x0, self.bar_x1
        if not pct or pct <= 0:
            return float(x0)
        fin = x0 + (x1 - x0) * min(pct, 100) / 100.0
        return float(min(max(fin, x0 + px(4)), x1))

    def _texto_barra(self):
        """(texto, x, color, fuente) del rotulo de la barra.

        Siempre en el mismo sitio, al principio del carril. Esta es la capa
        de ABAJO, en el color del carril; la parte que queda sobre el relleno
        la tapa una copia en el color del relleno (_rotulo_sobre_relleno).
        """
        texto, fuente = self._rotulo()
        return texto, self.bar_x0 + px(self.ROT_PAD), T.INK, fuente

    def _rotulo_sobre_relleno(self, texto, tx, cy, fuente):
        """Copia del rotulo en TEXT_ON_FILL, recortada exactamente al relleno.

        El canvas de tkinter no sabe recortar un texto, pero un canvas hijo
        si: se coloca justo encima del tramo relleno, muestra la misma imagen
        de fondo desplazada y encima el rotulo en blanco. Lo que asoma fuera
        del relleno es la capa de abajo. Resultado: la cifra cambia de color
        justo en el borde, como en las barras de progreso de Windows y macOS,
        y el relleno puede medir lo que de verdad mide.
        """
        c = self.cv
        x0 = self.bar_x0
        fin = self._fin_relleno(self.pct) if (self.pct and self.pct > 0) else x0
        ancho = int(round(fin)) - x0
        img = getattr(self, '_shape_img', None)
        sub = getattr(self, '_cv_fill', None)
        if not (HAVE_PIL and img is not None and ancho > 0 and fin > tx):
            if sub is not None:
                c.itemconfig(self._cv_fill_id, state='hidden')
            return
        if sub is None:
            sub = self._cv_fill = tk.Canvas(c, highlightthickness=0, bd=0,
                                            bg=T.TINT, cursor='')
            self._cv_fill_id = c.create_window(0, 0, anchor='nw', window=sub)
        c.coords(self._cv_fill_id, x0, self.bar_y)
        c.itemconfig(self._cv_fill_id, width=ancho, height=self.bar_h,
                     state='normal')
        sub.delete('all')
        sub.create_image(-x0, -self.bar_y, image=img, anchor='nw')
        sub.create_text(tx - x0, cy - self.bar_y, text=texto, anchor='w',
                        fill=T.TEXT_ON_FILL, font=fuente)

    def _draw_labels(self):
        c = self.cv
        c.delete('lbl')
        texto, tx, col, fuente = self._texto_barra()
        cy = T.H // 2 + self._dy_optico(fuente)
        c.create_text(tx, cy, text=texto, anchor='w', fill=col, font=fuente,
                      tags='lbl')
        self._rotulo_sobre_relleno(texto, tx, cy, fuente)
        if not self._cd:
            return
        # pegada a la X, alineada por la derecha. Sin fuente de emergencia:
        # el hueco ya se reserva para el caso mas ancho.
        fnt = self.f_sub
        c.create_text(self.cd_der, T.H // 2 + self._dy_optico(fnt),
                      text=self._cd, anchor='e',
                      fill=(T.LABEL if getattr(self, '_cargando', False) else T.TIME),
                      font=fnt, tags='lbl')
