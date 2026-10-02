"""Direcciones del módulo de suscripciones."""

from django.urls import path

from .views import (CambiarPlanView, MiSuscripcionView, MisModulosView,
                    PlanesView, RegistroLicoreraView)

urlpatterns = [
    path("registrar/", RegistroLicoreraView.as_view(), name="registrar-licorera"),
    path("planes/", PlanesView.as_view(), name="planes"),
    path("mi-suscripcion/", MiSuscripcionView.as_view(), name="mi-suscripcion"),
    path("mis-modulos/", MisModulosView.as_view(), name="mis-modulos"),
    path("cambiar-plan/", CambiarPlanView.as_view(), name="cambiar-plan"),
]
