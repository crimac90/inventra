"""
Direcciones principales de INVENTRA.

Este archivo es la puerta de entrada: recibe la dirección que pide el cliente y
decide qué parte del sistema la atiende. A medida que se construyan los módulos,
cada uno registra aquí su propio grupo de direcciones bajo /api/.

No se incluye el panel de administración de Django: INVENTRA se opera desde su
propia interfaz en React, que consume esta API.
"""

from django.http import JsonResponse
from django.urls import include, path


def estado(request):
    """
    Comprobación de vida del servicio.

    Responde sin exigir autenticación y sirve para verificar, desde el navegador
    o desde el servidor de despliegue, que la API está en línea.
    """
    return JsonResponse({
        "servicio": "INVENTRA",
        "estado": "en linea",
        "version_api": "v1",
    })


urlpatterns = [
    path("api/estado/", estado, name="estado"),
    path("api/seguridad/", include("seguridad.urls")),

    # Las direcciones de los demás módulos se agregan aquí a medida que se construyen.
]
