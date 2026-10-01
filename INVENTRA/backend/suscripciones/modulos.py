"""
Catálogo de módulos y en qué estado le llega cada uno a una licorera (RF-SUS-04).

POR QUÉ EXISTE ESTE ARCHIVO
El menú lateral decidía por su cuenta qué mostrar: la lista de módulos y la
marca «Pronto» estaban escritas a mano en el componente. Mientras todo estuviera
por construir no se notaba, pero esconde un error que sí se ve hoy: a una
licorera con plan Básico, el menú le dice que Sedes llegará «Pronto», y para
ella no va a llegar nunca, porque multisede es del plan Pro. Decirle «Pronto» a
quien nunca lo va a tener es prometer lo que no se piensa cumplir.

Tres estados, y el orden en que se deciden importa:

    plan        la característica no está en el plan contratado. Se responde
                primero: para esa licorera el módulo no existe, esté construido
                o no, y lo que corresponde es ofrecerle el plan que lo incluye,
                como pide la ERS.
    pronto      está en su plan pero todavía no se ha construido.
    disponible  está en su plan y se puede usar.

QUÉ NO DECIDE ESTE ARCHIVO
Qué módulos ve un vendedor y cuáles no. Eso depende del rol y se resuelve en el
frontend como cortesía, con el permiso del backend detrás: ocultar una entrada
del menú no protege nada.
"""

from .models import Plan

Caracteristica = Plan.Caracteristica


class Modulo:
    """Un módulo del producto, con lo que hace falta para situarlo en el menú."""

    def __init__(self, clave, texto, construido, caracteristica=None):
        self.clave = clave
        self.texto = texto
        self.construido = construido
        # None significa que el módulo entra en todos los planes. No es lo mismo
        # que «sin restricción conocida»: es una afirmación del catálogo.
        self.caracteristica = caracteristica

    def estado(self, plan):
        if (self.caracteristica is not None
                and plan is not None
                and not plan.incluye(self.caracteristica)):
            return "plan"
        return "disponible" if self.construido else "pronto"


# El orden es el del prototipo y el del punto 8.2 del documento de diseño.
# `construido` se cambia aquí el día que cada módulo se termine, y el menú se
# entera solo.
MODULOS = [
    Modulo("panel", "Panel", construido=True),
    Modulo("usuarios", "Usuarios", construido=True),
    Modulo("inventario", "Inventario", construido=False),
    Modulo("ventas", "Ventas", construido=False),
    Modulo("reportes", "Reportes", construido=False),
    Modulo("sedes", "Sedes", construido=False,
           caracteristica=Caracteristica.MULTISEDE),
]

# Reportes no lleva característica a propósito: el plan Básico incluye los
# reportes básicos, y lo que el Pro añade son la rotación y la utilidad. La
# restricción vive dentro del módulo, no en la puerta.


def estado_de_los_modulos(plan):
    """La lista que el frontend necesita para pintar el menú."""
    return [{"clave": m.clave, "texto": m.texto, "estado": m.estado(plan)}
            for m in MODULOS]
