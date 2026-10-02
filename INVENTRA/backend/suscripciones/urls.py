"""Direcciones del módulo de suscripciones."""

from django.urls import path

from .vistas_panel import AltaLicoreraView, PanelView, SuscripcionDeLicoreraView
from .views import (CambiarPlanView, MiSuscripcionView, MisModulosView,
                    PlanesView, RegistroLicoreraView)

urlpatterns = [
    path("registrar/", RegistroLicoreraView.as_view(), name="registrar-licorera"),
    path("planes/", PlanesView.as_view(), name="planes"),
    path("mi-suscripcion/", MiSuscripcionView.as_view(), name="mi-suscripcion"),
    path("mis-modulos/", MisModulosView.as_view(), name="mis-modulos"),
    path("cambiar-plan/", CambiarPlanView.as_view(), name="cambiar-plan"),

    # Panel de la plataforma. Van bajo «panel/» y no sueltas para que se vea de
    # un vistazo cuáles son del operador de INVENTRA y cuáles de un negocio.
    path("panel/", PanelView.as_view(), name="panel"),
    path("panel/licoreras/", AltaLicoreraView.as_view(), name="alta-licorera"),
    path("panel/licoreras/<int:id_licorera>/suscripcion/",
         SuscripcionDeLicoreraView.as_view(), name="suscripcion-de-licorera"),
]
