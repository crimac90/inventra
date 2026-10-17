# -*- coding: utf-8 -*-
"""
Añade a la categoría el margen con el que se propone el precio (RF-INV-11).

La columna nace con el mismo valor para todas, que es el punto de partida del
modelo; Django lo escribe en las filas que ya existen al aplicar la migración,
de modo que no hace falta una migración de datos aparte.
"""

from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventario", "0004_categorias_de_las_licoreras_existentes"),
    ]

    operations = [
        migrations.AddField(
            model_name="categoria",
            name="margen_sugerido",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("30.00"),
                help_text=(
                    "Porcentaje sobre el costo con el que se propone el precio de "
                    "venta de sus productos. El sistema propone; nunca aplica."
                ),
                max_digits=5,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("0")),
                    django.core.validators.MaxValueValidator(Decimal("500")),
                ],
            ),
        ),
    ]
