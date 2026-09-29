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


# ---------------------------------------------------------------------------
# Verificación del correo (D-10, bloque 1 del módulo SUS)
# ---------------------------------------------------------------------------
#
# POR QUÉ NO SE REUTILIZA EL TOKEN DE LA RECUPERACIÓN
# El de la recuperación (`default_token_generator`) calcula su firma con la
# contraseña y la fecha del último ingreso, y eso aquí estorba dos veces: quien
# se registra entra de inmediato al panel —lo que actualiza el último ingreso y
# dejaría inservible el enlace recién enviado— y el enlace debe seguir sirviendo
# aunque la persona cambie su contraseña antes de abrir el correo. Además dura
# treinta minutos, plazo razonable para una contraseña y hostil para un correo
# que puede leerse al día siguiente.
#
# Se usa `TimestampSigner`, que es la misma idea sin esos dos ingredientes: un
# valor firmado con la clave del proyecto, con su fecha dentro, que no se guarda
# en ninguna tabla. Se firma el identificador junto con el correo, de modo que si
# el correo de la cuenta cambia, los enlaces anteriores dejan de valer.
#
# El enlace no se invalida al usarlo, y no hace falta: lo que verifica ya está
# verificado, así que abrirlo dos veces no cambia nada.

ASUNTO_VERIFICACION = "Confirma tu correo en INVENTRA"

SAL_VERIFICACION = "inventra:verificacion-correo"


def _firmante():
    from django.core.signing import TimestampSigner
    return TimestampSigner(salt=SAL_VERIFICACION)


def firmar_verificacion(usuario):
    """Devuelve el valor firmado que viaja en el enlace."""
    return _firmante().sign_object({"uid": usuario.pk, "correo": usuario.correo})


def leer_verificacion(token):
    """
    Devuelve el contenido del token si es válido, o None.

    None cubre los cuatro casos a la vez —vencido, manipulado, mal formado o de
    una cuenta que ya no existe— porque a quien prueba enlaces al azar no se le
    explica cuál de ellos falló.
    """
    from django.core.signing import BadSignature, SignatureExpired
    try:
        return _firmante().unsign_object(token, max_age=settings.EMAIL_VERIFICATION_TIMEOUT)
    except (BadSignature, SignatureExpired, TypeError, ValueError):
        return None


def construir_enlace_verificacion(usuario):
    """La dirección apunta al frontend, que es quien llama a la API con el token."""
    base = settings.FRONTEND_URL.rstrip("/")
    return f"{base}/verificar-correo?token={firmar_verificacion(usuario)}"


def enviar_correo_verificacion(usuario):
    """Envía el enlace de confirmación a la dirección registrada de la cuenta."""
    enlace = construir_enlace_verificacion(usuario)
    dias = settings.EMAIL_VERIFICATION_TIMEOUT // 86400

    cuerpo = (
        f"Hola, {usuario.nombre_completo}:\n\n"
        "Gracias por registrarte en INVENTRA. Para confirmar que este correo es tuyo,\n"
        "abre el siguiente enlace:\n\n"
        f"{enlace}\n\n"
        f"El enlace vence en {dias} días. Mientras tanto puedes usar INVENTRA con\n"
        "normalidad: solo verás un aviso recordándote que confirmes el correo.\n\n"
        "Confirmarlo importa porque es la dirección a la que llega el enlace si algún\n"
        "día olvidas tu contraseña.\n\n"
        "Si no te registraste en INVENTRA, ignora este mensaje.\n\n"
        "INVENTRA\n"
    )

    send_mail(
        subject=ASUNTO_VERIFICACION,
        message=cuerpo,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[usuario.correo],
        fail_silently=False,
    )
    return enlace
