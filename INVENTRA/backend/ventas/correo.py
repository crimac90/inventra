# -*- coding: utf-8 -*-
"""
El aviso de que una jornada cerró descuadrada (D-37).

Es el único correo del módulo, y existe por una razón concreta: el aviso del
panel se retira en cuanto alguien escribe una explicación, y quien cierra la
caja suele ser el vendedor. Sin este correo bastaría escribir cualquier cosa
para que el dueño no se enterara nunca de que faltó dinero.

Por eso el mensaje **lleva dentro la explicación**: quien lo recibe puede
juzgar si lo escrito explica algo sin tener que entrar al sistema.
"""

from django.conf import settings
from django.core.mail import send_mail

from suscripciones.correo import administradores

ASUNTO = "Diferencia en el cierre de caja"


def enviar_aviso_de_diferencia(cierre):
    """
    Avisa a los administradores activos de la licorera. No hace nada si la
    jornada cuadró: un correo que llega todos los días deja de leerse.
    """
    if cierre.diferencia == 0:
        return

    destinatarios = [u.correo for u in administradores(cierre.licorera)]
    if not destinatarios:
        return

    falta = cierre.diferencia < 0
    cuanto = abs(cierre.diferencia)
    explicacion = (cierre.observacion or "").strip()

    cuerpo = (
        f"La caja de «{cierre.sede}» cerró con una diferencia.\n\n"
        f"Jornada: {cierre.fecha:%d/%m/%Y} (de las 06:00 a las 06:00 del día siguiente)\n"
        f"Cerró: {cierre.usuario.nombre_completo}\n\n"
        f"Efectivo según el sistema: ${cierre.total_efectivo:,.0f}\n"
        f"Efectivo contado: ${cierre.efectivo_contado:,.0f}\n"
        f"{'Faltan' if falta else 'Sobran'}: ${cuanto:,.0f}\n\n"
        + (f"Explicación de quien cerró:\n{explicacion}\n\n" if explicacion
           else "No se escribió ninguna explicación.\n\n")
        + "Puedes revisar el cierre y escribir o corregir la explicación desde el\n"
          "historial de ventas.\n\n"
          "INVENTRA\n"
    )

    send_mail(
        subject=ASUNTO,
        message=cuerpo,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=destinatarios,
        fail_silently=False,
    )
