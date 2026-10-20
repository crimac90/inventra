"""Direcciones del módulo de ventas."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (CierreDeCajaView, ExplicacionDelCierreView, MediosDePagoView,
                    VentaViewSet)

enrutador = DefaultRouter()
enrutador.register(r"", VentaViewSet, basename="venta")

urlpatterns = [
    path("medios-de-pago/", MediosDePagoView.as_view(), name="medios-de-pago"),
    path("cierre/", CierreDeCajaView.as_view(), name="cierre-de-caja"),
    path("cierre/<int:pk>/explicacion/", ExplicacionDelCierreView.as_view(),
         name="explicacion-del-cierre"),
    path("", include(enrutador.urls)),
]
