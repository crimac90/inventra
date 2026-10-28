# -*- coding: utf-8 -*-
"""
Qué referencias llevan un tiempo sin venderse (RF-INV-08).

Es un requisito del inventario y la respuesta la tiene este módulo: «sin
rotación» significa «sin ventas», y las ventas viven aquí. Por eso la consulta
se escribe en VEN y el catálogo la usa, en vez de que el catálogo arme un
filtro sobre una tabla que no es suya.

EL PERÍODO NO SE GUARDA EN NINGUNA PARTE. El requisito lo pide configurable, y
quien mira lo elige al consultar: treinta, sesenta o noventa días. Una columna
para guardarlo sería la tercera fuera del modelo entregado, y lo que resolvería
—dejar fijado «en mi negocio son cuarenta y cinco»— no lo pide nadie todavía.
Lo que sí hace falta es un valor por omisión, porque el panel enseña la cifra
sin preguntar.

UN PLAZO MAYOR SIEMPRE DEVUELVE MENOS O LO MISMO QUE UNO MENOR, nunca más. Lo que
se pregunta es «no se ha vendido en los últimos N días», de modo que lo que lleva
noventa días quieto lleva también sesenta y treinta: las tres listas se contienen
unas a otras. Que los tres plazos devuelvan exactamente las mismas referencias no
es un defecto del filtro; significa que ninguna referencia tiene su última venta
entre los treinta y los noventa días, y las que salen no es que lleven cuarenta
días paradas, es que no se han vendido nunca.

LAS ANULADAS NO CUENTAN COMO VENTA. Una referencia que solo aparece en una
venta deshecha no se ha vendido, y decir lo contrario escondería justo la
referencia estancada que se quiere encontrar.
"""

from datetime import timedelta

from django.utils import timezone

from .models import DetalleVenta, Venta

# Días sin venderse a partir de los cuales una referencia se considera
# estancada, cuando nadie elige otro plazo.
DIAS_POR_OMISION = 60

# Los plazos que ofrece la interfaz. Se escriben aquí y no en la pantalla
# porque el catálogo y el panel tienen que ofrecer los mismos.
PLAZOS = (30, 60, 90)


def dias_validos(valor):
    """
    El plazo pedido, o el de siempre si no viene o no vale.

    Un plazo imposible no es motivo para rechazar la consulta: el catálogo se
    abre igual y enseña la pregunta que sí sabe contestar.
    """
    try:
        dias = int(valor)
    except (TypeError, ValueError):
        return DIAS_POR_OMISION
    return dias if dias in PLAZOS else DIAS_POR_OMISION


def vendidos_desde(licorera, dias):
    """Los identificadores de producto con al menos una venta en el plazo."""
    desde = timezone.now() - timedelta(days=dias)
    return (
        DetalleVenta.objects
        .filter(venta__licorera=licorera,
                venta__estado=Venta.Estado.ACTIVA,
                venta__fecha__gte=desde)
        .values("producto_id")
    )


def sin_rotacion(productos, licorera, dias):
    """
    Las referencias del catálogo que no se han vendido en el plazo.

    Recibe la consulta de productos ya filtrada por quien la llama, de modo que
    se combina con el estado y con el nivel de existencias sin saber nada de
    ellos.
    """
    return productos.exclude(id__in=vendidos_desde(licorera, dias))
