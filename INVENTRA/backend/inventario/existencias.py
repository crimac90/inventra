"""
Las existencias, que no se guardan en ninguna columna.

El MER lo dice con todas sus letras en la tabla `producto`: «las existencias NO
se guardan aquí: se derivan de los lotes (una sola fuente de verdad)». Esta es
esa derivación, escrita una vez.

Es la misma forma que el estado de la suscripción en SUS, donde el cálculo manda
y la columna es una copia, llevada un paso más allá: aquí ni siquiera hay copia
que mantener al día, así que no hay forma de que se quede atrasada.
"""

from django.db.models import Sum

from .models import LoteInventario


def existencias_de(producto, sede):
    """Unidades disponibles de un producto en una sede."""
    total = (
        LoteInventario.objects
        .filter(producto=producto, sede=sede)
        .aggregate(total=Sum("cantidad_disponible"))["total"]
    )
    return total or 0


def existencias_por_producto(licorera, sede=None):
    """
    Un diccionario {id de producto: unidades} para toda la licorera.

    Existe por una razón concreta: la lista del catálogo necesita la existencia
    de cada fila, y preguntarla producto a producto haría una consulta por fila.
    Con veinte referencias no se nota; con dos mil, la pantalla deja de abrir.
    """
    consulta = LoteInventario.objects.filter(producto__licorera=licorera)
    if sede is not None:
        consulta = consulta.filter(sede=sede)
    return {
        fila["producto_id"]: fila["total"]
        for fila in consulta.values("producto_id").annotate(total=Sum("cantidad_disponible"))
    }
