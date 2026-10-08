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
