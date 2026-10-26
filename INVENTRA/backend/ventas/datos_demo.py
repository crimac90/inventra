"""
Las ventas con las que se enseña el módulo.

Vive aquí por lo mismo que el catálogo vive en `inventario/datos_demo.py`: el
comando es la puerta por la que se pide, y esto es lo que se pide.

Nada se inserta a mano. Cada venta pasa por `registrar_venta` y cada anulación
por `anular_venta`, que son las mismas funciones que llama el punto de venta,
de modo que las existencias bajan por PEPS, el kardex guarda el costo real del
lote del que salió cada unidad y los consecutivos se reparten como se reparten
de verdad. Si mañana cambia una regla de la venta, estos datos cambian con ella
o la carga falla, que es justo lo que debe pasar.

Las fechas. `venta.fecha` se llena sola al crear la fila y no admite un valor, que es como
el sistema impide antedatar una venta. Un juego de datos cargado de una sentada
nacería entero en el mismo minuto y el historial no tendría nada que filtrar ni
el cierre de caja ninguna jornada anterior que enseñar. Por eso, creadas las
filas por la vía normal, este módulo retrocede sus marcas con `update()`. Se
cambia cuándo se dice que ocurrió, nunca qué ocurrió ni en qué orden: las
ventas se crean de la más antigua a la más reciente, así que cada saldo del
kardex se calculó con las existencias que de verdad había en ese punto.

Las de la jornada en curso no se tocan: nacen con la hora de la carga, que es
la correcta.

La madrugada. Dos ventas están puestas a la una y media de la mañana a propósito. Pertenecen
a la noche anterior, que es la jornada en la que se vendieron, y son lo que
hace visible en los datos la definición de día del módulo: sin ellas, el
comportamiento está construido y nadie lo ve.

El correo no sale durante la carga. Una anulación avisa por correo y un cierre
descuadrado también, y cargar datos de demostración no es un día de trabajo: si alguien tiene configurado un servidor
de correo de verdad, la carga le escribiría a los administradores por ventas
inventadas. Mientras dura, el envío se desvía a un destino que no manda nada.
"""

from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from inventario.models import MovimientoInventario, Producto
from sedes.models import Sede

from .caja import resumen_de
from .jornada import jornada_actual
from .models import CierreCaja, DetalleVenta, MedioPago, Venta
from .operaciones import anular_venta, registrar_venta

