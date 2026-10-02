# -*- coding: utf-8 -*-
"""
Cambio de plan de una licorera (RF-SUS-02, decisiones D-23 y D-25).

POR QUÉ ESTÁ EN SU PROPIO ARCHIVO Y NO EN LA VISTA
La misma operación la van a disparar dos sitios distintos: la pantalla del
negocio, cuando baja de plan, y el panel de INVENTRA, cuando lo sube tras
cobrar. Escrita dentro de una vista habría que repetirla o llamarla desde fuera
de su sitio, y las reglas que decide —qué se rechaza, qué fecha hereda la fila
nueva, qué precio se congela— no son de la interfaz.

LAS REGLAS, Y DE DÓNDE SALEN

  Quién ejecuta (D-23). Bajar lo hace el administrador de la licorera, porque el
  rechazo tiene que salirle a la única persona que puede decidir qué usuario o
  sede inactiva; subir lo hace el Administrador INVENTRA, porque implica cobrar.
  Esa parte la aplica la vista; aquí se decide cuál de los dos sentidos es.

  Qué se rechaza (D-23). El cambio no se permite mientras la licorera tenga más
  de lo que admite el plan de destino. El sistema dice qué sobra y cuánto, y no
  inactiva nada por su cuenta: eso es una decisión del negocio.

  Qué fecha lleva la fila nueva (D-25). La de la anterior. El cliente no escribe
  fechas de vencimiento; si la heredara calculada, cambiar de plan sería una
  forma de regalarse vigencia. La fila anterior se cierra el día del cambio.

  Durante la prueba no se cambia de plan. La prueba corre sobre Pro para que el
  negocio evalúe el sistema completo (D-22), y bajarse a Básico en mitad de ella
  contradice lo que el manual promete y abriría dos agujeros: la fila nueva
  nacería con precio y ganaría los días de gracia que D-25 reserva a quien paga.
"""

from django.db import transaction
from django.utils import timezone

from .models import Suscripcion


class CambioNoPermitido(Exception):
    """El cambio no procede. El mensaje es para el usuario, no para el registro."""


def en_castellano(cantidad, singular, plural):
    """Escribe «un usuario» en vez del contador seguido del plural entre
    paréntesis: el documento de diseño prohíbe que el usuario vea rastros de
    programación, y esa forma abreviada es uno de los más visibles."""
    return "un %s" % singular if cantidad == 1 else "%d %s" % (cantidad, plural)


def excesos(licorera, plan):
    """
    Qué tiene esta licorera de más para caber en el plan indicado (RF-SUS-02).

    Devuelve frases ya redactadas, con la cifra concreta: quien las lee tiene que
    poder actuar, y «excede el límite de usuarios» no dice cuántos sobran.

    Las sedes entrarán aquí cuando exista el módulo SED. Hoy no hay tabla que
    contar, y escribir la comprobación contra una tabla que no existe sería
    fingir que se comprueba.
    """
    hallazgos = []
    if plan.maximo_usuarios is not None:
        activos = licorera.usuarios.filter(activo=True).count()
        if activos > plan.maximo_usuarios:
            hallazgos.append(
                "el plan %s admite %s y la licorera tiene %s."
                % (plan.nombre,
                   en_castellano(plan.maximo_usuarios, "usuario", "usuarios"),
                   en_castellano(activos, "usuario activo", "usuarios activos")))
    return hallazgos


def es_bajada(actual, destino):
    """
    Si pasar de un plan al otro cuesta menos dinero.

    El sentido se mide por el precio y no por las características porque es el
    precio lo que decide quién puede ejecutarlo: bajar no hay que cobrarlo, y
    por eso puede hacerlo el propio negocio (D-23).
    """
    return destino.precio_mensual < actual.precio_mensual


