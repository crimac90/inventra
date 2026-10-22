"""
Las consultas de ventas: por jornada y por los filtros del historial.

Viven aparte de las operaciones porque leer no es escribir, y sobre todo porque
las dos pantallas que consultan —el historial y el cierre de caja— y el
indicador del panel tienen que entender «día» de la misma manera. Si cada una
armara su propio filtro, a la una de la madrugada el panel diría una cifra y el
cierre otra, las dos correctas y distintas.

Las ventas anuladas no se suman en ninguna parte. Siguen apareciendo en el
historial, marcadas, porque una venta que desaparece deja un hueco que nadie
puede explicar; pero no cuentan como dinero, que es lo que el cierre compara
con el cajón.
"""

from decimal import Decimal

from django.db.models import Count, Q, Sum

from .jornada import limites_de
from .models import MedioPago, Venta


def activas(licorera):
    """Las ventas que cuentan como dinero: las que no se anularon."""
    return Venta.objects.filter(licorera=licorera, estado=Venta.Estado.ACTIVA)


def de_la_jornada(licorera, sede, jornada):
    """Las ventas activas de una sede en una jornada (de las 06:00 a las 06:00)."""
    inicio, fin = limites_de(jornada)
    return activas(licorera).filter(sede=sede, fecha__gte=inicio, fecha__lt=fin)


def totales_por_medio(ventas):
    """
    Lo vendido con cada medio de pago, y cuántas transacciones hubo.

    Devuelve los tres medios siempre, también los que no se usaron: un cierre
    que escondiera la fila de «tarjeta» porque hoy nadie pagó con tarjeta
    obligaría a mirar dos veces para saber si es cero o si falta.
    """
    sumas = {
        fila["medio_pago__nombre"]: fila["total"]
        for fila in ventas.values("medio_pago__nombre").annotate(total=Sum("total"))
    }
    return {nombre: sumas.get(nombre) or Decimal("0")
            for nombre in MedioPago.POR_DEFECTO}


def filtrar(licorera, *, desde=None, hasta=None, vendedor=None, producto=None,
            medio_pago=None, buscar=None):
    """
    El historial de ventas con los filtros de RF-VEN-05.

    Aquí sí entran las anuladas: el historial es el registro de lo que pasó, y
    lo que pasó incluye lo que se deshizo. Las fechas se reciben como jornadas
    y se traducen a momentos, para que una venta de la una de la madrugada
    salga buscando la noche en la que se vendió y no el día siguiente.
    """
    consulta = (
        Venta.objects
        .filter(licorera=licorera)
        .select_related("usuario", "medio_pago")
    )

    if desde is not None:
        consulta = consulta.filter(fecha__gte=limites_de(desde)[0])
    if hasta is not None:
        consulta = consulta.filter(fecha__lt=limites_de(hasta)[1])
    if vendedor is not None:
        consulta = consulta.filter(usuario=vendedor)
    if producto is not None:
        consulta = consulta.filter(lineas__producto=producto).distinct()
    if medio_pago is not None:
        consulta = consulta.filter(medio_pago=medio_pago)
    if buscar:
        texto = buscar.strip()
        if texto.isdigit():
            consulta = consulta.filter(consecutivo=int(texto))
        else:
            # Por nombre de producto o por la nota de la venta. La nota existe
            # para reconocer después una venta de mesa, y una nota que no se
            # puede buscar no sirve para reconocer nada.
            consulta = consulta.filter(
                Q(lineas__producto__nombre__icontains=texto)
                | Q(observacion__icontains=texto)).distinct()

    return consulta


def resumen(consulta):
    """
    Lo que los tres indicadores del historial dicen sobre el período.

    Se calcula sobre la misma consulta que llena la tabla, y no sobre la
    página que se está enseñando: con veinticinco filas a la vista, un total
    sacado de ellas hablaría de veinticinco ventas mientras el encabezado
    anuncia el mes entero.

    Lo anulado se cuenta aparte en vez de restarse del total. Son dos hechos
    distintos —lo que se vendió y lo que hubo que deshacer—, y mezclarlos
    escondería justo el que conviene mirar.
    """
    activas = consulta.filter(estado=Venta.Estado.ACTIVA).aggregate(
        total=Sum("total"), cuantas=Count("id"))
    anuladas = consulta.filter(estado=Venta.Estado.ANULADA).aggregate(
        total=Sum("total"), cuantas=Count("id"))

    vendido = activas["total"] or Decimal("0")
    transacciones = activas["cuantas"] or 0

    return {
        "vendido": vendido,
        "transacciones": transacciones,
        "promedio": (vendido / transacciones) if transacciones else Decimal("0"),
        "anuladas": anuladas["cuantas"] or 0,
        "valor_anulado": anuladas["total"] or Decimal("0"),
    }
