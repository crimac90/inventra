"""Direcciones del módulo de inventario."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CategoriasView, EntradaMercanciaViewSet, MargenesDeCategoriaView,
    ProductoViewSet, ResumenDeInventarioView)

enrutador = DefaultRouter()
enrutador.register(r"productos", ProductoViewSet, basename="producto")
enrutador.register(r"entradas", EntradaMercanciaViewSet, basename="entrada")

urlpatterns = [
    path("categorias/", CategoriasView.as_view(), name="categorias"),
    path("categorias/margenes/", MargenesDeCategoriaView.as_view(), name="margenes"),
    path("resumen/", ResumenDeInventarioView.as_view(), name="resumen-inventario"),
    path("", include(enrutador.urls)),
]
