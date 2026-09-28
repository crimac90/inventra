"""
Módulo SUS — Suscripciones.

Contiene las entidades que sostienen el modelo de negocio: el catálogo de
planes, la licorera (cada cliente del sistema) y el historial de suscripciones.

Corresponde a las tablas plan, licorera y suscripcion del diccionario de datos.
"""

from django.db import models
from django.db.models import Q
from django.utils import timezone


class Plan(models.Model):
    """Catálogo de planes comerciales. Define qué habilita cada uno (RF-SUS-04)."""

    nombre = models.CharField(
        max_length=30, unique=True,
        help_text="Nombre comercial del plan: Básico o Pro.",
    )
    precio_mensual = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text="Precio de lista de la suscripción mensual.",
    )
    maximo_sedes = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Límite de sedes. Vacío significa sin límite.",
    )
    maximo_usuarios = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Límite de usuarios. Vacío significa sin límite.",
    )
    permite_facturacion = models.BooleanField(
        default=False,
        help_text="Si el plan habilita la facturación electrónica.",
    )
    permite_reportes_avanzados = models.BooleanField(
        default=False,
        help_text="Si el plan habilita rotación y utilidad.",
    )
    activo = models.BooleanField(
        default=True,
        help_text="Permite retirar un plan sin borrar su historial.",
    )

    class Meta:
        db_table = "plan"
        verbose_name = "plan"
        verbose_name_plural = "planes"

    def __str__(self):
        return self.nombre


class Licorera(models.Model):
    """
    El cliente de INVENTRA. Cada licorera es un inquilino con datos aislados:
    toda tabla de negocio guarda a qué licorera pertenece (RF-SUS-01).
    """

    nombre = models.CharField(max_length=100, help_text="Nombre comercial del negocio.")
    nit = models.CharField(
        max_length=20, null=True, blank=True, unique=True,
        help_text="NIT o cédula del propietario. Único si se registra.",
    )
    direccion = models.CharField(
        max_length=150, null=True, blank=True,
        help_text="Dirección principal del negocio.",
    )
    telefono = models.CharField(
        max_length=20, null=True, blank=True,
        help_text="Teléfono de contacto.",
    )
    correo = models.EmailField(max_length=100, help_text="Correo de contacto del negocio.")
    fecha_registro = models.DateTimeField(
        auto_now_add=True,
        help_text="Cuándo se creó la cuenta en la plataforma.",
    )
    activo = models.BooleanField(
        default=True,
        help_text="Baja lógica: una licorera retirada conserva su historial.",
    )

    class Meta:
        db_table = "licorera"
        verbose_name = "licorera"
        verbose_name_plural = "licoreras"

    def __str__(self):
        return self.nombre

    def suscripcion_vigente(self):
        """
        Devuelve la suscripción que define hoy qué puede hacer el negocio.

        Vigente significa dos cosas a la vez: que su estado permite operar
        —en prueba, activa o en mora— y que no se le ha pasado la fecha.

        La condición de la fecha tiene dos formas porque hay dos casos. Una
        suscripción de plan contratado no tiene fecha de fin mientras esté vigente:
        `fecha_fin` se rellena el día que se cierra, al cambiar de plan o al darse
        de baja. Una suscripción de prueba nace con fecha de fin desde el primer
        día. Si solo se mirara «sin fecha de fin», ninguna prueba sería vigente; si
        solo se mirara la fecha, se colaría cualquier fila histórica ya cerrada.
        """
        hoy = timezone.localdate()
        return (
            self.suscripciones
            .filter(estado__in=Suscripcion.ESTADOS_OPERATIVOS)
            .filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=hoy))
            .select_related("plan")
            .order_by("-fecha_inicio")
            .first()
        )

    def plan_vigente(self):
        suscripcion = self.suscripcion_vigente()
        return suscripcion.plan if suscripcion else None

    def puede_agregar_usuario(self):
        """
        Indica si el plan contratado admite un usuario más (RF-SUS-04).

        El plan Básico permite uno solo; el Pro no tiene límite. Los usuarios
        inactivos no cuentan: quien fue dado de baja no ocupa un cupo.
        """
        plan = self.plan_vigente()
        if plan is None or plan.maximo_usuarios is None:
            return True
        return self.usuarios.filter(activo=True).count() < plan.maximo_usuarios


class Suscripcion(models.Model):
    """
    Historial de contratación de planes. Se crea una fila por período o por
    cambio de plan, de modo que el precio pactado queda congelado (RF-SUS-02 y 03).
    """

    class Estado(models.TextChoices):
        """
        Los cinco estados por los que pasa una suscripción (RF-SUS-03).

        El orden no es casual: es el ciclo de vida del cliente. Empieza en prueba,
        pasa a activa cuando contrata, cae en mora si deja de pagar, se suspende si
        la mora se prolonga, y se cancela si se va. Una prueba que vence sin contratar
        pasa directamente a suspendida: el negocio conserva sus datos y puede
        consultarlos, pero no registrar operaciones nuevas. Eso es lo que empuja a
        contratar sin castigar a quien todavía no lo ha hecho.
        """

        EN_PRUEBA = "en_prueba", "En prueba"
        ACTIVA = "activa", "Activa"
        EN_MORA = "en_mora", "En mora"
        SUSPENDIDA = "suspendida", "Suspendida"
        CANCELADA = "cancelada", "Cancelada"

    # Estados en los que la licorera puede registrar operaciones nuevas. Los demás
    # dejan consultar, pero no escribir. Lo consultarán INV, VEN y los módulos que
    # vengan, así que vive aquí y no repartido por cada vista.
    ESTADOS_OPERATIVOS = ("en_prueba", "activa", "en_mora")

    licorera = models.ForeignKey(
        Licorera, on_delete=models.PROTECT, related_name="suscripciones",
        db_column="licorera_id",
        help_text="Licorera dueña del registro; sostiene el aislamiento entre negocios.",
    )
    plan = models.ForeignKey(
        Plan, on_delete=models.PROTECT, related_name="suscripciones",
        db_column="plan_id",
        help_text="Plan contratado en este período.",
    )
    estado = models.CharField(
        max_length=12, choices=Estado.choices, default=Estado.ACTIVA,
        help_text="Estado actual de la suscripción.",
    )
    fecha_inicio = models.DateField(help_text="Inicio de la vigencia.")
    fecha_fin = models.DateField(
        null=True, blank=True,
        help_text="Fin de la vigencia. Vacío mientras esté vigente.",
    )
    precio_pactado = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text="Precio congelado al contratar; los aumentos no cambian el histórico.",
    )

    class Meta:
        db_table = "suscripcion"
        verbose_name = "suscripción"
        verbose_name_plural = "suscripciones"

    def __str__(self):
        return f"{self.licorera} — {self.plan} ({self.estado})"
