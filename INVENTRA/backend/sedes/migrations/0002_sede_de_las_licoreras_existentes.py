"""
Crea la sede principal de las licoreras que ya existían.

El mismo caso que las categorías del inventario: la sede se crea al registrar
una licorera, y las que ya estaban en la base cuando se añadió la tabla
se quedaron sin ninguna. Sin sede no se puede registrar inventario, porque las
existencias son por sede.

Repetible: solo toca las licoreras que no tienen ninguna.
"""

from django.db import migrations

NOMBRE_PRINCIPAL = "Sede principal"


def crear(apps, schema_editor):
    Licorera = apps.get_model("suscripciones", "Licorera")
    Sede = apps.get_model("sedes", "Sede")

    faltan = [
        Sede(licorera=licorera, nombre=NOMBRE_PRINCIPAL, activo=True)
        for licorera in Licorera.objects.all()
        if not Sede.objects.filter(licorera=licorera).exists()
    ]
    Sede.objects.bulk_create(faltan)


def deshacer(apps, schema_editor):
    """No se borra nada: una sede puede tener lotes y ventas colgando."""


class Migration(migrations.Migration):

    dependencies = [
        ("sedes", "0001_initial"),
        ("suscripciones", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(crear, deshacer),
    ]
