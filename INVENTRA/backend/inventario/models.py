"""
Catálogo de productos de una licorera (módulo INV).

QUÉ NO ESTÁ AQUÍ, Y POR QUÉ
Dos columnas que cualquiera esperaría en un producto y que el MER deja fuera a
propósito:

- **El costo.** Lo dice RF-INV-01 con todas sus letras: «el costo no se registra
  en la referencia: entra con cada lote de mercancía, porque la valoración PEPS
  exige el costo real de cada entrada y no un costo único por producto». Un
  costo por producto obligaría a elegir cuál —¿el de la última compra?— y
  falsearía la utilidad de todo lo vendido antes de esa compra.
- **Las existencias.** «Las existencias NO se guardan aquí: se deriva de los
  lotes (una sola fuente de verdad)». Es la misma forma del estado de la
  suscripción en SUS, donde el cálculo manda; aquí ni siquiera hay copia que
  mantener al día.

El precio de venta sí vive en el producto, y vive **separado del costo**
(RF-INV-11): el sistema puede sugerirlo a partir de un margen, pero nunca lo
cambia solo.
"""

from django.db import models


class Categoria(models.Model):
    """
    Categorías del catálogo, propias de cada licorera.

    Se siembran al registrar el negocio con los seis valores que enumera
    RF-INV-01 y no se gestionan desde ninguna pantalla: ningún requisito permite
    crearlas ni editarlas, y ninguna función existe sin requisito que la pida.
    """

    # Las seis de RF-INV-01, en el orden en que las enumera el requisito.
    POR_DEFECTO = ("Aguardiente", "Ron", "Cerveza", "Whisky", "Vino", "Otros")

    licorera = models.ForeignKey(
        "suscripciones.Licorera", on_delete=models.PROTECT, related_name="categorias",
        db_column="licorera_id",
        help_text="Licorera dueña del registro; sostiene el aislamiento entre negocios.",
    )
    nombre = models.CharField(max_length=50, help_text="Nombre de la categoría.")
    activo = models.BooleanField(default=True, help_text="Baja lógica.")

    class Meta:
        db_table = "categoria"
        verbose_name = "categoría"
        verbose_name_plural = "categorías"
        constraints = [
            models.UniqueConstraint(
                fields=["licorera", "nombre"], name="categoria_unica_por_licorera",
            ),
        ]

    def __str__(self):
        return self.nombre

    @classmethod
    def sembrar(cls, licorera):
        """
        Crea las categorías con las que nace una licorera.

        Repetible a propósito: la llaman las dos puertas del registro y la orden
        de datos de demostración, que se puede ejecutar dos veces.
        """
        return [
            cls.objects.get_or_create(licorera=licorera, nombre=nombre)[0]
            for nombre in cls.POR_DEFECTO
        ]


class Producto(models.Model):
    """Referencia del catálogo de una licorera (RF-INV-01 a 04)."""

    class Presentacion(models.TextChoices):
        """
        Las cinco del MER. Es una lista cerrada y no texto libre porque de ello
        depende poder agrupar y filtrar el catálogo: con texto libre, «Botella»,
        «botella» y «Botella 750» serían tres presentaciones distintas.
        """

        MEDIA = "media", "Media"
        BOTELLA = "botella", "Botella"
        LITRO = "litro", "Litro"
        GARRAFA = "garrafa", "Garrafa"
        UNIDAD = "unidad", "Unidad"

    licorera = models.ForeignKey(
        "suscripciones.Licorera", on_delete=models.PROTECT, related_name="productos",
        db_column="licorera_id",
        help_text="Licorera dueña del registro; sostiene el aislamiento entre negocios.",
    )
    categoria = models.ForeignKey(
        Categoria, on_delete=models.PROTECT, related_name="productos",
        db_column="categoria_id", help_text="Categoría del producto.",
    )
    nombre = models.CharField(
        max_length=120,
        help_text="Nombre de la referencia («Aguardiente Antioqueño 750 ml»).",
    )
    presentacion = models.CharField(
        max_length=10, choices=Presentacion.choices,
        help_text="Presentación comercial de la referencia.",
    )
    codigo_barras = models.CharField(
        max_length=50, null=True, blank=True,
        help_text="Código de barras; único dentro de la licorera si se registra.",
    )
    precio_venta = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text=(
            "Precio de venta vigente. Vive separado del costo (RF-INV-11) y solo "
            "lo cambia el administrador; las ventas ya hechas conservan el suyo."
        ),
    )
    stock_minimo = models.PositiveIntegerField(
        default=0, help_text="Umbral de la alerta de existencias bajas (RF-INV-07).",
    )
    activo = models.BooleanField(
        default=True,
        help_text="Baja lógica (RF-INV-04): no aparece en el punto de venta, conserva historial.",
    )
    fecha_creacion = models.DateTimeField(
        auto_now_add=True, help_text="Cuándo se creó la referencia.",
    )

    class Meta:
        db_table = "producto"
        verbose_name = "producto"
        verbose_name_plural = "productos"
        ordering = ["nombre"]
        constraints = [
            # Único DENTRO de la licorera: dos negocios distintos venden el
            # mismo aguardiente y comparten su código de barras, así que un
            # único global dejaría al segundo sin poder registrarlo.
            #
            # SIN CONDICIÓN, Y ESO IMPORTA. La primera versión llevaba
            # `condition=Q(codigo_barras__isnull=False)` para excluir los
            # productos sin código. Al migrar, Django avisó (W036) de que MySQL
            # no admite restricciones únicas con condición y de que, por tanto,
            # **no iba a crearla**: habría quedado una protección que parece
            # estar y no está, con la validación viviendo solo en el servidor
            # de la aplicación. La condición además sobraba: en SQL dos nulos no
            # son iguales entre sí, de modo que un índice único normal ya
            # permite tantos productos sin código como haga falta. Al quitarla,
            # la restricción se crea de verdad y los nulos siguen conviviendo.
            models.UniqueConstraint(
                fields=["licorera", "codigo_barras"],
                name="codigo_barras_unico_por_licorera",
            ),
        ]

    def __str__(self):
        return self.nombre


