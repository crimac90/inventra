# -*- coding: utf-8 -*-
"""
Reglas de negocio de las cuentas que no son de un serializador ni de una vista.

Aquí vive la que protege a la última cuenta de administrador de una licorera.
Se saca a un archivo propio porque hay DOS caminos para dejar una licorera sin
administrador —inactivar la cuenta o cambiarle el rol— y los atiende código
distinto: el primero la vista, el segundo el serializador. Escrita en uno solo,
el otro queda abierto.
"""

from .models import Rol, Usuario

SIN_ADMINISTRADOR = (
    "Es la única cuenta de administrador activa de esta licorera. Nombra antes a "
    "otro administrador: sin ninguno, el negocio no puede registrar usuarios ni "
    "productos, ni gestionar su suscripción."
)


def es_el_unico_administrador(usuario):
    """
    Si esta cuenta es el último administrador activo que le queda a su licorera.

    Una licorera sin administrador activo queda sin salida desde dentro de la
    aplicación: nadie puede crear usuarios, reactivar cuentas ni cambiar de
    plan, y las tres operaciones exigen ese rol. La única reparación sería
    entrar a la base de datos.

    Una cuenta ya inactiva devuelve `False`: no está administrando nada, así
    que nada se pierde al cambiarla.
    """
    if not usuario.activo or usuario.rol.nombre != Rol.ADMINISTRADOR_LICORERA:
        return False

    return not (
        Usuario.objects
        .filter(licorera=usuario.licorera,
                rol__nombre=Rol.ADMINISTRADOR_LICORERA,
                activo=True)
        .exclude(pk=usuario.pk)
        .exists()
    )
