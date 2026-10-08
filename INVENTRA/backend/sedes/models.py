"""
Sedes de una licorera (módulo SED del MER).

POR QUÉ ESTA APP EXISTE ANTES QUE SU MÓDULO (decisión D-30)
El módulo SED —RF-SED-01 a 05: crear sedes, asignar vendedores, trasladar
mercancía— NO está en el cronograma y no se construye en esta entrega. Pero el
MER declara `sede_id` como llave foránea **no nula** en cinco tablas que sí se
construyen: `lote_inventario`, `entrada_mercancia` y `movimiento_inventario` en
INV, y `venta` y `cierre_caja` en VEN. Las existencias son por sede.

Así que la tabla se crea con la forma que el modelo le da, y cada licorera nace
con una «Sede principal». No hay pantalla, ni dirección de la API, ni entrada en
el menú: solo la fila que el inventario necesita para existir. Lo que esto
compra es no tener que añadir una columna obligatoria a tablas con lotes,
movimientos y ventas dentro, en mitad del módulo más complejo.

El modelo vive en su propia app y no dentro de `inventario` porque la tabla es
de SED: el día que ese módulo se construya, se le añaden vistas aquí en vez de
mover un modelo de sitio, que en Django obliga a migrar la tabla entera.
"""

from django.db import models


class Sede(models.Model):
    """Punto de venta físico de una licorera (RF-SED-01)."""

    # Nombre de la sede que se crea con cada licorera. Está aquí y no escrito en
    # las dos vistas que registran negocios, para que las dos digan lo mismo.
    NOMBRE_PRINCIPAL = "Sede principal"

    licorera = models.ForeignKey(
        "suscripciones.Licorera", on_delete=models.PROTECT, related_name="sedes",
        db_column="licorera_id",
        help_text="Licorera dueña del registro; sostiene el aislamiento entre negocios.",
    )
    nombre = models.CharField(
        max_length=80,
        help_text="Nombre de la sede («Sede principal», «Sucursal Centro»…).",
    )
    direccion = models.CharField(
        max_length=150, null=True, blank=True, help_text="Dirección física.",
    )
    telefono = models.CharField(
        max_length=20, null=True, blank=True, help_text="Teléfono de la sede.",
    )
    activo = models.BooleanField(
        default=True,
        help_text="Baja lógica: una sede cerrada conserva su historial.",
    )

    class Meta:
        db_table = "sede"
        verbose_name = "sede"
        verbose_name_plural = "sedes"

    def __str__(self):
        return f"{self.nombre} — {self.licorera}"

    @classmethod
    def crear_principal(cls, licorera):
        """
        Crea la sede con la que nace toda licorera.

        Las dos puertas del registro —autoservicio y alta por INVENTRA— llaman
        aquí, igual que los datos de demostración. Escrito en cada sitio, bastaría
        olvidarlo en uno para que una licorera naciera sin sede y su inventario no
        se pudiera registrar; y el error aparecería en el módulo siguiente, lejos
        de su causa.
        """
        return cls.objects.create(licorera=licorera, nombre=cls.NOMBRE_PRINCIPAL)

    @classmethod
    def principal_de(cls, licorera):
        """
        La sede donde se registra el inventario de esta licorera.

        Mientras SED no se construya la respuesta es siempre la misma, pero el
        inventario **pregunta** en vez de suponerlo (D-31): un supuesto escrito a
        mano no falla cuando deja de ser cierto, devuelve el resultado equivocado
        en silencio. El día que haya varias sedes, lo que cambia es esta función
        y no las diez que la llaman.
        """
        return cls.objects.filter(licorera=licorera, activo=True).order_by("id").first()
