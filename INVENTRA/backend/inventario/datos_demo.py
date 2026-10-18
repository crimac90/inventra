"""
El catálogo con el que se enseña el módulo de inventario.

Vive aquí y no en el comando que lo carga por la misma razón que
`operaciones.py` no vive en una vista: el comando es la puerta por la que se
pide, y esto es lo que se pide. En `suscripciones` no tendría nada que hacer un
listado de aguardientes.

Nada se inserta a mano. Las entradas pasan por `registrar_entrada` y los
ajustes por `ajustar_existencias`, que son las mismas funciones que usa la
pantalla, de modo que los lotes, el kardex y los saldos quedan cuadrados porque
los calculó el sistema y no porque alguien los escribiera cuadrados. Si una
regla cambia, estos datos cambian con ella o la carga falla, que es justo lo
que debe pasar.

LAS FECHAS
`fecha_ingreso`, `fecha` y `fecha_creacion` se llenan solas al crear la fila y
no admiten un valor: así protegen al kardex de que nadie antedate un
movimiento. Un juego de datos cargado de una sentada nacería entonces entero en
el mismo minuto, y con él se perdería lo único que el PEPS necesita enseñar:
que un lote es más viejo que otro. Por eso, una vez creadas las filas por la
vía normal, este módulo retrocede sus marcas de tiempo con `update()`, que no
pasa por el modelo. Se cambia cuándo se dice que ocurrió, nunca qué ocurrió ni
en qué orden: las compras se crean de la más antigua a la más reciente, así que
cada saldo del kardex se calculó con las existencias que de verdad había en ese
punto de la historia.
"""

from datetime import timedelta

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from sedes.models import Sede

from .models import (Categoria, EntradaMercancia, LoteInventario,
                     MovimientoInventario, Producto)
from .operaciones import ajustar_existencias, registrar_entrada

PROVEEDOR = "Distribuidora La Mayorista"

