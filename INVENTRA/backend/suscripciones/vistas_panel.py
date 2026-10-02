# -*- coding: utf-8 -*-
"""
Panel del Administrador INVENTRA (RF-SUS-05 y RF-SUS-01, decisión D-25).

Lo que el operador de la plataforma puede hacer: ver las licoreras con su plan y
su estado, darlas de alta con un plan contratado, abrir un período nuevo
—renovar o subir de plan, que son la misma operación— y corregir una fecha de
vencimiento mal escrita.

LO QUE NO PUEDE HACER, Y ESTÁ VIGILADO POR EL PROPIO DISEÑO DE ESTAS RESPUESTAS
Ver la información comercial de un negocio. El requisito lo prohíbe y la forma
de cumplirlo no es acordarse: es que estas vistas no consulten nada de eso. De
aquí salen nombre, contacto, plan, estado y número de cuentas; no hay ninguna
consulta a productos ni a ventas que alguien pueda ampliar por descuido.

Van en su propio archivo porque son otra audiencia: `views.py` es lo que usa un
negocio sobre sí mismo, y esto es lo que usa la plataforma sobre todos.
"""

import logging

from django.db.models import Prefetch
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from seguridad.permissions import EsAdministradorDeInventra

from .cambio_de_plan import CambioNoPermitido, abrir_periodo, corregir_vencimiento
from .correo import enviar_correo_alta, enviar_correo_vencimiento
from .models import Licorera, Plan, Suscripcion
from .serializers import AltaLicoreraSerializer, LicoreraDelPanelSerializer

panel_log = logging.getLogger(__name__)


def metricas():
    """
    Las cifras globales que pide RF-SUS-05.

    Se calculan recorriendo en Python y no con una suma en la base porque el
    estado que vale es el **calculado** a partir de la fecha, no el que tiene
    guardado la fila: una consulta que filtrara por la columna `estado` diría
    que hay cuentas activas la mañana en que la orden diaria no corrió. Con el
    número de licoreras de este sistema, la diferencia de velocidad no existe;
    la de exactitud, sí.
    """
    registradas = 0
    activas = 0
    ingresos = 0
    por_estado = {}

    for licorera in Licorera.objects.filter(activo=True).prefetch_related("suscripciones"):
        registradas += 1
        suscripcion = licorera.suscripcion_actual()
        if suscripcion is None:
            por_estado["sin_suscripcion"] = por_estado.get("sin_suscripcion", 0) + 1
            continue
        estado = suscripcion.estado_por_fecha()
        por_estado[estado] = por_estado.get(estado, 0) + 1
        if suscripcion.esta_vigente():
            activas += 1
            # La prueba no suma: su precio pactado es cero porque no se cobra, de
            # modo que no hace falta excluirla, pero se deja dicho para que nadie
            # «arregle» más adelante ese cero.
            ingresos += suscripcion.precio_pactado

    return {
        "licoreras_registradas": registradas,
        "cuentas_activas": activas,
        "ingresos_mensuales_recurrentes": ingresos,
        "por_estado": por_estado,
    }


class PanelView(APIView):
    """Las licoreras y las cifras globales de la plataforma (RF-SUS-05)."""

    permission_classes = [EsAdministradorDeInventra]

    def get(self, request):
        licoreras = (
            Licorera.objects
            .prefetch_related(
                Prefetch("suscripciones",
                         queryset=Suscripcion.objects.select_related("plan")),
                "usuarios",
            )
            .order_by("nombre")
        )
        return Response({
            "metricas": metricas(),
            "licoreras": LicoreraDelPanelSerializer(licoreras, many=True).data,
        })


class AltaLicoreraView(APIView):
    """Alta directa de una licorera con su plan contratado (RF-SUS-01)."""

    permission_classes = [EsAdministradorDeInventra]

    def post(self, request):
        serializador = AltaLicoreraSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)
        creado = serializador.save()

        # Fuera de la transacción, igual que en el registro por autoservicio: la
        # licorera ya existe y el dueño puede pedir otro enlace desde la pantalla
        # de acceso. Lo que no puede pasar es que un servidor de correo caído
        # impida dar de alta a un cliente.
        try:
            enviar_correo_alta(creado["usuario"])
        except Exception:
            panel_log.exception("No se pudo enviar el correo de alta")

        return Response(
            LicoreraDelPanelSerializer(creado["licorera"]).data,
            status=status.HTTP_201_CREATED,
        )


class SuscripcionDeLicoreraView(APIView):
    """
    Las dos operaciones sobre la vigencia de una licorera (decisión D-25).

        POST   abre un período nuevo: renovar, o subir de plan.
        PATCH  corrige la fecha de la suscripción vigente.

    Las dos avisan por correo al administrador de la licorera, y las dos son el
    **único** sitio donde se escribe una fecha de vencimiento. De eso depende que
    la orden diaria no pueda mandar correos: no pasa por aquí.
    """

    permission_classes = [EsAdministradorDeInventra]

    def _licorera(self, id_licorera):
        return Licorera.objects.filter(id=id_licorera).first()

    def post(self, request, id_licorera):
        licorera = self._licorera(id_licorera)
        if licorera is None:
            return Response({"detalle": "Esa licorera no existe."},
                            status=status.HTTP_404_NOT_FOUND)

        plan = Plan.objects.filter(id=request.data.get("plan")).first()
        if plan is None:
            return Response({"detalle": "Elige un plan."},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            suscripcion = abrir_periodo(licorera, plan, _fecha(request.data.get("fecha_fin")))
        except CambioNoPermitido as motivo:
            return Response({"detalle": str(motivo)}, status=status.HTTP_409_CONFLICT)

        self._avisar(licorera, suscripcion)
        return Response(LicoreraDelPanelSerializer(licorera).data,
                        status=status.HTTP_201_CREATED)

    def patch(self, request, id_licorera):
        licorera = self._licorera(id_licorera)
        if licorera is None:
            return Response({"detalle": "Esa licorera no existe."},
                            status=status.HTTP_404_NOT_FOUND)

        try:
            cambio, suscripcion = corregir_vencimiento(
                licorera, _fecha(request.data.get("fecha_fin")))
        except CambioNoPermitido as motivo:
            return Response({"detalle": str(motivo)}, status=status.HTTP_409_CONFLICT)

        # Guardar sin haber tocado la fecha no es un cambio, y avisar de algo que
        # no pasó enseña a no leer los avisos.
        if cambio:
            self._avisar(licorera, suscripcion)

        licorera._actual = suscripcion
        return Response(LicoreraDelPanelSerializer(licorera).data)

    def _avisar(self, licorera, suscripcion):
        try:
            enviar_correo_vencimiento(licorera, suscripcion)
        except Exception:
            panel_log.exception("No se pudo enviar el aviso de vencimiento")


def _fecha(valor):
    """
    Convierte lo que llegó en la petición a fecha, o devuelve None.

    Un texto mal escrito no se distingue aquí de un campo vacío a propósito: los
    dos acaban en el mismo mensaje del servicio, «indica hasta cuándo vale», que
    es lo que la persona necesita leer en los dos casos.
    """
    from datetime import date

    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor))
    except (TypeError, ValueError):
        return None
