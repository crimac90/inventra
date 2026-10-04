"""
Módulo SUS — Suscripciones.

Contiene las entidades que sostienen el modelo de negocio: el catálogo de
planes, la licorera (cada cliente del sistema) y el historial de suscripciones.

Corresponde a las tablas plan, licorera y suscripcion del diccionario de datos.
"""

from django.db import models
from django.utils import timezone


class Plan(models.Model):
    """Catálogo de planes comerciales. Define qué habilita cada uno (RF-SUS-04)."""

    class Caracteristica(models.TextChoices):
        """
        Lo que un plan habilita o no habilita (RF-SUS-04).

        Las cuatro ya existían repartidas en columnas sueltas —dos banderas y dos
        topes numéricos—, y cada sitio que quería preguntar «¿este plan incluye
        multisede?» tenía que saber que eso se mira en `maximo_sedes` y que el
        valor que lo niega es el uno. Nombrarlas permite preguntarlo sin saber
        dónde está escrito, que es lo que necesitan el menú lateral y los módulos
        que vendrán.
        """

        MULTIUSUARIO = "multiusuario", "Más de un usuario"
        MULTISEDE = "multisede", "Más de una sede"
        REPORTES_AVANZADOS = "reportes_avanzados", "Reportes avanzados"
        FACTURACION = "facturacion", "Facturación electrónica"

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

    def incluye(self, caracteristica):
        """
        Si este plan habilita la característica indicada (RF-SUS-04).

        Los topes se leen como «¿deja pasar de uno?» y no como «¿cuántos?»,
        porque la pregunta aquí es de sí o no. Cuántos caben exactamente lo
        siguen respondiendo `maximo_usuarios` y `maximo_sedes`, que es otra
        pregunta: un plan intermedio de cinco usuarios incluiría multiusuario y
        tendría tope igualmente.
        """
        Caracteristica = self.Caracteristica
        if caracteristica == Caracteristica.FACTURACION:
            return self.permite_facturacion
        if caracteristica == Caracteristica.REPORTES_AVANZADOS:
            return self.permite_reportes_avanzados
        if caracteristica == Caracteristica.MULTIUSUARIO:
            return self.maximo_usuarios != 1
        if caracteristica == Caracteristica.MULTISEDE:
            return self.maximo_sedes != 1
        # Un nombre que no existe no puede devolver «no incluida» en silencio:
        # sería una restricción invisible que nadie encuentra.
        raise ValueError("Característica desconocida: %r" % (caracteristica,))


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

    def suscripcion_actual(self):
        """
        La última suscripción de la licorera, deje operar hoy o no.

        Son dos preguntas distintas y antes estaban mezcladas en una sola
        consulta: «cuál es la suscripción de este negocio» y «puede registrar
        operaciones». Mientras una suscripción vencida y una suspendida eran lo
        mismo, mezclarlas no molestaba. Con los días de gracia sí: una cuenta en
        mora tiene la fecha pasada y **debe seguir operando** (D-25), de modo que
        la fecha ya no puede decidir por sí sola. Aquí se responde la primera
        pregunta; la segunda la responde `esta_vigente()` sobre la fila devuelta.

        Se excluyen las canceladas porque son la baja definitiva: esa licorera no
        tiene suscripción, no tiene una que no vale.

        El desempate por identificador no es un adorno: al contratar el mismo día
        en que termina la prueba, las dos filas empiezan hoy, y sin él la consulta
        podría devolver la que se acaba de cerrar.
        """
        return (
            self.suscripciones
            .exclude(estado=Suscripcion.Estado.CANCELADA)
            .select_related("plan")
            .order_by("-fecha_inicio", "-id")
            .first()
        )

    def suscripcion_vigente(self):
        """
        La suscripción que hoy permite registrar operaciones, o None si ninguna.

        Es la actual, si deja operar. Toda la regla de fechas y estados vive en
        `Suscripcion.estado_por_fecha()`, escrita una sola vez, y no repartida
        entre esta consulta y el modelo.
        """
        actual = self.suscripcion_actual()
        return actual if actual is not None and actual.esta_vigente() else None

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

    # Duración de la prueba gratuita (RF-SUS-01). Vive aquí, y no en la vista que
    # registra, porque también la van a necesitar el panel de plataforma y la
    # orden que vence suscripciones: si estuviera escrita en cada sitio, cambiarla
    # sería buscarla.
    DIAS_DE_PRUEBA = 15

    # Los dos plazos que rodean al vencimiento (D-25). Son dos constantes y no
    # una, aunque hoy tuvieran el mismo valor, porque significan cosas opuestas:
    # una cuenta los días de antes y la otra los de después. Se eligieron
    # distintos a proposito, para que al leer el código no se confundan y para
    # que mover una no arrastre a la otra.
    DIAS_DE_AVISO = 3     # antes de la fecha de fin: el panel avisa, se opera normal
    DIAS_DE_GRACIA = 4    # después: la cuenta sigue operando en mora; al quinto, suspendida

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
        help_text=(
            "Hasta cuándo vale esta suscripción. La define el Administrador "
            "INVENTRA al activar y al renovar, y no puede ser una fecha pasada "
            "(RF-SUS-03); al cambiar de plan se acorta al día del cambio."
        ),
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

    # ------------------------------------------------------------------
    # Vigencia (RF-SUS-01 y RF-SUS-03)
    # ------------------------------------------------------------------

    def estado_por_fecha(self, hoy=None):
        """
        El estado que le corresponde hoy a esta suscripción según su fecha de fin.

        ESTE MÉTODO ES LA FUENTE DE VERDAD; la columna `estado` es una copia que
        la orden `actualizar_estados_suscripciones` mantiene al día (D-25). Se
        hizo así y no al revés porque una copia puede quedarse atrás —basta que
        la orden no corriera anoche— y entonces el sistema dejaría operar a quien
        ya venció. Lo que se calcula en el momento no se olvida de correr.

        Escalones, contando desde la fecha de fin:
            hasta ese día        conserva su estado (en prueba o activa)
            de 1 a DIAS_DE_GRACIA    en mora: sigue operando, con aviso de pago
            a partir de ahí          suspendida: consulta, no registra
        """
        # La cancelada es la baja definitiva. Ninguna fecha la revive: si este
        # método pudiera devolver otra cosa, la orden diaria resucitaría cuentas
        # que alguien dio de baja a conciencia.
        if self.estado == self.Estado.CANCELADA:
            return self.Estado.CANCELADA

        # Sin fecha de fin no hay nada que vencer. Desde D-25 la aplicación no
        # crea filas así, pero la columna admite nulo y las filas antiguas lo
        # son: se conserva la rama en vez de suponer que no existen.
        if self.fecha_fin is None:
            return self.estado

        hoy = hoy or timezone.localdate()
        vencida_hace = (hoy - self.fecha_fin).days
        if vencida_hace <= 0:
            return self.estado

        # La prueba no tiene días de gracia: lo dice RF-SUS-03 y tiene sentido,
        # porque quien no ha pagado nunca no está en mora de nada.
        if self.es_periodo_gratuito:
            return self.Estado.SUSPENDIDA

        if vencida_hace <= self.DIAS_DE_GRACIA:
            return self.Estado.EN_MORA
        return self.Estado.SUSPENDIDA

    def esta_vigente(self, hoy=None):
        """Si esta suscripción permite hoy registrar operaciones nuevas."""
        return self.estado_por_fecha(hoy) in self.ESTADOS_OPERATIVOS

    def dias_para_suspension(self, hoy=None):
        """
        Días que le quedan a una cuenta en mora antes de quedar suspendida, o
        None si no está en mora. El día en curso cuenta, igual que en
        `dias_restantes()`: mientras se pueda trabajar, el día no ha pasado.
        """
        hoy = hoy or timezone.localdate()
        if self.estado_por_fecha(hoy) != self.Estado.EN_MORA:
            return None
        return self.DIAS_DE_GRACIA + 1 - (hoy - self.fecha_fin).days

    def dias_restantes(self, hoy=None):
        """
        Días que faltan para que termine la vigencia, o None si no vence.

        El último día cuenta: una prueba que termina hoy tiene cero días
        restantes y todavía deja trabajar, igual que un plazo que vence a las
        doce de la noche. Devolver cero y seguir operando no es una excepción,
        es lo que significa «vence hoy».
        """
        if self.fecha_fin is None:
            return None
        hoy = hoy or timezone.localdate()
        return max(0, (self.fecha_fin - hoy).days)

    def avisa_vencimiento(self, hoy=None):
        """
        Si toca avisar de que la fecha de fin se acerca.

        Vive en el modelo y no en el serializador porque es una pregunta sobre
        la suscripción, no sobre cómo se dibuja. Estuvo escrito a mano en el
        componente del aviso —un tres repetido en dos lenguajes, que algún día
        valdría dos en uno de ellos—, pasó al serializador en el bloque 3 y baja
        aquí al aparecer el segundo interesado: cualquiera que necesite saberlo
        pregunta en el mismo sitio (regla 14).
        """
        dias = self.dias_restantes(hoy)
        return dias is not None and dias <= self.DIAS_DE_AVISO

    @property
    def es_prueba(self):
        """Si esta suscripción está ahora mismo en período de prueba."""
        return self.estado == self.Estado.EN_PRUEBA

    @property
    def es_periodo_gratuito(self):
        """
        Si esta fila corresponde a un período por el que no se cobra.

        No basta con mirar el estado, aunque «en prueba» lo diría: el estado
        cambia el día que la prueba vence, y a partir de ahí ya no se podría
        reconocer que lo fue —que es justo cuando hace falta saberlo, para no
        darle días de gracia—. El precio pactado, en cambio, se congela al abrir
        la fila y no se mueve nunca (D-22, que fija la prueba en cero): es el
        único dato que sigue diciendo qué fue esta suscripción después de dejar
        de serlo.
        """
        return self.estado == self.Estado.EN_PRUEBA or self.precio_pactado == 0
