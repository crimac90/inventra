"""
Direcciones principales de INVENTRA.

Este archivo es la puerta de entrada: recibe la dirección que pide el cliente y
decide qué parte del sistema la atiende. A medida que se construyan los módulos,
cada uno registra aquí su propio grupo de direcciones bajo /api/.

No se incluye el panel de administración de Django: INVENTRA se opera desde su
propia interfaz en React, que consume esta API.
"""

from django.conf import settings
from django.http import FileResponse, HttpResponse, JsonResponse
from django.urls import include, path, re_path


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


# La interfaz compilada. Cualquier dirección que no empiece por `api/` devuelve
# el `index.html` de Vite y es la propia interfaz, ya en el navegador, la que
# decide qué pantalla dibujar.
#
# El comodín hace falta por las recargas: quien está en `/ventas/historial` y
# pulsa F5 pide esa dirección AL SERVIDOR, que no la conoce. Sin esta línea
# recibiría un 404 en una pantalla que funciona perfectamente al llegar
# navegando.
#
# Va al final de la lista y excluye `api/` con una mirada hacia delante, para
# no tragarse las direcciones de la API ni dejar que un módulo futuro quede
# tapado por error.
def interfaz(request):
    """La pagina de la interfaz, tal como la dejo la compilacion."""
    pagina = settings.INTERFAZ_COMPILADA / "index.html"
    if not pagina.exists():
        # Pasa en un equipo donde nunca se ejecuto la compilacion. Se dice lo
        # que falta en vez de dejar un error del servidor sin explicacion.
        return HttpResponse(
            "La interfaz no esta compilada. Ejecuta «npm run build» en frontend/.",
            status=503, content_type="text/plain; charset=utf-8")
    # Se entrega el archivo y no se procesa como plantilla: lo que hay dentro
    # es JavaScript compilado, y una llave doble ahi no es una variable de
    # Django, es codigo.
    return FileResponse(pagina.open("rb"), content_type="text/html; charset=utf-8")


urlpatterns = [
    path("api/estado/", estado, name="estado"),
    path("api/seguridad/", include("seguridad.urls")),
    path("api/suscripciones/", include("suscripciones.urls")),
    path("api/inventario/", include("inventario.urls")),
    path("api/ventas/", include("ventas.urls")),

    # Las direcciones de los demás módulos se agregan aquí a medida que se construyen.

    re_path(r"^(?!api/).*$", interfaz, name="interfaz"),
]
