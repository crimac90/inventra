"""Direcciones del módulo de suscripciones."""

from django.urls import path

from .views import PlanesView, RegistroLicoreraView

urlpatterns = [
    path("registrar/", RegistroLicoreraView.as_view(), name="registrar-licorera"),
    path("planes/", PlanesView.as_view(), name="planes"),
]
