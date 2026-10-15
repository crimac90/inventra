"""
Siembra las categorías de las licoreras que ya existían.

`preparar_licorera_nueva()` siembra las categorías al CREAR una licorera, lo
que deja fuera a las que ya estaban en la base cuando se añadió el catálogo.
Una licorera sin categorías no puede registrar productos: su formulario no
tiene ninguna que elegir. Por eso la siembra de las anteriores es una
migración y no una línea de código.

Es una migración de DATOS y no de estructura: no crea ni cambia ninguna tabla,
solo rellena filas que faltan. Es repetible: solo toca las licoreras que no
tienen ninguna categoría, así que correrla dos veces no duplica nada.
"""

from django.db import migrations

# Las seis de RF-INV-01. Se escriben aquí y no se importan del modelo a
# propósito: una migración tiene que seguir haciendo lo mismo dentro de un año,
# y si leyera la lista del modelo cambiaría de comportamiento cada vez que la
# lista cambie. Una migración es una foto de lo que se hizo aquel día.
POR_DEFECTO = ("Aguardiente", "Ron", "Cerveza", "Whisky", "Vino", "Otros")


def sembrar(apps, schema_editor):
    Licorera = apps.get_model("suscripciones", "Licorera")
    Categoria = apps.get_model("inventario", "Categoria")

    for licorera in Licorera.objects.all():
        if Categoria.objects.filter(licorera=licorera).exists():
            continue
        Categoria.objects.bulk_create(
            [Categoria(licorera=licorera, nombre=nombre, activo=True)
             for nombre in POR_DEFECTO]
        )


def deshacer(apps, schema_editor):
    """
    No se borra nada al revertir.

    Una categoría puede tener productos colgando, y la llave está declarada con
    PROTECT: borrarlas fallaría o, peor, se llevaría por delante un catálogo.
    Revertir esta migración devuelve la estructura, no los datos.
    """


class Migration(migrations.Migration):

    dependencies = [
        ("inventario", "0003_entradamercancia_loteinventario_movimientoinventario"),
        ("suscripciones", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(sembrar, deshacer),
    ]