# Cada fila es una referencia del catálogo:
#
#   nombre, categoría, presentación, mínimo, precio de venta, compras
#
# y cada compra, (hace cuántos días, unidades, costo unitario).
#
# Las cantidades no son adorno. Están puestas para que la pantalla tenga algo
# que decir sin preparar nada: hay referencias con varias compras a distinto
# costo —lo que el PEPS y el costo promedio necesitan para verse—, referencias
# por debajo de su mínimo, y una sin ninguna compra, que es como queda un
# producto el día que se crea.
CATALOGO_PRINCIPAL = [
    ("Aguardiente Antioqueño Tapa Roja 750 ml", "Aguardiente", "botella", 12, 52000,
     [(95, 60, 38500), (40, 48, 39800)]),
    ("Aguardiente Antioqueño Sin Azúcar 750 ml", "Aguardiente", "botella", 12, 54000,
     [(88, 36, 40200)]),
    ("Aguardiente Antioqueño Tapa Roja 375 ml", "Aguardiente", "media", 10, 28000,
     [(88, 24, 20500)]),
    ("Aguardiente Antioqueño Tapa Roja 1000 ml", "Aguardiente", "litro", 6, 68000,
     [(60, 18, 51000)]),
    ("Aguardiente Antioqueño Tapa Roja 1750 ml", "Aguardiente", "garrafa", 4, 115000,
     [(60, 8, 86000)]),
    ("Aguardiente Néctar Azul 750 ml", "Aguardiente", "botella", 10, 49000,
     [(72, 30, 36000)]),
    ("Aguardiente Néctar Club 750 ml", "Aguardiente", "botella", 10, 51000,
     [(72, 24, 37500)]),
    ("Aguardiente Cristal 750 ml", "Aguardiente", "botella", 8, 46000,
     [(30, 6, 34000)]),

    ("Ron Medellín Añejo 3 años 750 ml", "Ron", "botella", 10, 46000,
     [(110, 40, 33500), (55, 30, 35200), (12, 24, 36800)]),
    ("Ron Medellín Añejo 8 años 750 ml", "Ron", "botella", 6, 72000,
     [(80, 15, 54000)]),
    ("Ron Medellín Añejo 3 años 1000 ml", "Ron", "litro", 5, 60000,
     [(70, 12, 44000)]),
    ("Ron Viejo de Caldas 8 años 750 ml", "Ron", "botella", 10, 50000,
     [(100, 36, 37800), (25, 24, 39500)]),
    ("Ron Viejo de Caldas 8 años 375 ml", "Ron", "media", 8, 27000,
     [(100, 18, 19800)]),
    ("Ron Viejo de Caldas Gran Reserva 750 ml", "Ron", "botella", 4, 95000,
     [(45, 6, 71000)]),
    ("Ron Santa Fe 750 ml", "Ron", "botella", 6, 42000,
     [(130, 12, 31000)]),

    ("Cerveza Poker 330 ml", "Cerveza", "unidad", 48, 3500, [(20, 240, 2350)]),
    ("Cerveza Águila 330 ml", "Cerveza", "unidad", 48, 3500, [(20, 240, 2350)]),
    ("Cerveza Club Colombia Dorada 330 ml", "Cerveza", "unidad", 36, 4500,
     [(20, 144, 3150)]),
    ("Cerveza Club Colombia Roja 330 ml", "Cerveza", "unidad", 36, 4500,
     [(20, 96, 3150)]),
    ("Cerveza Costeña 330 ml", "Cerveza", "unidad", 24, 3200, [(35, 72, 2200)]),
    ("Cerveza Pilsen 330 ml", "Cerveza", "unidad", 24, 3300, [(35, 120, 2250)]),
    ("Cerveza Corona 355 ml", "Cerveza", "unidad", 24, 6500, [(15, 72, 4500)]),
    ("Cerveza Heineken 330 ml", "Cerveza", "unidad", 24, 6000, [(15, 48, 4200)]),
    ("Cerveza Andina 330 ml", "Cerveza", "unidad", 24, 3200, [(50, 12, 2150)]),

    ("Whisky Old Parr 12 años 750 ml", "Whisky", "botella", 6, 148000,
     [(85, 12, 110000), (18, 6, 114500)]),
    ("Whisky Buchanan's Deluxe 12 años 750 ml", "Whisky", "botella", 6, 165000,
     [(85, 10, 125000)]),
    ("Whisky Johnnie Walker Red Label 750 ml", "Whisky", "botella", 6, 99000,
     [(65, 12, 74000)]),
    ("Whisky Johnnie Walker Black Label 750 ml", "Whisky", "botella", 4, 179000,
     [(65, 6, 135000)]),
    ("Whisky Something Special 750 ml", "Whisky", "botella", 4, 89000,
     [(40, 8, 66000)]),
    ("Whisky Grant's Triple Wood 750 ml", "Whisky", "botella", 4, 78000,
     [(40, 3, 58000)]),

    ("Vino Gato Negro Cabernet Sauvignon 750 ml", "Vino", "botella", 6, 38000,
     [(75, 24, 27500)]),
    ("Vino Gato Negro Sauvignon Blanc 750 ml", "Vino", "botella", 6, 38000,
     [(75, 18, 27500)]),
    ("Vino Casillero del Diablo Carmenere 750 ml", "Vino", "botella", 4, 56000,
     [(58, 12, 41500)]),
    ("Vino Santa Helena Reservado Merlot 750 ml", "Vino", "botella", 6, 34000,
     [(58, 18, 24000)]),
    ("Vino Frontera Cabernet Sauvignon 750 ml", "Vino", "botella", 6, 32000,
     [(32, 24, 22500)]),
    ("Vino Undurraga Carmenere 750 ml", "Vino", "botella", 4, 45000,
     [(32, 10, 33000)]),
    ("Vino Gran Tarapacá Cabernet Sauvignon 750 ml", "Vino", "botella", 4, 52000,
     []),

    ("Agua Cristal sin gas 600 ml", "Otros", "unidad", 24, 2500, [(10, 120, 1500)]),
    ("Gaseosa Coca-Cola 400 ml", "Otros", "unidad", 24, 3500, [(10, 96, 2200)]),
    ("Gaseosa Postobón Manzana 400 ml", "Otros", "unidad", 24, 3500, [(10, 72, 2200)]),
    ("Bebida energizante Red Bull 250 ml", "Otros", "unidad", 12, 8000, [(22, 48, 5600)]),
    ("Hielo en bolsa 2 kg", "Otros", "unidad", 10, 5000, [(5, 40, 3000)]),
    ("Cigarrillos Marlboro cajetilla x20", "Otros", "unidad", 20, 14000, [(28, 60, 11200)]),
    ("Cigarrillos L&M cajetilla x20", "Otros", "unidad", 20, 12000, [(28, 40, 9500)]),
    ("Vasos desechables 9 oz x25", "Otros", "unidad", 10, 6000, [(28, 24, 4200)]),
]

