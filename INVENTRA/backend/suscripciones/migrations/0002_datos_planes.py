"""
Carga inicial del catálogo de planes.

Los planes son datos que el sistema necesita para funcionar desde el primer
arranque, no información que capture el usuario. Por eso se cargan en una
migración: cualquier instalación nueva queda con los mismos catálogos.

Valores tomados del modelo de negocio y del requisito RF-SUS-04: el plan Básico
cubre un usuario y una sede, sin facturación electrónica ni reportes avanzados;
el plan Pro habilita multiusuario, multisede, facturación y reportes avanzados.
"""

from django.db import migrations


PLANES = [
    {
        "nombre": "Básico",
        "precio_mensual": "59900.00",
        "maximo_sedes": 1,
        "maximo_usuarios": 1,
        "permite_facturacion": False,
        "permite_reportes_avanzados": False,
    },
    {
        "nombre": "Pro",
        "precio_mensual": "109900.00",
        "maximo_sedes": None,          # sin límite
        "maximo_usuarios": None,       # sin límite
        "permite_facturacion": True,
        "permite_reportes_avanzados": True,
    },
]


def cargar_planes(apps, schema_editor):
    """Crea los planes si no existen. No sobrescribe precios ya registrados."""
    Plan = apps.get_model("suscripciones", "Plan")
    for datos in PLANES:
        Plan.objects.get_or_create(
            nombre=datos["nombre"],
            defaults={**datos, "activo": True},
        )


def borrar_planes(apps, schema_editor):
    """Deshace la carga si la migración se revierte."""
    Plan = apps.get_model("suscripciones", "Plan")
    Plan.objects.filter(nombre__in=[p["nombre"] for p in PLANES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("suscripciones", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(cargar_planes, borrar_planes),
    ]
