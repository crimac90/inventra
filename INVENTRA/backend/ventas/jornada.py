"""
Qué día es una venta.

Una licorera vende de noche, así que el día del calendario no sirve para cerrar
la caja: un corte a medianoche parte en dos una sola noche de trabajo. Y el
problema de fondo no es dónde cae cada venta, sino que **el cajón no se vacía a
las doce**: el efectivo que se cuenta a las dos de la madrugada corresponde a la
noche entera, y repartirlo entre dos cierres produciría un descuadre que nadie
cometió.

Por eso el día de este módulo es una jornada comercial: empieza a las seis de la
mañana y termina a las seis de la mañana siguiente. Lo vendido en la madrugada
pertenece a la jornada de la noche anterior.

La hora es una constante y no una columna por la misma razón que los tres
plazos de la suscripción: es la misma regla para cualquier licorera, y una que
atienda hasta las cinco de la mañana queda cubierta. El día que haga falta por
negocio, pasar de constante a columna es una migración pequeña.

El MER no cambia: `cierre_caja.fecha` sigue siendo una fecha. Lo único distinto
es qué significa —el día de la jornada— y qué ventas caen dentro.
"""

from datetime import time, timedelta

from django.utils import timezone

# Hora a la que termina una jornada y empieza la siguiente.
INICIO_DE_JORNADA = time(6, 0)


def jornada_de(momento):
    """
    La jornada a la que pertenece un instante.

    Antes de las seis de la mañana todavía se está en la jornada del día
    anterior, que es lo que hace que una venta de la una de la madrugada se
    cierre con la noche en la que se vendió.
    """
    local = timezone.localtime(momento)
    if local.time() < INICIO_DE_JORNADA:
        return (local - timedelta(days=1)).date()
    return local.date()


def jornada_actual():
    """La jornada que está abierta ahora mismo."""
    return jornada_de(timezone.now())


def limites_de(jornada):
    """
    El instante en que empieza una jornada y el instante en que termina.

    Se devuelven como momentos con zona horaria para poder filtrar `venta.fecha`,
    que es fecha y hora. El final es exclusivo: pertenece ya a la jornada
    siguiente.
    """
    zona = timezone.get_current_timezone()
    inicio = timezone.make_aware(
        timezone.datetime.combine(jornada, INICIO_DE_JORNADA), zona)
    return inicio, inicio + timedelta(days=1)
