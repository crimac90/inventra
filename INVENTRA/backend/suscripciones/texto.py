"""
Ayudas de redacción compartidas por las órdenes de consola.

POR QUÉ EXISTE ESTE ARCHIVO
El manual de marca fija que se escribe el plural y no «(s)». La regla se
redactó pensando en los mensajes de la aplicación y vale igual para lo que sale
por consola: quien lee «1 suscripción(es)» deja de estar seguro de que el
sistema contó bien, que es justo lo contrario de lo que un resumen debe
transmitir.

`cargar_datos_demo` la cumplía con una función escrita dentro de él y
`actualizar_estados_suscripciones` no la cumplía en absoluto. Una regla aplicada
en un solo sitio es media regla (regla 14), así que la función vive aquí y las
dos órdenes la usan.
"""


def plural(cantidad, singular, plural_irregular=None):
    """«1 usuario», «3 usuarios»: el número manda sobre la palabra."""
    if cantidad == 1:
        return "%d %s" % (cantidad, singular)
    return "%d %s" % (cantidad, plural_irregular or singular + "s")


def concuerda(cantidad, singular, plural_):
    """La forma verbal o adjetiva que le toca a esa cantidad."""
    return singular if cantidad == 1 else plural_
