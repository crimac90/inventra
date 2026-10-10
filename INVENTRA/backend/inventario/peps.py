"""
Valoración de las salidas por PEPS — primeras entradas, primeras salidas
(RF-INV-10).

QUÉ RESUELVE
Cuando salen diez unidades de un producto, no basta con restar diez: hay que
saber **de qué lotes** salieron, porque cada lote tiene su costo real y de ahí
sale la utilidad verdadera (RF-REP-05). Se consumen siempre los lotes más
antiguos primero, que es como se mueve la mercancía de verdad en una licorera y
lo que evita que quede fondo de bodega eterno.

POR QUÉ ESTÁ AQUÍ Y NO EN EL PUNTO DE VENTA
Lo van a llamar el ajuste por merma, la venta y, el día que exista, el traslado
entre sedes. Escrito dentro de la venta, el ajuste tendría que copiarlo y las
dos copias se separarían en el primer arreglo. Escrito aquí, se construye y se
prueba con el módulo pequeño y el grande solo lo llama.

LA NO RETROACTIVIDAD, QUE ES LA MITAD DEL REQUISITO
El costo se **copia** al consumir. Si mañana alguien corrige el costo de un
lote, lo que ya salió conserva el costo con el que salió: la utilidad de un mes
cerrado no cambia porque se corrija una factura hoy.
"""

from django.core.exceptions import ValidationError
from django.db import transaction

from .existencias import existencias_de
from .kardex import registrar_movimiento
from .models import LoteInventario


class Consumo:
    """
    Un tramo de la salida: cuántas unidades salieron de qué lote y a qué costo.

    Es lo que esta función devuelve a quien la llama, y es exactamente lo que
    el punto de venta necesitará guardar en `consumo_lote` para poder calcular
    después la utilidad real de cada línea.
    """

    __slots__ = ("lote", "cantidad", "costo_unitario")

    def __init__(self, lote, cantidad, costo_unitario):
        self.lote = lote
        self.cantidad = cantidad
        self.costo_unitario = costo_unitario

    @property
    def costo_total(self):
        return self.costo_unitario * self.cantidad

    def __repr__(self):
        return "Consumo(lote=%s, cantidad=%d, costo=%s)" % (
            self.lote_id_legible, self.cantidad, self.costo_unitario)

    @property
    def lote_id_legible(self):
        return getattr(self.lote, "id", None)


@transaction.atomic
def consumir(*, producto, sede, cantidad, tipo, usuario, documento_tipo,
             documento_id, motivo=None):
    """
    Saca `cantidad` unidades del producto en esa sede, por orden de antigüedad.

    Devuelve la lista de `Consumo` —un tramo por cada lote tocado— y deja en el
    kardex **un movimiento por tramo**, con el costo de ese lote. Un movimiento
    único por la salida entera no podría llevar costo, porque no hay un solo
    costo: una venta de diez puede salir de dos compras distintas.

    Si no hay existencias suficientes no saca nada y lo dice. No se admite
    dejar el inventario en negativo: una existencia negativa no significa nada
    y, en cuanto aparece una, deja de poder confiarse en el resto.
    """
    if cantidad <= 0:
        raise ValidationError("La cantidad a retirar debe ser mayor que cero.")

    disponible = existencias_de(producto, sede)
    if disponible < cantidad:
        raise ValidationError(
            "No hay existencias suficientes de «%s»: hay %d y se piden %d."
            % (producto.nombre, disponible, cantidad))

    # `select_for_update` bloquea estas filas hasta el final de la transacción.
    # Sin él, dos ventas simultáneas del último lote leerían las mismas cinco
    # unidades disponibles y las venderían las dos: el inventario quedaría en
    # negativo y ninguna de las dos operaciones habría hecho nada mal por su
    # cuenta. El orden es el del modelo —fecha de ingreso y, a igualdad, el
    # identificador—, que es la definición del PEPS escrita una sola vez.
    lotes = (
        LoteInventario.objects
        .select_for_update()
        .filter(producto=producto, sede=sede, cantidad_disponible__gt=0)
        .order_by("fecha_ingreso", "id")
    )

    consumos = []
    por_sacar = cantidad

    for lote in lotes:
        if por_sacar == 0:
            break

        tomadas = min(lote.cantidad_disponible, por_sacar)
        lote.cantidad_disponible -= tomadas
        lote.save(update_fields=["cantidad_disponible"])
        por_sacar -= tomadas

        registrar_movimiento(
            producto=producto, sede=sede, tipo=tipo, cantidad=tomadas,
            usuario=usuario, lote=lote,
            # El costo se copia, no se referencia: es lo que sostiene la no
            # retroactividad de RF-INV-10.
            costo_unitario=lote.costo_unitario,
            documento_tipo=documento_tipo, documento_id=documento_id,
            motivo=motivo,
        )
        consumos.append(Consumo(lote, tomadas, lote.costo_unitario))

    if por_sacar:
        # No debería ocurrir: las existencias se comprobaron arriba y las filas
        # están bloqueadas. Si ocurre, algo cuenta mal y es preferible deshacer
        # la transacción entera que dejar una salida a medias.
        raise ValidationError(
            "No se pudieron retirar todas las unidades de «%s»." % producto.nombre)

    return consumos


def costo_total(consumos):
    """Lo que costó de verdad una salida, sumando lo que puso cada lote."""
    return sum(consumo.costo_total for consumo in consumos)
