"""
Ventas, sus líneas y el cierre de caja (módulo VEN).

Cuatro tablas, las cuatro del MER. Dos ideas las gobiernan, y conviene tenerlas
claras antes de leer los campos:

**El precio se congela en la línea; el costo no está aquí.** `detalle_venta`
guarda el precio al que se vendió, porque cambiar mañana el precio del catálogo
no puede cambiar lo que se cobró ayer. El costo no tiene columna porque una
línea puede salir de dos lotes a dos costos distintos, de modo que un solo
costo por línea no podría ser cierto. El costo real queda en el kardex, un
movimiento por tramo consumido, y la utilidad se calcula cruzando el detalle
con esos movimientos.

**Nada se borra.** Una venta equivocada se anula y conserva su número; un cierre
se rehace y conserva su fila. El consecutivo sin huecos es lo que permite
afirmar que no falta ninguna venta.
"""

from django.db import models


class MedioPago(models.Model):
    """
    Cómo pagó el cliente (RF-VEN-02).

    Es una tabla y no una lista en el código porque el MER la declara así y
    porque `venta` la referencia con una llave foránea: el histórico tiene que
    seguir diciendo «transferencia» aunque algún día se deje de aceptar.

    Se siembra con los tres del requisito y no se gestiona: ninguna pantalla los
    crea, igual que las categorías del inventario o los roles.
    """

    EFECTIVO = "efectivo"
    TRANSFERENCIA = "transferencia"
    TARJETA = "tarjeta"
    POR_DEFECTO = (EFECTIVO, TRANSFERENCIA, TARJETA)

    nombre = models.CharField(
        max_length=30, unique=True, help_text="Nombre del medio de pago.")
    activo = models.BooleanField(
        default=True,
        help_text="Permite dejar de ofrecerlo sin borrar el historial que lo usa.")

    class Meta:
        db_table = "medio_pago"
        verbose_name = "medio de pago"
        verbose_name_plural = "medios de pago"
        ordering = ["id"]

    def __str__(self):
        return self.nombre

    @property
    def es_efectivo(self):
        return self.nombre == self.EFECTIVO


class Venta(models.Model):
    """Encabezado de una venta del punto de venta (RF-VEN-01 a 05)."""

    class Estado(models.TextChoices):
        ACTIVA = "activa", "Activa"
        ANULADA = "anulada", "Anulada"

    licorera = models.ForeignKey(
        "suscripciones.Licorera", on_delete=models.PROTECT, related_name="ventas",
        db_column="licorera_id",
        help_text="Licorera dueña del registro; sostiene el aislamiento entre negocios.",
    )
    sede = models.ForeignKey(
        "sedes.Sede", on_delete=models.PROTECT, related_name="ventas",
        db_column="sede_id", help_text="Sede donde se vendió.",
    )
    usuario = models.ForeignKey(
        "seguridad.Usuario", on_delete=models.PROTECT, related_name="ventas",
        db_column="usuario_id", help_text="Quién registró la venta.",
    )
    consecutivo = models.PositiveIntegerField(
        help_text=("Número visible para el negocio, único dentro de la licorera. "
                   "Es el dato por el que un cliente nombra su compra."),
    )
    fecha = models.DateTimeField(
        auto_now_add=True,
        help_text="Fecha y hora; de ella se deriva la jornada a la que pertenece.",
    )
    total = models.DecimalField(
        max_digits=12, decimal_places=2, help_text="Suma de los subtotales del detalle.",
    )
    medio_pago = models.ForeignKey(
        MedioPago, on_delete=models.PROTECT, related_name="ventas",
        db_column="medio_pago_id", help_text="Cómo pagó el cliente.",
    )
    monto_recibido = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text=("Efectivo entregado por el cliente, para calcular el cambio. "
                   "Vacío en los demás medios, donde no hay cambio que devolver."),
    )
    estado = models.CharField(
        max_length=10, choices=Estado.choices, default=Estado.ACTIVA,
        help_text="Las ventas no se borran: se anulan (RF-VEN-04).",
    )
    observacion = models.CharField(
        max_length=60, null=True, blank=True,
        help_text=("Nota corta para reconocer la venta: «mesa 1, pedido 3». "
                   "El negocio también sirve mesas, y quien cobra necesita "
                   "poder identificar después una venta que no se llevó el "
                   "cliente en la mano."),
    )
    motivo_anulacion = models.CharField(
        max_length=255, null=True, blank=True,
        help_text="Por qué se anuló; obligatorio al anular.",
    )
    anulada_por = models.ForeignKey(
        "seguridad.Usuario", on_delete=models.PROTECT, related_name="ventas_anuladas",
        db_column="anulada_por", null=True, blank=True,
        help_text=("Quién la anuló. No es quien la registró: anular es del "
                   "administrador y cobrar es del vendedor."),
    )
    fecha_anulacion = models.DateTimeField(
        null=True, blank=True,
        help_text=("Cuándo se anuló. No se deriva de la fecha de la venta: "
                   "entre una y otra pueden pasar horas dentro de la misma "
                   "jornada, y es el dato que ordena los hechos."),
    )

    class Meta:
        db_table = "venta"
        verbose_name = "venta"
        verbose_name_plural = "ventas"
        ordering = ["-fecha", "-id"]
        constraints = [
            # El número que ve el negocio es único DENTRO de la licorera, no en
            # todo el sistema: dos licoreras tienen cada una su venta número 1.
            models.UniqueConstraint(
                fields=["licorera", "consecutivo"], name="consecutivo_unico_por_licorera",
            ),
        ]

    def __str__(self):
        return "Venta #%d" % self.consecutivo

    @property
    def cambio(self):
        """Lo que se devolvió, o nada si no se pagó en efectivo."""
        if self.monto_recibido is None:
            return None
        return self.monto_recibido - self.total


