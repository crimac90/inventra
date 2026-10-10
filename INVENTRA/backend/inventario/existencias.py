"""
Las existencias, que no se guardan en ninguna columna.

El MER lo dice con todas sus letras en la tabla `producto`: «las existencias NO
se guardan aquí: se derivan de los lotes (una sola fuente de verdad)». Esta es
esa derivación, escrita una vez.

Es la misma forma que el estado de la suscripción en SUS, donde el cálculo manda
y la columna es una copia, llevada un paso más allá: aquí ni siquiera hay copia
que mantener al día, así que no hay forma de que se quede atrasada.
"""

from django.db.models import Sum, Value
from django.db.models.functions import Coalesce

from .models import LoteInventario


def existencias_de(producto, sede):
    """Unidades disponibles de un producto en una sede."""
    total = (
        LoteInventario.objects
        .filter(producto=producto, sede=sede)
        .aggregate(total=Sum("cantidad_disponible"))["total"]
    )
    return total or 0


def existencias_totales(producto):
    """Unidades disponibles de un producto, sumando todas sus sedes."""
    total = (
        LoteInventario.objects
        .filter(producto=producto)
        .aggregate(total=Sum("cantidad_disponible"))["total"]
    )
    return total or 0


def con_existencias(consulta):
    """
    Añade a una consulta de productos la columna calculada `disponibles`.

    Es la misma suma de arriba, hecha dentro de la consulta en vez de una vez
    por fila. La lista del catálogo necesita la existencia de cada producto y
    preguntarla una por una haría una consulta por fila: con veinte referencias
    no se nota, con dos mil la pantalla deja de abrir.

    `Coalesce` convierte en cero el vacío que devuelve la suma cuando un
    producto no tiene ningún lote. Sin eso, una referencia recién registrada
    saldría con un hueco en vez de con el cero que le corresponde, y cualquier
    filtro por nivel de existencias la dejaría fuera.
    """
    return consulta.annotate(
        disponibles=Coalesce(Sum("lotes__cantidad_disponible"), Value(0)))
