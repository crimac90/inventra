"""
Las operaciones que mueven inventario, fuera de las vistas.

Mismo criterio que `cambio_de_plan.py` en SUS: lo que mueve existencias no vive
en una vista, porque lo van a disparar la pantalla, la carga de datos de prueba
y —más adelante— el punto de venta. Una vista traduce peticiones; esto es la
regla del negocio.
"""

from django.core.exceptions import ValidationError
from django.db import transaction

from sedes.models import Sede

from .kardex import registrar_movimiento
from .models import EntradaMercancia, LoteInventario, MovimientoInventario


@transaction.atomic
def registrar_entrada(*, licorera, usuario, lineas, proveedor=None, observacion=None,
                      sede=None):
    """
    Registra la llegada de mercancía (RF-INV-05).

    `lineas` es una lista de diccionarios con `producto`, `cantidad` y
    `costo_unitario`. Cada línea crea **un lote con su costo congelado** y su
    movimiento en el kardex.

    Va entera en una transacción: una entrada que creara dos lotes de tres, o
    los lotes sin su movimiento, dejaría el inventario diciendo una cosa y el
    kardex otra, que es el único desacuerdo que este módulo no puede permitirse.

    La sede se pregunta en vez de suponerse (D-31). Hoy la respuesta es siempre
    la sede principal, porque SED no está construido; el día que haya varias,
    cambia esta línea y no las diez que la llaman.
    """
    if not lineas:
        raise ValidationError("La entrada no tiene ninguna línea.")

    if sede is None:
        sede = Sede.principal_de(licorera)
    if sede is None:
        raise ValidationError("La licorera no tiene ninguna sede donde recibir la mercancía.")

    entrada = EntradaMercancia.objects.create(
        licorera=licorera, sede=sede, usuario=usuario,
        proveedor=(proveedor or "").strip() or None,
        observacion=(observacion or "").strip() or None,
    )

    for linea in lineas:
        producto = linea["producto"]
        cantidad = int(linea["cantidad"])
        costo = linea["costo_unitario"]

        if producto.licorera_id != licorera.id:
            # No debería llegar hasta aquí —el serializador limita el catálogo—,
            # pero esta función también la llaman la carga de datos y, mañana,
            # lo que venga: la regla del aislamiento se comprueba donde vive la
            # operación y no solo donde se escribe el formulario.
            raise ValidationError("Ese producto no pertenece a esta licorera.")
        if cantidad <= 0:
            raise ValidationError("La cantidad de cada línea debe ser mayor que cero.")
        if costo is None or costo < 0:
            raise ValidationError("El costo unitario no puede ser negativo.")

        lote = LoteInventario.objects.create(
            producto=producto, sede=sede,
            origen=LoteInventario.Origen.COMPRA, entrada=entrada,
            cantidad_inicial=cantidad, cantidad_disponible=cantidad,
            costo_unitario=costo,
        )
        registrar_movimiento(
            producto=producto, sede=sede,
            tipo=MovimientoInventario.Tipo.ENTRADA,
            cantidad=cantidad, usuario=usuario, lote=lote,
            costo_unitario=costo,
            documento_tipo=MovimientoInventario.Documento.ENTRADA,
            documento_id=entrada.id,
        )

    return entrada
