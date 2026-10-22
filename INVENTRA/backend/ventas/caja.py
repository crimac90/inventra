"""
El cierre de caja (RF-VEN-06).

Compara lo que dice el sistema con lo que hay en el cajón, para una sede y una
jornada. Tres ideas lo gobiernan:

**El día es una jornada, de las seis a las seis.** El cajón no se vacía a
medianoche, así que un corte al filo del calendario repartiría entre dos
cierres el efectivo de una sola noche.

**No hay apertura de caja ni saldo anterior.** Cada cierre se calcula con todas
las ventas de su jornada, desde la primera, y por eso se puede rehacer sin que
nada se duplique: no se crea otra fila, se actualiza la que hay.

**Solo se compara el efectivo.** La transferencia y la tarjeta no pasan por el
cajón; contarlas no diría nada, y su control está en el extracto.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from sedes.models import Sede

from .consultas import de_la_jornada, totales_por_medio
from .correo import enviar_aviso_de_diferencia
from .jornada import jornada_actual
from .models import CierreCaja, MedioPago


def resumen_de(licorera, sede, jornada):
    """Lo que el sistema dice de una jornada, antes de contar el cajón."""
    ventas = de_la_jornada(licorera, sede, jornada)
    totales = totales_por_medio(ventas)
    return {
        "jornada": jornada,
        "transacciones": ventas.count(),
        "efectivo": totales[MedioPago.EFECTIVO],
        "transferencia": totales[MedioPago.TRANSFERENCIA],
        "tarjeta": totales[MedioPago.TARJETA],
    }


@transaction.atomic
def cerrar_jornada(*, licorera, usuario, efectivo_contado, jornada=None,
                   observacion=None, sede=None):
    """
    Guarda el cierre de una jornada, o lo rehace si ya existía.

    Solo se cierra la jornada en curso. Las anteriores ya terminaron y su
    cierre, si se hizo, es la foto de cómo quedó aquella caja; si no se hizo,
    rehacerlo hoy sería contar un cajón que ya se vació y se volvió a llenar.
    """
    if sede is None:
        sede = Sede.principal_de(licorera)
    if sede is None:
        raise ValidationError("La licorera no tiene ninguna sede que cerrar.")

    en_curso = jornada_actual()
    if jornada is None:
        jornada = en_curso
    if jornada != en_curso:
        raise ValidationError(
            "Solo se cierra la jornada en curso. La del %s ya terminó."
            % jornada.strftime("%d/%m/%Y"))

    if efectivo_contado is None or efectivo_contado < 0:
        raise ValidationError("Escribe cuánto efectivo hay en la caja.")

    resumen = resumen_de(licorera, sede, jornada)
    diferencia = Decimal(efectivo_contado) - resumen["efectivo"]

    cierre, creado = CierreCaja.objects.update_or_create(
        sede=sede, fecha=jornada,
        defaults={
            "licorera": licorera,
            "total_efectivo": resumen["efectivo"],
            "total_transferencia": resumen["transferencia"],
            "total_tarjeta": resumen["tarjeta"],
            "efectivo_contado": Decimal(efectivo_contado),
            "diferencia": diferencia,
            "usuario": usuario,
            "observacion": (observacion or "").strip() or None,
        },
    )

    # El correo sale también al rehacer: si la segunda cuenta vuelve a no
    # cuadrar, es una diferencia nueva y nadie la ha visto todavía.
    enviar_aviso_de_diferencia(cierre)
    return cierre, creado


def explicar_diferencia(*, cierre, texto):
    """
    Escribe o corrige la explicación de una diferencia, también después de
    cerrada la jornada.

    Es una nota y no una cifra: no mueve ningún total ni la diferencia. Mientras
    esté vacía, la jornada sigue avisada en el panel.
    """
    if not (texto or "").strip():
        raise ValidationError("Escribe la explicación de la diferencia.")

    cierre.observacion = texto.strip()
    cierre.save(update_fields=["observacion"])
    return cierre


def jornadas_sin_explicar(licorera, limite=5):
    """
    Las jornadas que cerraron con diferencia y sin explicación, de la más
    reciente a la más antigua. Es lo que el panel mantiene a la vista hasta que
    alguien escriba el porqué.
    """
    return (
        CierreCaja.objects
        # Vacía es vacía, tanto si es nula como si es una cadena sin nada: las
        # dos puertas de escritura normalizan a nulo, pero la consulta no se
        # apoya en eso para decidir si alguien explicó algo.
        .filter(Q(observacion__isnull=True) | Q(observacion=""), licorera=licorera)
        .exclude(diferencia=0)
        .select_related("sede")
        .order_by("-fecha")[:limite]
    )
