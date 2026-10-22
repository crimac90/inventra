"""
Las operaciones que registran y deshacen una venta.

Fuera de las vistas, igual que `inventario/operaciones.py` y por la misma
razón: a esto lo van a llamar la pantalla del punto de venta y la carga de
datos de demostración. Una vista traduce peticiones; esto es la regla del
negocio.

Lo que esta capa NO hace es inventarse el descuento de existencias: llama a
`peps.consumir()`, que ya saca por antigüedad, bloquea los lotes y deja en el
kardex un movimiento por tramo con el costo real de cada uno. El PEPS se
construyó en INV precisamente para llegar aquí resuelto.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from inventario.kardex import registrar_movimiento
from inventario.models import LoteInventario, MovimientoInventario
from inventario.peps import consumir
from sedes.models import Sede
from suscripciones.models import Licorera

from .correo import enviar_aviso_de_anulacion
from .jornada import jornada_actual, jornada_de
from .models import DetalleVenta, Venta


@transaction.atomic
def registrar_venta(*, licorera, usuario, lineas, medio_pago, monto_recibido=None,
                    sede=None, observacion=None):
    """
    Registra una venta y descuenta el inventario (RF-VEN-01 y RF-VEN-02).

    `lineas` es una lista de diccionarios con `producto` y `cantidad`. El precio
    no se recibe: se toma del catálogo en este instante y se congela en la
    línea, porque es el sistema quien dice a cómo se vende y no quien llama.

    `observacion` es la nota corta con la que el negocio reconoce una venta que
    no se llevó el cliente en la mano, del estilo de «mesa 1, pedido 3».

    Va entera en una transacción. Una venta que descontara tres referencias de
    cuatro, o que cobrara sin descontar, dejaría el inventario diciendo una cosa
    y la caja otra, y no hay forma de descubrirlo hasta el conteo físico.
    """
    if not lineas:
        raise ValidationError("La venta no tiene ninguna línea.")

    if sede is None:
        sede = Sede.principal_de(licorera)
    if sede is None:
        raise ValidationError("La licorera no tiene ninguna sede desde la que vender.")

    # Todo lo que puede rechazar la venta se comprueba ANTES de tocar el
    # inventario. La transacción desharía igualmente un rechazo tardío, pero
    # consumir lotes para descubrir después que el efectivo no alcanzaba es
    # bloquear filas que otra caja podría estar esperando.
    revisadas = [_revisar(linea, licorera) for linea in lineas]
    total = sum(subtotal for _, _, subtotal in revisadas)
    _comprobar_pago(medio_pago, monto_recibido, total)

    venta = Venta.objects.create(
        licorera=licorera, sede=sede, usuario=usuario,
        consecutivo=_siguiente_consecutivo(licorera),
        total=total, medio_pago=medio_pago, monto_recibido=monto_recibido,
        observacion=(observacion or "").strip() or None,
    )

    for producto, cantidad, subtotal in revisadas:
        DetalleVenta.objects.create(
            venta=venta, producto=producto, cantidad=cantidad,
            precio_unitario=producto.precio_venta, subtotal=subtotal,
        )
        # El descuento y el costo real los pone el PEPS. Si no hay existencias
        # suficientes, levanta y la transacción entera se deshace: una venta a
        # medias es peor que una venta rechazada.
        consumir(
            producto=producto, sede=sede, cantidad=cantidad,
            tipo=MovimientoInventario.Tipo.VENTA, usuario=usuario,
            documento_tipo=MovimientoInventario.Documento.VENTA,
            documento_id=venta.id,
        )

    return venta


def _revisar(linea, licorera):
    """Comprueba una línea y devuelve el producto, la cantidad y su subtotal."""
    producto = linea["producto"]
    cantidad = int(linea["cantidad"])

    if producto.licorera_id != licorera.id:
        # El serializador ya limita el catálogo, pero la regla del aislamiento
        # se comprueba donde vive la operación y no solo donde se escribe el
        # formulario.
        raise ValidationError("Ese producto no pertenece a esta licorera.")
    if not producto.activo:
        raise ValidationError(
            "«%s» está descontinuado y no se puede vender." % producto.nombre)
    if cantidad <= 0:
        raise ValidationError("La cantidad de cada línea debe ser mayor que cero.")

    return producto, cantidad, producto.precio_venta * cantidad


def _comprobar_pago(medio_pago, monto_recibido, total):
    """
    El efectivo admite un monto recibido; los demás medios, no.

    Una transferencia de la que alguien dijera que «recibió más» no significa
    nada, y el cambio que el sistema calculara sería dinero que nadie entregó.

    El monto es opcional incluso en efectivo: quien paga justo no tiene que
    escribir nada, y el cambio es cero.
    """
    if monto_recibido is None:
        return
    if not medio_pago.es_efectivo:
        raise ValidationError(
            "Solo el pago en efectivo lleva monto recibido: no hay cambio que "
            "devolver en una transferencia ni en una tarjeta.")
    if monto_recibido < total:
        raise ValidationError(
            "El efectivo recibido no alcanza: el total es %s." % total)


def _siguiente_consecutivo(licorera):
    """
    El número de venta que ve el negocio, sin huecos ni repeticiones.

    La fila de la licorera se bloquea antes de mirar el último número. Dos cajas
    vendiendo a la vez son el caso normal y no el raro: sin el bloqueo, las dos
    leerían el mismo máximo y pedirían el mismo número, y la restricción de la
    base rechazaría una de las dos ventas en mitad del cobro.

    Un hueco en la numeración tampoco es inocente: es lo que permite afirmar que
    no falta ninguna venta.
    """
    Licorera.objects.select_for_update().get(pk=licorera.pk)
    ultimo = (
        Venta.objects
        .filter(licorera=licorera)
        .aggregate(ultimo=Max("consecutivo"))["ultimo"]
    )
    return (ultimo or 0) + 1


@transaction.atomic
def se_puede_anular(venta):
    """
    Si una venta admite anulación ahora mismo.

    La respuesta la da el servidor y no la pantalla: la jornada empieza a las
    seis de la mañana, y escribir esa hora también en el navegador la dejaría
    en dos sitios que pueden dejar de coincidir. La pantalla pregunta y
    enseña el botón según lo que se le conteste; aquí se decide.
    """
    return (venta.estado == Venta.Estado.ACTIVA
            and jornada_de(venta.fecha) == jornada_actual())


def anular_venta(*, venta, usuario, motivo):
    """
    Deshace una venta devolviendo la mercancía a sus lotes (RF-VEN-04).

    La venta no se borra: se marca, conserva su número y su detalle, y queda
    con el motivo y con quien la anuló. Un hueco en la numeración es lo único
    que impediría afirmar después que no falta ninguna venta.

    Cada unidad vuelve al lote del que salió: el kardex sabe de qué lote salió
    cada tramo, de modo que la devolución es
    exacta y el PEPS sigue siendo cierto después. Crear un lote nuevo con lo
    devuelto sería más fácil y lo pondría al final de la cola: lo devuelto se
    vendería después de lo que se compró más tarde, y su costo dejaría de
    corresponder a la compra por la que entró.
    """
    if venta.estado != Venta.Estado.ACTIVA:
        raise ValidationError("Esa venta ya está anulada.")
    if not (motivo or "").strip():
        raise ValidationError("Escribe el motivo de la anulación.")
    if not se_puede_anular(venta):
        raise ValidationError(
            "Solo se anulan las ventas de la jornada en curso. Una venta anterior "
            "ya entró en un cierre de caja, y deshacerla descuadraría un día cerrado.")

    salidas = (
        MovimientoInventario.objects
        .filter(licorera=venta.licorera,
                documento_tipo=MovimientoInventario.Documento.VENTA,
                documento_id=venta.id,
                tipo=MovimientoInventario.Tipo.VENTA)
        .select_related("lote", "producto")
        .order_by("id")
    )

    for salida in salidas:
        # Se bloquea el lote por lo mismo que al consumirlo: entre leer sus
        # unidades y escribirlas no puede colarse otra operación.
        lote = (LoteInventario.objects
                .select_for_update()
                .get(pk=salida.lote_id))
        devueltas = -salida.cantidad
        lote.cantidad_disponible += devueltas
        lote.save(update_fields=["cantidad_disponible"])

        registrar_movimiento(
            producto=salida.producto, sede=venta.sede,
            tipo=MovimientoInventario.Tipo.ANULACION_VENTA,
            cantidad=devueltas, usuario=usuario, lote=lote,
            # El costo es el que llevaba la salida, no el del lote hoy: lo que
            # vuelve tiene que valer lo que valió al salir.
            costo_unitario=salida.costo_unitario,
            documento_tipo=MovimientoInventario.Documento.VENTA,
            documento_id=venta.id,
            motivo=motivo,
        )

    venta.estado = Venta.Estado.ANULADA
    venta.motivo_anulacion = motivo.strip()
    venta.anulada_por = usuario
    venta.fecha_anulacion = timezone.now()
    venta.save(update_fields=["estado", "motivo_anulacion", "anulada_por",
                              "fecha_anulacion"])

    # El aviso sale al administrador por lo mismo que el de la caja
    # descuadrada: una anulación no deja rastro en el cierre —lo anulado no
    # cuenta como dinero— y el historial solo la enseña a quien va a buscarla.
    enviar_aviso_de_anulacion(venta)
    return venta