def comprobar(licorera, destino):
    """Levanta `CambioNoPermitido` con el motivo, o no hace nada si procede."""
    suscripcion = licorera.suscripcion_actual()
    if suscripcion is None:
        raise CambioNoPermitido(
            "Tu licorera no tiene un plan activo. Comunícate con INVENTRA para contratarlo.")

    if suscripcion.es_periodo_gratuito:
        raise CambioNoPermitido(
            "Tu licorera está en período de prueba con el plan Pro, que incluye todas "
            "las funciones. Al terminar la prueba podrás elegir el plan que quieras. Ten "
            "en cuenta que el plan Básico admite un solo usuario y no incluye sedes, "
            "facturación electrónica ni reportes avanzados.")

    if suscripcion.plan_id == destino.id:
        raise CambioNoPermitido("Tu licorera ya tiene el plan %s." % destino.nombre)

    if not destino.activo:
        raise CambioNoPermitido("El plan %s no está disponible." % destino.nombre)

    sobra = excesos(licorera, destino)
    if sobra:
        raise CambioNoPermitido(
            "No se puede cambiar al plan %s todavía: %s Inactiva lo que no necesites y "
            "vuelve a intentarlo." % (destino.nombre, " ".join(sobra)))

    return suscripcion


@transaction.atomic
def cambiar(licorera, destino):
    """
    Cierra la suscripción actual y abre la del plan nuevo (RF-SUS-02).

    Las dos filas se escriben juntas o no se escribe ninguna: a mitad de camino
    la licorera se quedaría con dos suscripciones abiertas o con ninguna, y la
    consulta que decide cuál manda devolvería cualquier cosa.
    """
    anterior = comprobar(licorera, destino)
    hoy = timezone.localdate()

    # La fecha de fin se guarda ANTES de cerrar la fila anterior: cerrarla es
    # precisamente sobrescribirla, y la nueva tiene que heredar la original.
    vence = anterior.fecha_fin

    # Cerrar una fila es acortarla, nunca alargarla. Una suscripción ya vencida
    # —la cuenta suspendida que se pasa al plan barato antes de ponerse al día—
    # conserva la fecha en que venció: ponerle la de hoy le regalaría los días
    # que estuvo sin servicio, y el historial diría que estuvo vigente.
    anterior.fecha_fin = hoy if vence is None else min(vence, hoy)
    anterior.save(update_fields=["fecha_fin"])

    nueva = Suscripcion(
        licorera=licorera,
        plan=destino,
        estado=Suscripcion.Estado.ACTIVA,
        fecha_inicio=hoy,
        fecha_fin=vence,
        precio_pactado=destino.precio_mensual,
    )
    # Si lo que se hereda es una fecha ya pasada —una cuenta suspendida que se
    # pasa al plan barato antes de ponerse al día—, la fila nace suspendida. Se
    # guarda ya calculado para que la columna no mienta hasta que corra la orden.
    nueva.estado = nueva.estado_por_fecha(hoy)
    nueva.save()
    return nueva


# ---------------------------------------------------------------------------
# Lo que ejecuta el Administrador INVENTRA (RF-SUS-01 y RF-SUS-05, D-25)
# ---------------------------------------------------------------------------

def _no_puede_ser_pasada(fecha_fin):
    """
    La fecha que escribe una persona nunca puede quedar en el pasado (D-25).

    El mínimo es hoy, así que lo más agresivo que puede hacer una corrección es
    dejar el vencimiento en hoy, nunca ayer: un negocio no puede quedarse sin
    acceso por un día que ya trabajó. No aplica cuando es el sistema el que
    cierra una fila al cambiar de plan; eso no lo escribe nadie a mano.
    """
    if fecha_fin is None:
        raise CambioNoPermitido("Indica hasta cuándo vale la suscripción.")
    if fecha_fin < timezone.localdate():
        raise CambioNoPermitido(
            "La fecha de vencimiento no puede quedar en el pasado. Lo más atrás "
            "que puede ponerse es hoy.")


