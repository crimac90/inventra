# -*- coding: utf-8 -*-
"""
El texto con el que la API dice que algo no existe.

Django arma el mensaje del 404 con el nombre de la clase del modelo —«No
Producto matches the given query.»— y la librería de la API lo deja llegar tal
cual hasta la respuesta. Eso pone en la pantalla de una persona una frase en
inglés y, de paso, el nombre interno de una tabla.

Importa más de lo que parece porque el 404 no es aquí una respuesta de borde:
es la que sostiene el aislamiento entre negocios. Pedir algo de otra licorera
contesta que no existe, y esa frase tiene que estar escrita a conciencia. No
nombra al dueño ni insinúa que el registro exista en otra parte: decir «no
pertenece a tu licorera» confirmaría justo lo que el 404 se niega a confirmar.
"""

from django.http import Http404
from rest_framework.views import exception_handler

NO_EXISTE = "No se encontró lo que pediste."


def manejador(excepcion, contexto):
    """Deja pasar todo, y solo reescribe el 404 que viene de Django."""
    respuesta = exception_handler(excepcion, contexto)
    if respuesta is not None and isinstance(excepcion, Http404):
        respuesta.data = {"detalle": NO_EXISTE}
    return respuesta
