"""
Carga inicial del catálogo de roles.

Los tres roles del sistema están definidos en la especificación de requisitos
(RF-SEG-05) y en el documento de historias de usuario. Se cargan aquí para que
toda instalación nueva pueda crear usuarios desde el primer momento.
"""

from django.db import migrations


ROLES = [
    (
        "administrador_licorera",
        "Dueño o encargado de la licorera; gestiona productos, inventario, "
        "usuarios, reportes y configuración.",
    ),
    (
        "vendedor",
        "Registra las ventas y consulta existencias.",
    ),
    (
        "administrador_inventra",
        "Administra la plataforma: licoreras, planes y estado de las suscripciones.",
    ),
]


def cargar_roles(apps, schema_editor):
    Rol = apps.get_model("seguridad", "Rol")
    for nombre, descripcion in ROLES:
        Rol.objects.get_or_create(nombre=nombre, defaults={"descripcion": descripcion})


def borrar_roles(apps, schema_editor):
    Rol = apps.get_model("seguridad", "Rol")
    Rol.objects.filter(nombre__in=[nombre for nombre, _ in ROLES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("seguridad", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(cargar_roles, borrar_roles),
    ]
