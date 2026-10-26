# -*- coding: utf-8 -*-
"""
Los dos avisos del módulo: una jornada que cerró descuadrada y una venta
anulada.

**La diferencia de caja.** El aviso del panel se retira en cuanto alguien
escribe una explicación, y quien cierra la caja suele ser el vendedor. Sin
este correo bastaría escribir cualquier cosa para que el dueño no se enterara
nunca de que faltó dinero. Por eso el mensaje lleva dentro la explicación:
quien lo recibe puede juzgar si lo escrito explica algo sin entrar al sistema.

**La anulación.** Una venta anulada no deja rastro en el cierre, y no por un
descuido: lo anulado no cuenta como dinero, de modo que si el efectivo se
devolvió al cliente el cajón cuadra igual. Eso vale tanto para la devolución
legítima como para la que no lo es —quien anula una venta y se queda el
efectivo deja la caja cuadrada al céntimo—, así que el cierre no puede
detectarla y el historial solo la enseña a quien va a buscarla. El correo es
el único sitio donde una anulación sale a buscar a quien debe juzgarla.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail

from suscripciones.correo import administradores

registro = logging.getLogger(__name__)

ASUNTO = "Diferencia en el cierre de caja"
ASUNTO_ANULACION = "Se anuló una venta"


def _enviar(asunto, cuerpo, destinatarios):
    """
    Manda el aviso sin que un fallo del correo tumbe la operación.

    Un aviso es la consecuencia de algo que ya ocurrió, no parte de ello. Si el
    servidor de correo no responde, la venta sigue anulada y la caja sigue
    cerrada: hacer fracasar la operación por el aviso deja al negocio sin poder
    deshacer una venta porque el proveedor de correo está caído, y además
    esconde el fallo real detrás de un error del servidor que no explica nada.

    Lo que no se hace es callarlo: queda en el registro del servidor, que es
    donde se mira cuando alguien dice que no le llegó el correo.
    """
    try:
        send_mail(
            subject=asunto,
            message=cuerpo,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=destinatarios,
            fail_silently=False,
        )
    except Exception:
        registro.exception("No se pudo enviar el aviso «%s» a %s",
                           asunto, ", ".join(destinatarios))


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
          "apartado de cierre de caja.\n\n"
          "INVENTRA\n"
    )

    _enviar(ASUNTO, cuerpo, destinatarios)


def enviar_aviso_de_anulacion(venta):
    """
    Avisa a los administradores activos de que una venta se deshizo.

    Lleva el número, el monto, el motivo y quién la anuló, que es lo que hace
    falta para juzgarla sin entrar.

    No se excluye del envío a quien anuló. Es el mismo grupo de destinatarios,
    y quitarlo obligaría a preguntarse quién recibió qué el día que haya que
    reconstruir lo que pasó.
    """
    destinatarios = [u.correo for u in administradores(venta.licorera)]
    if not destinatarios:
        return

    cuerpo = (
        f"Se anuló la venta #{venta.consecutivo} de «{venta.sede}».\n\n"
        f"Fecha de la venta: {venta.fecha:%d/%m/%Y %H:%M}\n"
        f"Total: ${venta.total:,.0f} ({venta.medio_pago.nombre})\n"
        f"La registró: {venta.usuario.nombre_completo}\n"
        f"La anuló: {venta.anulada_por.nombre_completo}\n\n"
        f"Motivo:\n{venta.motivo_anulacion}\n\n"
        "La mercancía volvió al inventario, cada unidad al lote del que salió.\n"
        "El cierre de caja no refleja esta venta, de modo que si el efectivo no\n"
        "se devolvió al cliente la caja cerrará con un sobrante.\n\n"
        "INVENTRA\n"
    )

    _enviar(ASUNTO_ANULACION, cuerpo, destinatarios)