@transaction.atomic
def abrir_periodo(licorera, plan, fecha_fin):
    """
    Abre un período contratado: renovar y subir de plan son la misma operación.

    Las dos cierran la suscripción vigente y abren otra con un plan y una fecha
    que pone el Administrador INVENTRA. La única diferencia es si el plan cambia,
    y eso no justifica dos caminos distintos que luego hay que mantener iguales.

    La fecha la escribe él y no se hereda, al revés que en la bajada: subir y
    renovar implican cobrar, y quien cobra sabe por cuánto tiempo se pagó. La
    bajada es la excepción, y lo es porque ahí no hay dinero de por medio.

    **Bajar de plan no se hace desde aquí.** El rechazo por exceso de usuarios o
    sedes tiene que salirle a quien puede decidir qué inactiva, y esa persona no
    está en INVENTRA (D-23).
    """
    _no_puede_ser_pasada(fecha_fin)
    if not plan.activo:
        raise CambioNoPermitido("El plan %s no está disponible." % plan.nombre)

    anterior = licorera.suscripcion_actual()
    if anterior is not None and es_bajada(anterior.plan, plan):
        raise CambioNoPermitido(
            "Bajar al plan %s lo hace el administrador de la licorera desde su "
            "cuenta: es quien puede decidir qué usuarios o sedes inactiva."
            % plan.nombre)

    # El exceso solo se comprueba cuando el plan CAMBIA. Renovar el mismo plan no
    # altera ningún límite, así que no hay nada que validar; comprobarlo igual
    # dejaba a una licorera que por lo que fuera excediera su propio plan sin
    # poder renovar —es decir, sin poder pagar—, y negarle el cobro no arregla el
    # exceso: lo congela. Lo encontró una prueba del aviso por correo, que se
    # quedó sin correo porque la renovación nunca llegó a ejecutarse.
    if anterior is None or anterior.plan_id != plan.id:
        sobra = excesos(licorera, plan)
        if sobra:
            raise CambioNoPermitido(
                "La licorera no cabe en el plan %s: %s" % (plan.nombre, " ".join(sobra)))

    hoy = timezone.localdate()
    if anterior is not None:
        vencia = anterior.fecha_fin
        anterior.fecha_fin = hoy if vencia is None else min(vencia, hoy)
        anterior.save(update_fields=["fecha_fin"])

    nueva = Suscripcion(
        licorera=licorera,
        plan=plan,
        estado=Suscripcion.Estado.ACTIVA,
        fecha_inicio=hoy,
        fecha_fin=fecha_fin,
        precio_pactado=plan.precio_mensual,
    )
    nueva.save()
    return nueva


@transaction.atomic
def corregir_vencimiento(licorera, fecha_fin):
    """
    Cambia la fecha de la suscripción vigente, sin abrir una fila nueva (D-25).

    Es el caso de haber escrito dos años donde eran dos meses. No es una
    renovación: no hay período nuevo, hay un dato mal puesto.

    Devuelve `(cambió, suscripción)`. El booleano existe para que la vista sepa
    si mandar el correo: guardar el formulario sin tocar la fecha no son dos
    correos, es ninguno.

    ESTE ES EL ÚNICO SITIO QUE PUEDE DEVOLVER UNA SUSCRIPCIÓN A LA VIDA, y por
    eso está separado de todo lo demás. Si alguien tecleó una fecha demasiado
    temprana y la cuenta quedó suspendida, corregirla tiene que arreglarlo —de
    nada sirve poder editar si el daño ya es irreversible—. Lo hace una persona
    a conciencia, que es la diferencia con la orden diaria: aquélla solo avanza
    precisamente porque no hay nadie mirando.
    """
    _no_puede_ser_pasada(fecha_fin)

    suscripcion = licorera.suscripcion_actual()
    if suscripcion is None:
        raise CambioNoPermitido("Esta licorera no tiene una suscripción que corregir.")

    if suscripcion.fecha_fin == fecha_fin:
        return False, suscripcion

    suscripcion.fecha_fin = fecha_fin
    if suscripcion.estado in (Suscripcion.Estado.EN_MORA, Suscripcion.Estado.SUSPENDIDA):
        suscripcion.estado = (Suscripcion.Estado.EN_PRUEBA
                              if suscripcion.es_periodo_gratuito
                              else Suscripcion.Estado.ACTIVA)
    suscripcion.estado = suscripcion.estado_por_fecha()
    suscripcion.save(update_fields=["fecha_fin", "estado"])
    return True, suscripcion