class DetalleVenta(models.Model):
    """
    Una línea de la venta, con el precio congelado (RF-VEN-01).

    El precio se copia y no se referencia: cambiar mañana el precio del catálogo
    no puede cambiar lo que se cobró ayer, que es la otra mitad de RF-INV-03.
    """

    venta = models.ForeignKey(
        Venta, on_delete=models.PROTECT, related_name="lineas",
        db_column="venta_id", help_text="Venta a la que pertenece la línea.",
    )
    producto = models.ForeignKey(
        "inventario.Producto", on_delete=models.PROTECT, related_name="lineas_vendidas",
        db_column="producto_id", help_text="Referencia vendida.",
    )
    cantidad = models.PositiveIntegerField(help_text="Unidades vendidas.")
    precio_unitario = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text="Precio de venta congelado en el momento de vender.",
    )
    subtotal = models.DecimalField(
        max_digits=12, decimal_places=2, help_text="Cantidad por precio unitario.",
    )

    class Meta:
        db_table = "detalle_venta"
        verbose_name = "línea de venta"
        verbose_name_plural = "líneas de venta"
        ordering = ["id"]

    def __str__(self):
        return "%d × %s" % (self.cantidad, self.producto)


class CierreCaja(models.Model):
    """
    El cierre de una jornada en una sede (RF-VEN-06).

    `fecha` es la **jornada**, no el día del calendario: empieza a las seis de
    la mañana y termina a las seis de la mañana siguiente, de modo que lo
    vendido de madrugada se cierra con la noche en la que se vendió. El MER no
    cambia por esto: la columna sigue siendo una fecha y lo único distinto es
    qué ventas caen dentro.

    No hay apertura de caja ni saldo que venga del cierre anterior. Cada cierre
    se calcula con todas las ventas de su jornada, desde la primera, y por eso
    se puede rehacer mientras la jornada siga abierta sin que nada se duplique.
    """

    licorera = models.ForeignKey(
        "suscripciones.Licorera", on_delete=models.PROTECT, related_name="cierres",
        db_column="licorera_id",
        help_text="Licorera dueña del registro; sostiene el aislamiento entre negocios.",
    )
    sede = models.ForeignKey(
        "sedes.Sede", on_delete=models.PROTECT, related_name="cierres",
        db_column="sede_id", help_text="Sede del cierre.",
    )
    fecha = models.DateField(help_text="Jornada cerrada (de las 06:00 a las 06:00).")
    total_efectivo = models.DecimalField(
        max_digits=12, decimal_places=2, help_text="Ventas en efectivo según el sistema.",
    )
    total_transferencia = models.DecimalField(
        max_digits=12, decimal_places=2, help_text="Ventas por transferencia según el sistema.",
    )
    total_tarjeta = models.DecimalField(
        max_digits=12, decimal_places=2, help_text="Ventas con tarjeta según el sistema.",
    )
    efectivo_contado = models.DecimalField(
        max_digits=12, decimal_places=2, help_text="Efectivo físico contado por el usuario.",
    )
    diferencia = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text=("Contado menos lo que dice el sistema: negativo si falta dinero, "
                   "positivo si sobra. Se guarda calculado para que el cierre se lea "
                   "tal como quedó ese día."),
    )
    usuario = models.ForeignKey(
        "seguridad.Usuario", on_delete=models.PROTECT, related_name="cierres",
        db_column="usuario_id", help_text="Quién hizo el cierre.",
    )
    observacion = models.CharField(
        max_length=255, null=True, blank=True,
        help_text=("Explicación de la diferencia. Mientras esté vacía, la jornada "
                   "aparece avisada en el panel; se puede escribir después."),
    )

    class Meta:
        db_table = "cierre_caja"
        verbose_name = "cierre de caja"
        verbose_name_plural = "cierres de caja"
        ordering = ["-fecha"]
        constraints = [
            models.UniqueConstraint(
                fields=["sede", "fecha"], name="un_cierre_por_sede_y_jornada",
            ),
        ]

    def __str__(self):
        return "Cierre %s — %s" % (self.fecha, self.sede)

    @property
    def total_vendido(self):
        return self.total_efectivo + self.total_transferencia + self.total_tarjeta

    @property
    def hay_que_explicar(self):
        """Una diferencia sin explicación es la que el panel mantiene a la vista."""
        return self.diferencia != 0 and not (self.observacion or "").strip()