# Cada venta es:
#
#   hace cuántas jornadas, hora, minuto, quién vendió, medio de pago,
#   [(referencia, unidades), ...], nota
#
# «quién» es «vendedor» o «administrador»; la nota puede ir vacía.
#
# Las canastas no son al azar. Hay compras de mostrador de una botella, rondas
# de cerveza con hielo y vasos, una venta de mesa con su nota, y cantidades que
# acumuladas cruzan el segundo lote del Ron Medellín, que es lo que hace que el
# PEPS se pueda enseñar con el kardex delante en vez de contarlo.
VENTAS = [
    (7, 19, 40, "vendedor", MedioPago.EFECTIVO,
     [("Aguardiente Antioqueño Tapa Roja 750 ml", 2), ("Cerveza Águila 330 ml", 6)], ""),
    (7, 21, 15, "vendedor", MedioPago.EFECTIVO,
     [("Ron Medellín Añejo 3 años 750 ml", 1), ("Gaseosa Coca-Cola 400 ml", 2)], ""),
    (7, 22, 50, "vendedor", MedioPago.TARJETA,
     [("Whisky Old Parr 12 años 750 ml", 1)], ""),

    (6, 20, 10, "vendedor", MedioPago.EFECTIVO,
     [("Cerveza Poker 330 ml", 12), ("Hielo en bolsa 2 kg", 1)], "Mesa 3"),
    (6, 23, 5, "vendedor", MedioPago.TRANSFERENCIA,
     [("Ron Medellín Añejo 3 años 750 ml", 2), ("Agua Cristal sin gas 600 ml", 4)], ""),
    (6, 1, 30, "vendedor", MedioPago.EFECTIVO,
     [("Cerveza Águila 330 ml", 10), ("Cigarrillos Marlboro cajetilla x20", 1)], ""),

    (5, 19, 25, "administrador", MedioPago.EFECTIVO,
     [("Aguardiente Néctar Azul 750 ml", 1)], ""),
    (5, 20, 45, "vendedor", MedioPago.EFECTIVO,
     [("Ron Viejo de Caldas 8 años 750 ml", 2), ("Gaseosa Postobón Manzana 400 ml", 2)], ""),
    (5, 22, 30, "vendedor", MedioPago.TARJETA,
     [("Whisky Johnnie Walker Red Label 750 ml", 1), ("Bebida energizante Red Bull 250 ml", 2)],
     "Mesa 1, pedido 2"),

    (4, 18, 50, "vendedor", MedioPago.EFECTIVO,
     [("Cerveza Club Colombia Dorada 330 ml", 6)], ""),
    (4, 21, 0, "vendedor", MedioPago.EFECTIVO,
     [("Ron Medellín Añejo 3 años 750 ml", 3), ("Vasos desechables 9 oz x25", 1),
      ("Hielo en bolsa 2 kg", 2)], "Mesa 2"),
    (4, 23, 40, "vendedor", MedioPago.TRANSFERENCIA,
     [("Aguardiente Antioqueño Tapa Roja 1000 ml", 2)], ""),

    (3, 19, 15, "vendedor", MedioPago.EFECTIVO,
     [("Cerveza Pilsen 330 ml", 8), ("Cigarrillos L&M cajetilla x20", 1)], ""),
    (3, 20, 30, "administrador", MedioPago.EFECTIVO,
     [("Vino Gato Negro Cabernet Sauvignon 750 ml", 1)], ""),
    (3, 22, 10, "vendedor", MedioPago.EFECTIVO,
     [("Ron Medellín Añejo 3 años 750 ml", 4), ("Cerveza Corona 355 ml", 6)], "Mesa 4"),
    (3, 1, 20, "vendedor", MedioPago.TARJETA,
     [("Aguardiente Antioqueño Tapa Roja 750 ml", 3)], ""),

    (2, 19, 55, "vendedor", MedioPago.EFECTIVO,
     [("Cerveza Águila 330 ml", 12), ("Agua Cristal sin gas 600 ml", 2)], ""),
    (2, 21, 40, "vendedor", MedioPago.TRANSFERENCIA,
     [("Whisky Buchanan's Deluxe 12 años 750 ml", 1)], ""),
    (2, 23, 15, "vendedor", MedioPago.EFECTIVO,
     [("Ron Viejo de Caldas 8 años 375 ml", 2), ("Gaseosa Coca-Cola 400 ml", 3)], ""),

    (1, 18, 30, "vendedor", MedioPago.EFECTIVO,
     [("Aguardiente Antioqueño Sin Azúcar 750 ml", 2)], ""),
    (1, 20, 20, "vendedor", MedioPago.EFECTIVO,
     [("Cerveza Poker 330 ml", 18), ("Hielo en bolsa 2 kg", 2),
      ("Vasos desechables 9 oz x25", 2)], "Mesa 1, pedido 3"),
    (1, 21, 50, "vendedor", MedioPago.TARJETA,
     [("Ron Medellín Añejo 3 años 750 ml", 2), ("Vino Santa Helena Reservado Merlot 750 ml", 1)],
     ""),
    (1, 23, 30, "vendedor", MedioPago.EFECTIVO,
     [("Cerveza Heineken 330 ml", 6)], ""),

    # La jornada en curso queda abierta y con poco movimiento, para que quien
    # recorra el sistema tenga una caja que cerrar y no una ya cuadrada.
    (0, None, None, "vendedor", MedioPago.EFECTIVO,
     [("Aguardiente Antioqueño Tapa Roja 750 ml", 1), ("Cerveza Águila 330 ml", 4)], ""),
    (0, None, None, "vendedor", MedioPago.TRANSFERENCIA,
     [("Ron Medellín Añejo 3 años 1000 ml", 1)], "Mesa 2"),
]

