# -*- coding: utf-8 -*-
"""
El precio que el sistema PROPONE, y que nunca aplica (RF-INV-11).

El requisito está escrito en negativo —«sugerir precio por margen, nunca
automático»—, y esa es la regla que manda: un sistema que reprecia solo al
subir un costo rompe sin avisar una promoción, un precio acordado con el
proveedor o un artículo que se vende casi a costo para atraer clientes.

Se propone sobre el **promedio ponderado de las existencias**: lo que costó todo lo que
hay en bodega, dividido entre las unidades que hay. No sobre la última compra.

La diferencia no es teórica. Con 100 unidades compradas a 60.000 y 20 de
promoción a 20.000, la última compra dice 20.000 y el promedio dice 53.333;
proponer sobre la última llevaría a vender por debajo de costo las 100 caras
sin que nada lo advirtiera. El promedio es además la única base con la que un
precio único deja el margen pedido sobre el lote completo.

Sin existencias no hay promedio, y entonces se usa el costo de la última
compra: es lo único que se sabe, y conviene decirlo en la pantalla.

Un promedio reparte, y por eso se publica también el rango: con lotes muy distintos, el precio que deja un 30 % sobre
el conjunto puede quedar por debajo del costo de algunas unidades. Eso es
legítimo —el margen se cumple si se vende todo— pero no puede ser invisible,
así que se devuelven también el costo mínimo y el máximo y el detalle de los
lotes vivos, y la pantalla avisa cuando el precio no cubre al más caro.

EL REDONDEO sube a la centena siguiente, nunca baja: un precio de 47.353 no se
cobra en ninguna parte, y redondear hacia abajo recortaría el margen pedido.
"""

from decimal import Decimal, ROUND_CEILING

from django.db.models import F, Max, Min, Q, Sum, Value
from django.db.models.functions import Coalesce

from .models import LoteInventario

CENTENA = Decimal("100")


def lotes_vivos(producto):
    """Los lotes que todavía tienen unidades, del más antiguo al más nuevo."""
    return (
        LoteInventario.objects
        .filter(producto=producto, cantidad_disponible__gt=0)
        .order_by("fecha_ingreso", "id")
    )


def costo_de_la_ultima_compra(producto):
    """El costo del lote más reciente de la referencia, o `None` si nunca entró."""
    lote = (
        LoteInventario.objects
        .filter(producto=producto)
        .order_by("-fecha_ingreso", "-id")
        .first()
    )
    return lote.costo_unitario if lote else None


def con_costos(consulta):
    """
    Añade a cada producto lo que costaron sus existencias, sin salir de la
    consulta: el valor total de lo que hay, y el costo del lote más barato y
    del más caro entre los que aún tienen unidades.

    Va aquí y no fila a fila por la misma razón que las existencias: la lista
    del catálogo trae veinticinco referencias, y preguntarlo una por una serían
    veinticinco viajes más a la base.
    """
    disponible = Q(lotes__cantidad_disponible__gt=0)
    return consulta.annotate(
        valor_existencias=Coalesce(
            Sum(F("lotes__cantidad_disponible") * F("lotes__costo_unitario")),
            Value(Decimal("0"))),
        costo_minimo=Min("lotes__costo_unitario", filter=disponible),
        costo_maximo=Max("lotes__costo_unitario", filter=disponible),
    )


def costo_promedio(producto, unidades=None, valor=None):
    """
    Lo que costó, en promedio, cada unidad de las que hay en existencia.

    Acepta el total y el valor ya calculados —la lista los trae anotados— y los
    pregunta a la base solo cuando no vienen, que es el caso de un producto
    suelto recién guardado.

    Devuelve `None` sin existencias: no hay nada cuyo costo promediar.
    """
    if unidades is None or valor is None:
        resumen = (
            LoteInventario.objects
            .filter(producto=producto)
            .aggregate(
                unidades=Coalesce(Sum("cantidad_disponible"), Value(0)),
                valor=Coalesce(
                    Sum(F("cantidad_disponible") * F("costo_unitario")),
                    Value(Decimal("0"))),
            )
        )
        unidades, valor = resumen["unidades"], resumen["valor"]

    if not unidades:
        return None
    return Decimal(valor) / Decimal(unidades)


def sugerir_precio(costo, margen):
    """
    El precio que se propone para un costo y un margen, redondeado a la centena.

    Devuelve `None` cuando no hay costo: una referencia que nunca ha entrado no
    tiene de dónde sacar una propuesta, y proponer sobre cero daría cero.
    """
    if costo is None:
        return None
    bruto = Decimal(costo) * (Decimal("1") + Decimal(margen) / Decimal("100"))
    return (bruto / CENTENA).quantize(Decimal("1"), rounding=ROUND_CEILING) * CENTENA
