"""
Carga inicial de los medios de pago.

Los tres que nombra RF-VEN-02. Se cargan en una migración, como los planes y
los roles, porque son datos que el sistema necesita para funcionar desde el
primer arranque: sin ellos no se puede registrar una venta. No son información
que capture el usuario y ninguna pantalla los crea.

La lista va escrita aquí y no importada del modelo a propósito: una migración
es la foto de lo que se hizo aquel día, y tiene que seguir produciendo lo mismo
aunque el modelo cambie después.
"""

from django.db import migrations

MEDIOS = ["efectivo", "transferencia", "tarjeta"]


def cargar(apps, schema_editor):
    MedioPago = apps.get_model("ventas", "MedioPago")
    for nombre in MEDIOS:
        MedioPago.objects.get_or_create(nombre=nombre, defaults={"activo": True})


def retirar(apps, schema_editor):
    """
    Al revertir no se borra nada.

    `venta.medio_pago_id` está declarada con PROTECT, así que borrarlos fallaría
    en cuanto exista una sola venta. Y un catálogo que el sistema necesita para
    arrancar no es algo que convenga retirar por revertir una migración.
    """


class Migration(migrations.Migration):

    dependencies = [("ventas", "0001_initial")]

    operations = [migrations.RunPython(cargar, retirar)]
