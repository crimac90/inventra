"""
Lo que nace junto con una licorera.

POR QUÉ ES UNA FUNCIÓN Y NO TRES LÍNEAS EN CADA SITIO
Una licorera se crea por tres puertas —el registro por autoservicio, el alta
desde el panel de INVENTRA (D-26) y la orden de datos de demostración— y todas
tienen que dejarla en el mismo estado. Repartido, bastaría olvidar una pieza en
una de las tres para que un negocio naciera a medias, y el error no aparecería
ahí: aparecería en INV, al intentar registrar un producto sin categorías o un
lote sin sede, lejos de su causa y semanas después.

Aquí, añadir algo que toda licorera necesite es una línea y vale para las tres.
"""

from inventario.models import Categoria
from sedes.models import Sede


def preparar_licorera_nueva(licorera):
    """
    Deja una licorera recién creada lista para trabajar.

    Es repetible: las dos llamadas de dentro comprueban antes de crear, porque
    la orden de datos de demostración se puede ejecutar dos veces.
    """
    if not licorera.sedes.exists():
        Sede.crear_principal(licorera)
    Categoria.sembrar(licorera)
