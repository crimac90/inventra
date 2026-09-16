"""
Permisos del sistema.

Un permiso responde una sola pregunta antes de que la vista haga nada: ¿este
usuario puede realizar esta acción? Si la respuesta es no, la petición se
rechaza con código 403 y no llega a tocar la base de datos.
"""

from rest_framework.permissions import BasePermission

from .models import Rol


class EsAdministradorDeLicorera(BasePermission):
    """
    Solo el administrador de una licorera gestiona los usuarios de su negocio
    (RF-SEG-05). El vendedor no puede crear ni modificar cuentas.
    """

    message = "Esta acción solo la puede realizar el administrador de la licorera."

    def has_permission(self, request, view):
        usuario = request.user
        return (
            usuario.is_authenticated
            and usuario.licorera_id is not None
            and usuario.rol.nombre == Rol.ADMINISTRADOR_LICORERA
        )


class EsAdministradorDeInventra(BasePermission):
    """Reservado al personal de la plataforma: administra licoreras y planes."""

    message = "Esta acción solo la puede realizar el personal de INVENTRA."

    def has_permission(self, request, view):
        usuario = request.user
        return usuario.is_authenticated and usuario.es_administrador_inventra
