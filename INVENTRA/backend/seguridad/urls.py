"""Direcciones del módulo de seguridad."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CambiarContrasenaView,
    CierreSesionView,
    InicioSesionView,
    PerfilView,
    RenovacionView,
    RestablecerContrasenaView,
    RolesView,
    SolicitarRecuperacionView,
    UsuarioViewSet,
)

# El enrutador genera automáticamente las direcciones del conjunto de vistas:
#   /usuarios/           listar y crear
#   /usuarios/<id>/      consultar, modificar e inactivar
#   /usuarios/<id>/reactivar/
enrutador = DefaultRouter()
enrutador.register(r"usuarios", UsuarioViewSet, basename="usuario")

urlpatterns = [
    path("ingresar/", InicioSesionView.as_view(), name="ingresar"),
    path("salir/", CierreSesionView.as_view(), name="salir"),
    path("renovar/", RenovacionView.as_view(), name="renovar"),
    path("perfil/", PerfilView.as_view(), name="perfil"),
    path("cambiar-contrasena/", CambiarContrasenaView.as_view(), name="cambiar-contrasena"),
    path("recuperar/", SolicitarRecuperacionView.as_view(), name="recuperar"),
    path("restablecer/", RestablecerContrasenaView.as_view(), name="restablecer"),
    path("roles/", RolesView.as_view(), name="roles"),
    path("", include(enrutador.urls)),
]