# El segundo negocio no es una copia pequeña del primero: existe para que el
# aislamiento se pueda comprobar entrando. Repite tres referencias a propósito,
# con otro precio y otro costo, porque lo que hay que ver es que cada licorera
# tiene las suyas y no las del vecino.
CATALOGO_SECUNDARIO = [
    ("Aguardiente Antioqueño Tapa Roja 750 ml", "Aguardiente", "botella", 6, 53000,
     [(20, 24, 39000)]),
    ("Ron Medellín Añejo 3 años 750 ml", "Ron", "botella", 6, 47000,
     [(20, 12, 34000)]),
    ("Cerveza Poker 330 ml", "Cerveza", "unidad", 24, 3600, [(10, 120, 2400)]),
    ("Cerveza Águila 330 ml", "Cerveza", "unidad", 24, 3600, [(10, 96, 2400)]),
    ("Whisky Johnnie Walker Red Label 750 ml", "Whisky", "botella", 4, 102000,
     [(30, 4, 75000)]),
    ("Agua Cristal sin gas 600 ml", "Otros", "unidad", 24, 2600, [(8, 60, 1550)]),
]

# Diferencias de conteo ya aplicadas, para que el kardex no sea una lista de
# entradas: nombre, unidades (con signo), motivo y hace cuántos días.
#
# Las tres direcciones que el ajuste admite están representadas, y una de ellas
# deja una referencia en cero: un agotado que se puede explicar es más útil que
# uno que simplemente nunca se compró.
AJUSTES = [
    ("Ron Viejo de Caldas 8 años 375 ml", -3, "Rotura en bodega", 20),
    ("Cerveza Costeña 330 ml", -72, "Conteo físico: caja no hallada en bodega", 14),
    ("Vino Santa Helena Reservado Merlot 750 ml", 4,
     "Conteo físico: unidades encontradas", 9),
]

# Referencias retiradas de la venta que conservan su historial (RF-INV-04).
DESCONTINUADOS = ["Ron Santa Fe 750 ml"]