# La venta que se deshace: su posición en la lista de arriba y el motivo.
#
# Es de una jornada ya cerrada a propósito. Enseña las dos mitades de la regla:
# en el historial se ve anulada, con su motivo y con quién la anuló, y al
# intentar anularla de nuevo el sistema contesta que solo se anulan las de la
# jornada en curso.
#
# Se deshace en el momento que le toca —justo después de registrarla y antes
# de seguir con las siguientes—, no al final de la carga. El saldo que el
# kardex guarda en cada movimiento es una foto del instante en que se escribió,
# así que anular al final dejaría esa foto tomada después de ventas que
# cronológicamente ocurren más tarde, y el kardex leído por fecha contaría una
# historia que no cuadra con las existencias.
ANULADA = (10, "El cliente devolvió la mercancía sin abrir")

# Cierres ya hechos: hace cuántas jornadas, efectivo contado y explicación.
#
# Dos, y distintos a propósito. El de hace tres días cerró con un faltante
# explicado, que es como queda una diferencia resuelta; el de ayer con un
# faltante SIN explicar, que es lo que mantiene vivo el aviso del panel. Sin el
# segundo, esa alerta está construida y no se ve.
CIERRES = [
    (3, "Se pagó un domicilio con efectivo de la caja"),
    (1, None),
]

# Cuánto falta en cada caja respecto de lo que dice el sistema.
FALTANTES = {3: Decimal("12000"), 1: Decimal("15000")}


@contextmanager
def _sin_correo():
    """Desvía el correo mientras dura la carga."""
    original = settings.EMAIL_BACKEND
    settings.EMAIL_BACKEND = "django.core.mail.backends.dummy.EmailBackend"
    try:
        yield
    finally:
        settings.EMAIL_BACKEND = original


def _momento(jornadas_atras, hora, minuto):
    """
    El instante en que ocurrió una venta de una jornada anterior.

    Una hora anterior a las seis pertenece a la jornada del día previo, así que
    su fecha real es la del día siguiente: así es como una venta de la una y
    media de la mañana se cierra con la noche en la que se vendió.
    """
    jornada = jornada_actual() - timedelta(days=jornadas_atras)
    dia = jornada + timedelta(days=1) if hora < 6 else jornada
    ingenuo = timezone.datetime(dia.year, dia.month, dia.day, hora, minuto)
    return timezone.make_aware(ingenuo, timezone.get_current_timezone())


def _fechar_venta(venta, cuando):
    """Retrocede la venta y los movimientos de inventario que causó."""
    Venta.objects.filter(pk=venta.pk).update(fecha=cuando)
    MovimientoInventario.objects.filter(
        licorera=venta.licorera,
        documento_tipo=MovimientoInventario.Documento.VENTA,
        documento_id=venta.id,
    ).update(fecha=cuando)
    venta.refresh_from_db()


def _efectivo_entregado(total):
    """
    Lo que el cliente pone sobre el mostrador: el total redondeado hacia
    arriba al siguiente billete de diez mil. Nadie paga justo, y un juego de
    datos donde el cambio siempre es cero no enseña para qué está ese campo.
    """
    diez_mil = Decimal("10000")
    return (total / diez_mil).to_integral_value(rounding="ROUND_CEILING") * diez_mil


