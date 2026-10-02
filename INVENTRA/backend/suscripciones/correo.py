# -*- coding: utf-8 -*-
"""
Mensajes de correo del módulo de suscripciones.

Separados de los de seguridad por la misma razón que aquéllos están juntos: el
texto que lee el negocio es contenido, no lógica, y conviene poder cambiarlo sin
entrar en las vistas. Lo que no se duplica es el mecanismo: el enlace para
definir la contraseña es el mismo de la recuperación, ya construido y probado.
"""

from django.conf import settings
from django.core.mail import send_mail

from seguridad.correo import construir_enlace_recuperacion
from seguridad.models import Rol

ASUNTO_ALTA = "Tu licorera ya está creada en INVENTRA"
ASUNTO_VENCIMIENTO = "Vigencia de tu suscripción en INVENTRA"


def administradores(licorera):
    """
    A quién se le avisa de lo que pasa con la suscripción: a quien puede hacer
    algo al respecto. Solo las cuentas activas; una dada de baja no lee nada.
    """
    return list(
        licorera.usuarios
        .filter(activo=True, rol__nombre=Rol.ADMINISTRADOR_LICORERA)
        .order_by("id")
    )


def enviar_correo_alta(usuario):
    """
    Avisa al dueño de que su licorera está creada y le pide definir su contraseña.

    La cuenta nace **sin contraseña utilizable**: la escribe su dueño abriendo
    este enlace. Así el Administrador INVENTRA nunca llega a conocer la clave de
    un cliente, que es lo correcto y además lo único que se puede sostener si
    algún día hay que explicar quién pudo entrar a una cuenta.
    """
    enlace = construir_enlace_recuperacion(usuario)
    minutos = settings.PASSWORD_RESET_TIMEOUT // 60

    cuerpo = (
        f"Hola, {usuario.nombre_completo}:\n\n"
        f"Tu licorera «{usuario.licorera.nombre}» ya está creada en INVENTRA.\n\n"
        "Por seguridad, tu cuenta todavía no tiene contraseña: la defines tú, abriendo\n"
        "el siguiente enlace:\n\n"
        f"{enlace}\n\n"
        f"El enlace vence en {minutos} minutos y solo puede usarse una vez. Si se te\n"
        "pasa el plazo, puedes pedir otro desde la pantalla de acceso, en «¿Olvidaste\n"
        "tu contraseña?».\n\n"
        "INVENTRA\n"
    )

    send_mail(
        subject=ASUNTO_ALTA,
        message=cuerpo,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[usuario.correo],
        fail_silently=False,
    )
    return enlace


def enviar_correo_vencimiento(licorera, suscripcion):
    """
    Avisa de hasta cuándo vale la suscripción (decisión D-25).

    Sale cada vez que el Administrador INVENTRA fija o corrige esa fecha, y
    **solo entonces**. La orden que pone al día los estados no pasa por aquí
    porque no escribe la fecha: esa es la garantía de que nadie recibe un correo
    cada día que su suscripción cambia de estado sola.
    """
    destinatarios = [a.correo for a in administradores(licorera)]
    if not destinatarios:
        # Una licorera sin administrador activo no es un error de este envío; se
        # calla en vez de fallar y dejar la operación a medias.
        return []

    cuerpo = (
        f"Hola:\n\n"
        f"La suscripción de «{licorera.nombre}» quedó registrada con estos datos:\n\n"
        f"    Plan:     {suscripcion.plan.nombre}\n"
        f"    Vigencia: hasta el {suscripcion.fecha_fin:%d/%m/%Y}\n\n"
        "A partir de esa fecha tu licorera sigue funcionando cuatro días más, con un\n"
        "aviso de pago a la vista. Pasados esos cuatro días tu información se conserva\n"
        "y la puedes seguir consultando, pero el sistema deja de admitir registros\n"
        "nuevos hasta que renueves.\n\n"
        "Si esta fecha no es la que acordaste, comunícate con nosotros.\n\n"
        "INVENTRA\n"
    )

    send_mail(
        subject=ASUNTO_VENCIMIENTO,
        message=cuerpo,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=destinatarios,
        fail_silently=False,
    )
    return destinatarios
