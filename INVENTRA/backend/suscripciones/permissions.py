"""
Permisos del módulo de suscripciones.

Aquí vive la regla que traduce el estado de la suscripción en conducta
(RF-SUS-03): una cuenta suspendida deja consultar y no deja registrar.

POR QUÉ ES UN PERMISO Y NO UNA COMPROBACIÓN EN CADA VISTA
Lo van a preguntar INV, VEN, SED y FAC antes de cada escritura. Escrita en cada
vista, la regla se repetiría en decenas de sitios y bastaría olvidarla en uno
para que un negocio suspendido siguiera registrando ventas. Escrita aquí, se
añade a una vista con una línea y se comprueba antes de que la petición toque la
base de datos.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission


class PuedeRegistrarOperaciones(BasePermission):
    """
    Deja consultar siempre y registrar solo con la suscripción vigente.

    «Vigente» incluye la cuenta en mora: durante los días de gracia el negocio
    opera con normalidad y solo ve un aviso de pago (D-25). El corte llega con
    la suspensión.
    """

    message = (
        "Tu suscripción no está vigente. Puedes consultar tu información, pero el "
        "sistema no admite registrar operaciones nuevas hasta que actives un plan."
    )

    def has_permission(self, request, view):
        # Consultar siempre se puede: es media frase del requisito, «permite
        # consultar la información, pero no registrar operaciones nuevas».
        if request.method in SAFE_METHODS:
            return True

        usuario = request.user
        if not usuario.is_authenticated:
            return False

        # El personal de INVENTRA no pertenece a ninguna licorera y por tanto no
        # tiene suscripción que mirar. Lo que puede hacer lo decide su propio
        # permiso; este no le corresponde.
        if usuario.licorera_id is None:
            return True

        return usuario.licorera.suscripcion_vigente() is not None
