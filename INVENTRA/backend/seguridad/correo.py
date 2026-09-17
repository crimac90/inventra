"""
Mensajes de correo del módulo de seguridad.

Se aparta del resto del código por dos razones: el texto que recibe el usuario es
contenido, no lógica, y así se puede cambiar sin tocar las vistas; y el envío es
la única parte del módulo que depende de un servicio externo, de modo que queda
aislada en un solo archivo.
"""

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

ASUNTO_RECUPERACION = "Restablecimiento de contraseña en INVENTRA"


def construir_enlace_recuperacion(usuario):
    """
    Arma la dirección que se le envía al usuario.

    El enlace apunta al frontend, no a la API: quien lo abre es una persona con un
    navegador, que necesita un formulario donde escribir la contraseña nueva. Esa
    pantalla toma los dos valores de la dirección y se los entrega a la API.
    """
    identificador = urlsafe_base64_encode(force_bytes(usuario.pk))
    token = default_token_generator.make_token(usuario)
    base = settings.FRONTEND_URL.rstrip("/")
    return f"{base}/restablecer-contrasena?uid={identificador}&token={token}"


def enviar_correo_recuperacion(usuario):
    """Envía el enlace de restablecimiento a la dirección registrada de la cuenta."""
    enlace = construir_enlace_recuperacion(usuario)
    minutos = settings.PASSWORD_RESET_TIMEOUT // 60

    cuerpo = (
        f"Hola, {usuario.nombre_completo}:\n\n"
        "Recibimos una solicitud para restablecer la contraseña de tu cuenta en INVENTRA.\n\n"
        "Para definir una contraseña nueva, abre el siguiente enlace:\n\n"
        f"{enlace}\n\n"
        f"El enlace vence en {minutos} minutos y solo puede usarse una vez.\n\n"
        "Si no solicitaste este cambio, ignora este mensaje: tu contraseña actual\n"
        "sigue siendo válida.\n\n"
        "INVENTRA\n"
    )

    send_mail(
        subject=ASUNTO_RECUPERACION,
        message=cuerpo,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[usuario.correo],
        fail_silently=False,
    )
    return enlace
