"""
El kardex: el único sitio desde el que se escribe un movimiento de inventario
(RF-INV-09).

POR QUÉ UNA SOLA PUERTA
Van a mover existencias la entrada de mercancía, el ajuste, la venta, la
anulación de venta y —el día que exista SED— el traslado. Si cada una escribiera
su propio movimiento, bastaría olvidarlo en una para que el kardex dejara de
cuadrar con las existencias reales, y eso no se descubre con una prueba: se
descubre meses después, haciendo inventario físico, sin saber cuál de las cinco
operaciones fue la que no anotó.

Aquí, además, el signo de la cantidad no se confía a quien llama: se comprueba
contra el tipo de movimiento. Registrar una venta con cantidad positiva es un
error fácil de cometer y silencioso —el saldo subiría—, así que se rechaza.
"""

from django.core.exceptions import ValidationError

from .existencias import existencias_de
from .models import MovimientoInventario

# Qué signo debe llevar la cantidad en cada tipo de movimiento. La tabla está
# escrita aquí y no en cada operación para que no se pueda contradecir.
SIGNO = {
    MovimientoInventario.Tipo.ENTRADA: +1,
    MovimientoInventario.Tipo.VENTA: -1,
    MovimientoInventario.Tipo.ANULACION_VENTA: +1,
    MovimientoInventario.Tipo.AJUSTE_POSITIVO: +1,
    MovimientoInventario.Tipo.AJUSTE_NEGATIVO: -1,
    MovimientoInventario.Tipo.TRASLADO_SALIDA: -1,
    MovimientoInventario.Tipo.TRASLADO_ENTRADA: +1,
}

# Los movimientos que no se pueden registrar sin decir por qué (RF-INV-06). Un
# ajuste sin motivo es una existencia que cambió y nadie sabe explicar.
EXIGEN_MOTIVO = {
    MovimientoInventario.Tipo.AJUSTE_POSITIVO,
    MovimientoInventario.Tipo.AJUSTE_NEGATIVO,
}


def registrar_movimiento(*, producto, sede, tipo, cantidad, usuario,
                         documento_tipo, documento_id, lote=None,
                         costo_unitario=None, motivo=None):
    """
    Anota un movimiento en el kardex y devuelve la fila creada.

    `cantidad` se recibe en unidades, siempre positiva: el signo lo pone esta
    función según el tipo. Quien llama dice qué pasó, no cómo se anota.

    IMPORTANTE: se llama DESPUÉS de haber movido los lotes, nunca antes. El
    saldo resultante se calcula aquí leyendo las existencias ya actualizadas,
    que es lo que convierte al kardex en una foto fiel de cómo quedó el
    inventario y no en una previsión de cómo iba a quedar.
    """
    if tipo not in SIGNO:
        raise ValidationError("Tipo de movimiento desconocido: %s" % tipo)
    if cantidad <= 0:
        raise ValidationError("La cantidad del movimiento debe ser mayor que cero.")
    if tipo in EXIGEN_MOTIVO and not (motivo or "").strip():
        raise ValidationError("Este movimiento exige un motivo.")

    return MovimientoInventario.objects.create(
        licorera=producto.licorera,
        producto=producto,
        sede=sede,
        lote=lote,
        tipo=tipo,
        cantidad=SIGNO[tipo] * cantidad,
        costo_unitario=costo_unitario,
        documento_tipo=documento_tipo,
        documento_id=documento_id,
        usuario=usuario,
        motivo=(motivo or "").strip() or None,
        saldo_resultante=existencias_de(producto, sede),
    )
