# -*- coding: utf-8 -*-
"""Rotulos del modo dormido."""

import random

# ─── Mensajes del modo dormido ─────────────────────────────────────────
# Al llegar al 100 % la barra dice 'Claude duerme'... o, con cierta
# probabilidad, otra cosa. El mensaje se sortea UNA vez por cada periodo de
# descanso (la semilla es la hora de reinicio): no cambia en cada repintado
# ni al reabrir el widget, y el siguiente descanso trae otro sorteo.
MENSAJE_DORMIDO = 'Claude duerme'
PROB_MENSAJE_CLASICO = 0.5          # 50 %: el de siempre; 50 %: uno de estos
MENSAJES_DORMIDO = (
    'Claude está soñando',
    'Zzz…',
    'Recargando neuronas',
    'Claude ha ido a por café',
    'Enfriando circuitos',
    'Claude medita',
    'Siesta obligatoria',
    'Recargando pilas',
    'Fuera de la oficina',
    'Modo avión',
    'Vuelve enseguida',
    'Soñando con tokens',
    'Toca estirar las piernas',
    'Ha salido a tomar el aire',
    'Claude hace yoga',
    'Cerrado por descanso',
)


def mensaje_dormido(semilla):
    """Mensaje del modo dormido para ese periodo de descanso."""
    rnd = random.Random(str(semilla))
    if rnd.random() < PROB_MENSAJE_CLASICO:
        return MENSAJE_DORMIDO
    return rnd.choice(MENSAJES_DORMIDO)
