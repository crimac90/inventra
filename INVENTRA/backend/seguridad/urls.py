"""Direcciones del módulo de seguridad."""

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import CierreSesionView, InicioSesionView, PerfilView

urlpatterns = [
    path("ingresar/", InicioSesionView.as_view(), name="ingresar"),
    path("salir/", CierreSesionView.as_view(), name="salir"),
    path("renovar/", TokenRefreshView.as_view(), name="renovar"),
    path("perfil/", PerfilView.as_view(), name="perfil"),
]