@transaction.atomic
def sembrar(licorera, vendedor, administrador):
    """
    Registra las ventas, la anulación y los cierres de una licorera.

    Repetible: si la licorera ya tiene ventas, no se añade ninguna. Devuelve
    cuántas se crearon y cuántas cajas quedaron cerradas.
    """
    if Venta.objects.filter(licorera=licorera).exists():
        return 0, 0

    sede = Sede.principal_de(licorera)
    catalogo = {p.nombre: p for p in Producto.objects.filter(licorera=licorera)}
    medios = {m.nombre: m for m in MedioPago.objects.all()}
    autores = {"vendedor": vendedor, "administrador": administrador}

    posicion_anulada, motivo_anulacion = ANULADA

    with _sin_correo():
        registradas = []
        for numero, (jornadas, hora, minuto, quien, medio, canasta, nota) in enumerate(VENTAS):
            lineas = [{"producto": catalogo[nombre], "cantidad": unidades}
                      for nombre, unidades in canasta
                      if nombre in catalogo]
            if not lineas:
                continue

            total = sum(l["producto"].precio_venta * l["cantidad"] for l in lineas)
            recibido = (_efectivo_entregado(total)
                        if medio == MedioPago.EFECTIVO else None)

            venta = registrar_venta(
                licorera=licorera, usuario=autores[quien], sede=sede,
                lineas=lineas, medio_pago=medios[medio],
                monto_recibido=recibido, observacion=nota,
            )
            registradas.append((venta, jornadas, hora, minuto))

            # Se deshace aquí, con las ventas posteriores todavía sin
            # registrar. El sistema solo permite anular una venta de la
            # jornada en curso, y esa regla no se esquiva para cargar datos:
            # la venta acaba de nacer, así que todavía es de hoy; las fechas
            # de todas se retroceden después.
            if numero == posicion_anulada:
                anular_venta(venta=venta, usuario=administrador,
                             motivo=motivo_anulacion)

        for venta, jornadas, hora, minuto in registradas:
            # Las de la jornada en curso nacen con la hora correcta.
            if jornadas == 0:
                continue
            cuando = _momento(jornadas, hora, minuto)
            _fechar_venta(venta, cuando)
            if venta.fecha_anulacion is not None:
                # La anulación ocurrió después de la venta, no antes.
                Venta.objects.filter(pk=venta.pk).update(
                    fecha_anulacion=cuando + timedelta(minutes=25))
                MovimientoInventario.objects.filter(
                    licorera=licorera,
                    documento_tipo=MovimientoInventario.Documento.VENTA,
                    documento_id=venta.id,
                    tipo=MovimientoInventario.Tipo.ANULACION_VENTA,
                ).update(fecha=cuando + timedelta(minutes=25))

        cerradas = _cerrar_jornadas_pasadas(licorera, sede, administrador)

    return len(registradas), cerradas


def _cerrar_jornadas_pasadas(licorera, sede, usuario):
    """
    Deja cerradas las cajas de dos jornadas anteriores.

    Es el único sitio de la carga que no pasa por su operación, y la razón es
    que esa operación se niega a hacerlo a propósito: `cerrar_jornada` solo
    cierra la jornada en curso, porque rehacer una anterior sería contar un
    cajón que ya se vació. La regla es correcta y no se toca.

    Lo que sí se conserva es de dónde salen las cifras: los totales por medio
    de pago los calcula `resumen_de`, la misma función que usa el cierre de
    verdad, de modo que lo único escrito a mano es cuánto efectivo apareció en
    el cajón, que en la vida real también lo escribe una persona.
    """
    cerradas = 0
    for jornadas_atras, explicacion in CIERRES:
        jornada = jornada_actual() - timedelta(days=jornadas_atras)
        resumen = resumen_de(licorera, sede, jornada)
        contado = resumen["efectivo"] - FALTANTES[jornadas_atras]

        CierreCaja.objects.update_or_create(
            sede=sede, fecha=jornada,
            defaults={
                "licorera": licorera,
                "total_efectivo": resumen["efectivo"],
                "total_transferencia": resumen["transferencia"],
                "total_tarjeta": resumen["tarjeta"],
                "efectivo_contado": contado,
                "diferencia": contado - resumen["efectivo"],
                "usuario": usuario,
                "observacion": explicacion,
            },
        )
        cerradas += 1
    return cerradas


def retirar(dominio):
    """
    Borra las ventas de las licoreras de demostración.

    De las hojas a la raíz: **el detalle va antes que la venta**, porque
    `DetalleVenta.venta` está declarada con PROTECT y la base se niega a borrar
    una venta con líneas colgando. El orden de un borrado no se deduce: se lee
    en las llaves.

    Los movimientos de inventario que causaron las ventas los retira
    `inventario`, que es de donde son.
    """
    de_la_licorera = {"licorera__correo__endswith": dominio}
    cierres = CierreCaja.objects.filter(**de_la_licorera).delete()[0]
    DetalleVenta.objects.filter(venta__licorera__correo__endswith=dominio).delete()
    ventas = Venta.objects.filter(**de_la_licorera).delete()[0]
    return cierres, ventas
