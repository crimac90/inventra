"""Direcciones del módulo de inventario."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AlertasDeInventarioView, CategoriasView, EntradaMercanciaViewSet,
    ProductoViewSet)

enrutador = DefaultRouter()
enrutador.register(r"productos", ProductoViewSet, basename="producto")
enrutador.register(r"entradas", EntradaMercanciaViewSet, basename="entrada")

urlpatterns = [
    path("categorias/", CategoriasView.as_view(), name="categorias"),
    path("alertas/", AlertasDeInventarioView.as_view(), name="alertas-inventario"),
    path("", include(enrutador.urls)),
]