def sembrar(licorera, usuario, catalogo, ajustes=(), descontinuados=()):
    """
    Deja el catálogo de una licorera montado y con existencias.

    Repetible: una referencia que ya existe se respeta tal como está y no
    vuelve a comprarse, así que ejecutar la carga dos veces no infla el
    inventario. Devuelve cuántas referencias se crearon en esta pasada.
    """
    sede = Sede.principal_de(licorera)
    categorias = {c.nombre: c for c in Categoria.objects.filter(licorera=licorera)}
    nuevos = {}
    # Las compras se juntan por día. Un proveedor no entrega una referencia por
    # viaje, y una entrada por línea dejaría el juego de datos sin un solo
    # ejemplo de lo que la pantalla permite hacer: recibir varias de una vez.
    por_dia = {}

    for numero, fila in enumerate(catalogo, start=1):
        nombre, categoria, presentacion, minimo, precio, compras = fila
        producto, creado = Producto.objects.get_or_create(
            licorera=licorera, nombre=nombre,
            defaults={
                "categoria": categorias[categoria],
                "presentacion": presentacion,
                "stock_minimo": minimo,
                "precio_venta": precio,
                # Ficticio, con la longitud y el prefijo de país de uno real,
                # para que el buscador por código tenga qué encontrar.
                "codigo_barras": "770%010d" % numero,
            },
        )
        if not creado:
            continue
        nuevos[nombre] = producto

        for dias, cantidad, costo in compras:
            por_dia.setdefault(dias, []).append(
                {"producto": producto, "cantidad": cantidad, "costo_unitario": costo})

        # La referencia no puede ser más joven que su primera compra.
        primera = max((d for d, _, _ in compras), default=0)
        Producto.objects.filter(pk=producto.pk).update(fecha_creacion=_hace(primera))

    # De la entrega más antigua a la más reciente. El orden es el del kardex:
    # cada saldo se calcula con lo que había hasta ese momento.
    for dias in sorted(por_dia, reverse=True):
        entrada = registrar_entrada(
            licorera=licorera, usuario=usuario, sede=sede, proveedor=PROVEEDOR,
            lineas=por_dia[dias],
        )
        _fechar_entrada(entrada, _hace(dias))

    for nombre, cantidad, motivo, dias in ajustes:
        producto = nuevos.get(nombre)
        if producto is None:
            continue
        _ajustar(producto, usuario, cantidad, motivo, _hace(dias))

    for nombre in descontinuados:
        producto = nuevos.get(nombre)
        if producto is not None:
            producto.activo = False
            producto.save(update_fields=["activo"])

    return len(nuevos)


@transaction.atomic
def _ajustar(producto, usuario, cantidad, motivo, cuando):
    """
    Aplica una diferencia de conteo y la fecha.

    El ajuste no devuelve lo que creó, y tampoco debería: quien lo llama de
    verdad no lo necesita. Para fecharlo se mira qué filas aparecieron después
    de llamarlo, que dentro de una transacción es exacto.
    """
    ultimo_lote = LoteInventario.objects.aggregate(Max("id"))["id__max"] or 0
    ultimo_movimiento = MovimientoInventario.objects.aggregate(Max("id"))["id__max"] or 0

    ajustar_existencias(producto=producto, usuario=usuario, cantidad=cantidad,
                        motivo=motivo)

    LoteInventario.objects.filter(id__gt=ultimo_lote).update(fecha_ingreso=cuando)
    MovimientoInventario.objects.filter(id__gt=ultimo_movimiento).update(fecha=cuando)


def _fechar_entrada(entrada, cuando):
    """Retrocede la entrada, sus lotes y sus movimientos al mismo instante."""
    EntradaMercancia.objects.filter(pk=entrada.pk).update(fecha=cuando)
    LoteInventario.objects.filter(entrada=entrada).update(fecha_ingreso=cuando)
    MovimientoInventario.objects.filter(
        licorera=entrada.licorera,
        documento_tipo=MovimientoInventario.Documento.ENTRADA,
        documento_id=entrada.id,
    ).update(fecha=cuando)


def _hace(dias):
    """
    El instante de hace tantos días, a media mañana.

    La hora se fija en vez de conservar la actual para que una carga hecha de
    madrugada no deje entradas registradas a las tres de la mañana.
    """
    momento = timezone.localtime() - timedelta(days=dias)
    return momento.replace(hour=9, minute=30, second=0, microsecond=0)


def retirar(dominio):
    """
    Borra el inventario de las licoreras de demostración.

    El orden va de las hojas a la raíz, porque las llaves foráneas están
    declaradas con PROTECT y la base se niega a borrar un lote con movimientos
    colgando. Devuelve lo retirado, en el mismo orden, para poder contarlo.
    """
    de_la_licorera = {"licorera__correo__endswith": dominio}
    movimientos = MovimientoInventario.objects.filter(**de_la_licorera).delete()[0]
    lotes = LoteInventario.objects.filter(
        producto__licorera__correo__endswith=dominio).delete()[0]
    entradas = EntradaMercancia.objects.filter(**de_la_licorera).delete()[0]
    productos = Producto.objects.filter(**de_la_licorera).delete()[0]
    return movimientos, lotes, entradas, productos