class EntradaMercancia(models.Model):
    """
    Llegada de mercancía del proveedor (RF-INV-05).

    Es el encabezado: el proveedor, la fecha y quién la registró. Las líneas no
    son una tabla aparte —el MER no la tiene— porque **cada línea ES un lote**:
    una entrada de tres referencias crea tres lotes, cada uno con su costo.
    """

    licorera = models.ForeignKey(
        "suscripciones.Licorera", on_delete=models.PROTECT, related_name="entradas",
        db_column="licorera_id",
        help_text="Licorera dueña del registro; sostiene el aislamiento entre negocios.",
    )
    sede = models.ForeignKey(
        "sedes.Sede", on_delete=models.PROTECT, related_name="entradas",
        db_column="sede_id", help_text="Sede que recibe la mercancía.",
    )
    usuario = models.ForeignKey(
        "seguridad.Usuario", on_delete=models.PROTECT, related_name="entradas",
        db_column="usuario_id", help_text="Quién registró la entrada.",
    )
    proveedor = models.CharField(
        max_length=100, null=True, blank=True,
        help_text="Nombre del proveedor (texto libre en esta versión).",
    )
    fecha = models.DateTimeField(
        auto_now_add=True, help_text="Fecha y hora de la entrada.",
    )
    observacion = models.CharField(
        max_length=255, null=True, blank=True,
        help_text="Nota opcional (número de factura del proveedor, etc.).",
    )

    class Meta:
        db_table = "entrada_mercancia"
        verbose_name = "entrada de mercancía"
        verbose_name_plural = "entradas de mercancía"
        ordering = ["-fecha"]

    def __str__(self):
        return f"Entrada {self.id} — {self.fecha:%d/%m/%Y}"


class LoteInventario(models.Model):
    """
    Un lote de mercancía con su costo congelado. **El corazón del PEPS.**

    POR QUÉ EL COSTO VIVE AQUÍ Y NO EN EL PRODUCTO
    Porque el mismo ron comprado en marzo a 38.000 y en junio a 42.000 son dos
    costos reales distintos, y lo que se vendió en abril salió del primero. Un
    costo único por producto obligaría a elegir cuál, y al elegir el último
    falsearía hacia atrás la utilidad de todo lo vendido antes (RF-INV-10).

    POR QUÉ `cantidad_disponible` SÍ SE GUARDA
    La existencia de un producto no se guarda: se suma de sus lotes. Pero lo que
    le queda a un lote sí es una columna, y no es una contradicción: es el dato
    que el PEPS consume y resta, y tiene que poder bloquearse mientras se
    consume para que dos ventas simultáneas no vacíen el mismo lote dos veces.
    Derivarlo exigiría recorrer todas las salidas de la historia en cada venta.
    """

    class Origen(models.TextChoices):
        COMPRA = "compra", "Compra"
        TRASLADO = "traslado", "Traslado"
        AJUSTE_POSITIVO = "ajuste_positivo", "Ajuste positivo"

    producto = models.ForeignKey(
        Producto, on_delete=models.PROTECT, related_name="lotes",
        db_column="producto_id", help_text="Referencia a la que pertenece el lote.",
    )
    sede = models.ForeignKey(
        "sedes.Sede", on_delete=models.PROTECT, related_name="lotes",
        db_column="sede_id",
        help_text="Sede donde está físicamente el lote (las existencias son por sede).",
    )
    origen = models.CharField(
        max_length=15, choices=Origen.choices, default=Origen.COMPRA,
        help_text="Cómo nació el lote.",
    )
    entrada = models.ForeignKey(
        EntradaMercancia, on_delete=models.PROTECT, related_name="lotes",
        null=True, blank=True, db_column="entrada_id",
        help_text="Entrada que lo creó (vacío si nació de un ajuste).",
    )
    # El MER declara además `traslado_id`, que aquí no existe todavía: la tabla
    # `traslado` es del módulo SED, que no se construye. A diferencia de
    # `sede_id`, esta columna admite vacío y siempre lo estaría, así que
    # añadirla el día que SED llegue es una migración barata y sin riesgo. El
    # origen «traslado» sí se declara arriba, porque el MER lo fija y un valor
    # de lista que nadie usa no cuesta nada (D-31).
    cantidad_inicial = models.PositiveIntegerField(
        help_text="Unidades con las que nació el lote.",
    )
    cantidad_disponible = models.PositiveIntegerField(
        help_text="Unidades que aún quedan; el PEPS consume primero los más antiguos.",
    )
    costo_unitario = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text="Costo de adquisición congelado; no se altera por compras posteriores.",
    )
    fecha_ingreso = models.DateTimeField(
        auto_now_add=True, help_text="Define el orden PEPS (primero en entrar, primero en salir).",
    )

    class Meta:
        db_table = "lote_inventario"
        verbose_name = "lote de inventario"
        verbose_name_plural = "lotes de inventario"
        # El orden del PEPS, escrito una vez: por fecha de ingreso y, a igualdad
        # de fecha, por identificador. El desempate importa más de lo que
        # parece: dos lotes de la misma entrada comparten fecha al segundo, y
        # sin un segundo criterio el orden de consumo sería el que quisiera la
        # base ese día, de modo que la misma venta podría costar distinto.
        ordering = ["fecha_ingreso", "id"]

    def __str__(self):
        return f"Lote {self.id} — {self.producto} ({self.cantidad_disponible})"


