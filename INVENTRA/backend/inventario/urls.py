"""Direcciones del módulo de inventario."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CategoriasView, ProductoViewSet

enrutador = DefaultRouter()
enrutador.register(r"productos", ProductoViewSet, basename="producto")

urlpatterns = [
    path("categorias/", CategoriasView.as_view(), name="categorias"),
    path("", include(enrutador.urls)),
]
