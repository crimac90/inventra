"""
Permisos del módulo de suscripciones.

Aquí vive la regla que traduce el estado de la suscripción en conducta
(RF-SUS-03): una cuenta suspendida deja consultar y no deja registrar.

POR QUÉ ES UN PERMISO Y NO UNA COMPROBACIÓN EN CADA VISTA
Lo van a preguntar INV, VEN, SED y FAC antes de cada escritura. Escrita en cada
vista, la regla se repetiría en decenas de sitios y bastaría olvidarla en uno
para que un negocio suspendido siguiera registrando ventas. Escrita aquí, se
añade a una vista con una línea y se comprueba antes de que la petición toque la
base de datos.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission


SIN_VERIFICAR = (
    "Para registrar información primero tienes que confirmar tu correo. Te enviamos "
    "un enlace a tu dirección; ábrelo y vuelve a intentarlo."
)

SIN_SUSCRIPCION = (
    "Tu suscripción no está vigente. Puedes consultar tu información, pero el "
    "sistema no admite registrar operaciones nuevas hasta que actives un plan."
)


class PuedeRegistrarOperaciones(BasePermission):
    """
    Deja consultar siempre y registrar solo con el correo confirmado y la
    suscripción vigente.

    DOS MOTIVOS, UN SOLO PERMISO (decisión D-29)
    Hasta el 05/10/2026 solo miraba la suscripción. Se le añadió el correo sin
    confirmar porque la prueba gratuita entrega quince días del plan Pro, y
    entregar eso a una dirección que nadie demostró controlar es regalar el
    producto a un desconocido. Como la regla es la misma —consultar sí,
    registrar no— vive en el mismo sitio en vez de en un permiso paralelo que
    habría que recordar enganchar en cada vista nueva.

    «Vigente» incluye la cuenta en mora: durante los días de gracia el negocio
    opera con normalidad y solo ve un aviso de pago (D-25). El corte llega con
    la suspensión.

    EL ORDEN IMPORTA, Y ES A PROPÓSITO
    Con varios permisos DRF devuelve el mensaje del primero que falla, y aquí
    los dos motivos viven dentro de uno solo, así que el orden lo decide este
    método. Se mira primero el correo: es la condición más básica —sin ella no
    sabemos ni a quién pertenece la cuenta— y es la única que la persona puede
    resolver sola en un minuto. Decirle que renueve el plan a quien además no ha
    confirmado su correo lo manda a resolver lo caro antes que lo inmediato.
    """

    message = SIN_SUSCRIPCION

    def has_permission(self, request, view):
        # Consultar siempre se puede: es media frase del requisito, «permite
        # consultar la información, pero no registrar operaciones nuevas».
        if request.method in SAFE_METHODS:
            return True

        usuario = request.user
        if not usuario.is_authenticated:
            return False

        # El personal de INVENTRA no pertenece a ninguna licorera y por tanto no
        # tiene suscripción que mirar. Lo que puede hacer lo decide su propio
        # permiso; este no le corresponde. El correo sí se le exige: la razón
        # —saber a quién pertenece la cuenta— no depende de tener negocio.
        if not usuario.correo_verificado:
            self.message = SIN_VERIFICAR
            return False

        if usuario.licorera_id is None:
            return True

        return usuario.licorera.suscripcion_vigente() is not None