class MovimientoInventario(models.Model):
    """
    El kardex: registro **inmutable** de todo movimiento de existencias
    (RF-INV-06 y RF-INV-09).

    Ninguna vista escribe aquí por su cuenta: todo pasa por
    `kardex.registrar_movimiento()`. Si cada operación escribiera su propio
    movimiento, bastaría olvidarlo en una para que el kardex dejara de cuadrar,
    y nadie se enteraría hasta el inventario físico.

    `saldo_resultante` es una foto: las existencias del producto en esa sede
    DESPUÉS del movimiento. Se guarda, y no se recalcula al consultar, porque el
    kardex tiene que poder leerse tal como quedó ese día aunque después se
    corrija cualquier otra cosa.
    """

    class Tipo(models.TextChoices):
        ENTRADA = "entrada", "Entrada"
        VENTA = "venta", "Venta"
        ANULACION_VENTA = "anulacion_venta", "Anulación de venta"
        AJUSTE_POSITIVO = "ajuste_positivo", "Ajuste positivo"
        AJUSTE_NEGATIVO = "ajuste_negativo", "Ajuste negativo"
        TRASLADO_SALIDA = "traslado_salida", "Traslado (salida)"
        TRASLADO_ENTRADA = "traslado_entrada", "Traslado (entrada)"

    class Documento(models.TextChoices):
        ENTRADA = "entrada", "Entrada"
        VENTA = "venta", "Venta"
        TRASLADO = "traslado", "Traslado"
        AJUSTE = "ajuste", "Ajuste"

    licorera = models.ForeignKey(
        "suscripciones.Licorera", on_delete=models.PROTECT, related_name="movimientos",
        db_column="licorera_id",
        help_text="Licorera dueña del registro; sostiene el aislamiento entre negocios.",
    )
    producto = models.ForeignKey(
        Producto, on_delete=models.PROTECT, related_name="movimientos",
        db_column="producto_id", help_text="Referencia afectada.",
    )
    sede = models.ForeignKey(
        "sedes.Sede", on_delete=models.PROTECT, related_name="movimientos",
        db_column="sede_id", help_text="Sede afectada.",
    )
    lote = models.ForeignKey(
        LoteInventario, on_delete=models.PROTECT, related_name="movimientos",
        null=True, blank=True, db_column="lote_id",
        help_text="Lote afectado, si aplica.",
    )
    tipo = models.CharField(
        max_length=16, choices=Tipo.choices, help_text="Naturaleza del movimiento.",
    )
    cantidad = models.IntegerField(
        help_text="Positiva si suma a las existencias, negativa si resta.",
    )
    costo_unitario = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Costo asociado al movimiento, para el kardex valorizado.",
    )
    documento_tipo = models.CharField(
        max_length=10, choices=Documento.choices,
        help_text="Tipo del documento que originó el movimiento.",
    )
    documento_id = models.BigIntegerField(
        help_text="Identificador del documento origen (trazabilidad total).",
    )
    usuario = models.ForeignKey(
        "seguridad.Usuario", on_delete=models.PROTECT, related_name="movimientos",
        db_column="usuario_id", help_text="Quién causó el movimiento.",
    )
    motivo = models.CharField(
        max_length=255, null=True, blank=True,
        help_text="Obligatorio en los ajustes (RF-INV-06): merma, rotura, conteo…",
    )
    saldo_resultante = models.PositiveIntegerField(
        help_text="Existencias del producto en la sede después del movimiento.",
    )
    fecha = models.DateTimeField(auto_now_add=True, help_text="Fecha y hora del movimiento.")

    class Meta:
        db_table = "movimiento_inventario"
        verbose_name = "movimiento de inventario"
        verbose_name_plural = "movimientos de inventario"
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"{self.get_tipo_display()} {self.cantidad:+d} — {self.producto}"
