"""
Pone al día el estado guardado de las suscripciones (RF-SUS-03, decisión D-25).

QUÉ HACE Y QUÉ NO
El estado que manda se calcula en el momento, con `Suscripcion.estado_por_fecha()`.
Esta orden no decide nada: copia ese cálculo a la columna `estado`, para que el
panel de plataforma y cualquier consulta directa a la base vean lo mismo que ve
la aplicación. Si un día no corre, el sistema se comporta igual de bien; solo
queda desactualizado lo que está escrito.

Tres cosas que NO hace, y cada una evita un problema concreto:

  - No toca `fecha_fin`. Esa columna solo la escribe una persona, y el correo al
    administrador de la licorera cuelga de esa acción. Como esta orden no pasa
    por ahí, no puede mandar un correo cada día aunque el estado cambie.
  - No retrocede. Solo avanza en el ciclo —activa, en mora, suspendida—, de modo
    que no puede devolver a la vida una fila vencida. Renovar abre una fila
    nueva; revivir la vieja sería otra cosa y no es tarea suya.
  - No mira las canceladas. Son la baja definitiva y ninguna fecha las revierte.

USO
    python manage.py actualizar_estados_suscripciones
    python manage.py actualizar_estados_suscripciones --simular
    python manage.py actualizar_estados_suscripciones --fecha 2026-12-31

`--fecha` existe para poder demostrar el vencimiento en la sustentación sin
esperar quince días ni cambiar el reloj del equipo.
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from suscripciones.models import Suscripcion

# Posición de cada estado en el ciclo de vida. La orden solo escribe cuando el
# estado calculado va por delante del guardado.
AVANCE = {
    Suscripcion.Estado.EN_PRUEBA: 0,
    Suscripcion.Estado.ACTIVA: 0,
    Suscripcion.Estado.EN_MORA: 1,
    Suscripcion.Estado.SUSPENDIDA: 2,
}


class Command(BaseCommand):
    help = "Actualiza el estado de las suscripciones según su fecha de fin."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fecha",
            help="Fecha desde la que calcular, en formato AAAA-MM-DD. Por omisión, hoy.",
        )
        parser.add_argument(
            "--simular",
            action="store_true",
            help="Dice qué cambiaría, sin escribir nada.",
        )

    def handle(self, *args, **opciones):
        hoy = self._fecha(opciones.get("fecha"))
        simular = opciones["simular"]

        cambiadas = 0
        for suscripcion in (Suscripcion.objects
                            .exclude(estado=Suscripcion.Estado.CANCELADA)
                            .select_related("licorera")):
            nuevo = suscripcion.estado_por_fecha(hoy)
            if AVANCE[nuevo] <= AVANCE[suscripcion.estado]:
                continue
            self.stdout.write(
                "%s: %s -> %s" % (suscripcion.licorera.nombre,
                                  suscripcion.estado, nuevo))
            if not simular:
                suscripcion.estado = nuevo
                suscripcion.save(update_fields=["estado"])
            cambiadas += 1

        if not cambiadas:
            self.stdout.write(self.style.SUCCESS("Ningún estado que actualizar."))
            return
        resumen = "%d suscripción(es) %s." % (
            cambiadas, "cambiarían" if simular else "actualizadas")
        self.stdout.write(self.style.SUCCESS(resumen))

    def _fecha(self, texto):
        if not texto:
            return timezone.localdate()
        try:
            return date.fromisoformat(texto)
        except ValueError:
            raise CommandError("La fecha debe ir en formato AAAA-MM-DD.")
