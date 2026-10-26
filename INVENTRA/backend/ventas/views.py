"""
Direcciones del módulo de ventas.

El reparto por rol se invierte respecto a INV, y es la primera vez que ocurre:
**vender es del vendedor**. Lo que sigue siendo del administrador es deshacer
—anular una venta—, porque quien cobra no debería poder borrar su propio cobro.

Como en INV, las vistas traducen peticiones y no deciden nada: la regla vive en
`operaciones.py` y en `caja.py`, que son las que llaman también los datos de
demostración.
"""

from django.core.exceptions import ValidationError as ErrorDeValidacion
from django.utils.dateparse import parse_date
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from seguridad.permissions import EsAdministradorDeLicorera
from suscripciones.permissions import PuedeRegistrarOperaciones

from .caja import (cerrar_jornada, explicar_diferencia, jornadas_sin_cerrar,
                   jornadas_sin_explicar, resumen_de, ultimos_cierres)
from .consultas import de_la_jornada, filtrar, resumen, utilidad_del_mes
from .jornada import jornada_actual
from .models import CierreCaja, MedioPago
from .operaciones import anular_venta, registrar_venta
from .serializers import (AnulacionSerializer, CierreCrearSerializer,
                          CierreSerializer, ExplicacionSerializer,
                          MedioPagoSerializer, VentaCrearSerializer,
                          VentaDeLaListaSerializer, VentaSerializer)
from django.db.models import Sum

from seguridad.models import Rol
from sedes.models import Sede


def rechazo(error):
    """Un dato rechazado es un 400, no un fallo del servidor."""
    return Response({"detalle": "; ".join(error.messages)},
                    status=status.HTTP_400_BAD_REQUEST)


class MediosDePagoView(ListAPIView):
    """Los medios que ofrece el punto de venta (RF-VEN-02)."""

    serializer_class = MedioPagoSerializer
    pagination_class = None

    def get_queryset(self):
        return MedioPago.objects.filter(activo=True)


class VentaViewSet(mixins.ListModelMixin,
                   mixins.RetrieveModelMixin,
                   viewsets.GenericViewSet):
    """Registrar, consultar y anular ventas (RF-VEN-01 a 05)."""

    def get_permissions(self):
        permisos = list(self.permission_classes)
        if self.action in ("create", "anular"):
            permisos += [PuedeRegistrarOperaciones]
        if self.action == "anular":
            permisos += [EsAdministradorDeLicorera]
        return [permiso() for permiso in permisos]

    def get_serializer_class(self):
        return VentaDeLaListaSerializer if self.action == "list" else VentaSerializer

    def get_queryset(self):
        """El historial con los filtros de RF-VEN-05, siempre de la propia licorera."""
        parametros = self.request.query_params

        def fecha(nombre):
            valor = parametros.get(nombre)
            return valor or None

        consulta = filtrar(
            self.request.user.licorera,
            desde=fecha("desde"), hasta=fecha("hasta"),
            vendedor=parametros.get("vendedor") or None,
            producto=parametros.get("producto") or None,
            medio_pago=parametros.get("medio_pago") or None,
            buscar=parametros.get("buscar"),
        )
        return consulta.order_by("-fecha", "-id")

    def list(self, request, *args, **kwargs):
        """
        La página de resultados y, con ella, los totales del período.

        Van en la misma respuesta y no en una dirección aparte porque los dos
        salen de la misma consulta filtrada: separarlos admitiría que la tabla
        y los indicadores llegaran de dos momentos distintos y dijeran cosas
        que no concuerdan.
        """
        consulta = self.filter_queryset(self.get_queryset())
        pagina = self.paginate_queryset(consulta)
        datos = self.get_serializer(
            pagina if pagina is not None else consulta, many=True).data

        if pagina is None:
            return Response({"results": datos, "resumen": resumen(consulta)})

        respuesta = self.get_paginated_response(datos)
        respuesta.data["resumen"] = resumen(consulta)
        return respuesta

    def create(self, request):
        """Cobra una venta y descuenta el inventario."""
        serializador = VentaCrearSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)
        licorera = request.user.licorera

        medio = MedioPago.objects.filter(
            id=serializador.validated_data["medio_pago_id"], activo=True).first()
        if medio is None:
            return Response({"detalle": "Ese medio de pago no está disponible."},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            venta = registrar_venta(
                licorera=licorera, usuario=request.user,
                lineas=serializador.productos(licorera), medio_pago=medio,
                monto_recibido=serializador.validated_data.get("monto_recibido"),
                observacion=serializador.validated_data.get("observacion"),
            )
        except ErrorDeValidacion as error:
            return rechazo(error)

        return Response(VentaSerializer(venta).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def anular(self, request, pk=None):
        """Deshace una venta de la jornada en curso (RF-VEN-04)."""
        serializador = AnulacionSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)

        try:
            venta = anular_venta(venta=self.get_object(), usuario=request.user,
                                 motivo=serializador.validated_data["motivo"])
        except ErrorDeValidacion as error:
            return rechazo(error)

        return Response(VentaSerializer(venta).data, status=status.HTTP_200_OK)


class CierreDeCajaView(APIView):
    """
    El cierre de la jornada en curso (RF-VEN-06).

    Un GET devuelve lo que dice el sistema antes de contar, y el cierre de hoy
    si ya se hizo; un POST lo guarda o lo rehace.

    El GET admite una jornada en la dirección, que es por donde se llega desde
    el aviso del panel a una caja que cerró descuadrada hace días. Se lee, no
    se cierra: el POST sigue siendo solo de la jornada en curso, porque rehacer
    una anterior sería contar un cajón que ya se vació.
    """

    def get_permissions(self):
        permisos = list(self.permission_classes)
        if self.request.method == "POST":
            permisos += [PuedeRegistrarOperaciones]
            # Cerrar la caja del turno es de quien lo termina; cerrar tarde
            # una jornada que quedó sin cerrar es decidir una cifra que ya
            # nadie puede contar, y eso se reserva a quien administra.
            if self.request.data.get("jornada"):
                permisos += [EsAdministradorDeLicorera]
        return [permiso() for permiso in permisos]

    def get(self, request):
        licorera = request.user.licorera
        sede = Sede.principal_de(licorera)

        jornada = jornada_actual()
        pedida = parse_date(request.query_params.get("jornada") or "")
        # Una fecha ilegible no es motivo para no abrir la pantalla: se enseña
        # la jornada en curso, que es lo que se pedía sin parámetro.
        if pedida is not None:
            jornada = pedida
        cierre = CierreCaja.objects.filter(sede=sede, fecha=jornada).first()

        resumen = resumen_de(licorera, sede, jornada)
        return Response({
            "jornada": jornada,
            "en_curso": jornada == jornada_actual(),
            "transacciones": resumen["transacciones"],
            "total_efectivo": resumen["efectivo"],
            "total_transferencia": resumen["transferencia"],
            "total_tarjeta": resumen["tarjeta"],
            "cierre": CierreSerializer(cierre).data if cierre else None,
            # La historia del módulo, que RF-VEN-06 pide dejar registrada: un
            # registro al que no se puede llegar no es un registro. Sin la
            # jornada que se está mirando, que ya está arriba.
            "anteriores": CierreSerializer(
                ultimos_cierres(licorera, excepto=jornada), many=True).data,
        })

    def post(self, request):
        serializador = CierreCrearSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)

        try:
            cierre, creado = cerrar_jornada(
                licorera=request.user.licorera, usuario=request.user,
                efectivo_contado=serializador.validated_data["efectivo_contado"],
                jornada=serializador.validated_data.get("jornada"),
                observacion=serializador.validated_data.get("observacion"),
            )
        except ErrorDeValidacion as error:
            return rechazo(error)

        return Response(CierreSerializer(cierre).data,
                        status=status.HTTP_201_CREATED if creado else status.HTTP_200_OK)


class ExplicacionDelCierreView(APIView):
    """
    Escribe o corrige la explicación de una diferencia.

    Vive aparte del cierre porque se puede hacer mucho después, cuando la
    jornada ya terminó: es una nota y no una cifra.
    """

    def get_permissions(self):
        return [permiso() for permiso in list(self.permission_classes)
                + [EsAdministradorDeLicorera, PuedeRegistrarOperaciones]]

    def patch(self, request, pk):
        cierre = CierreCaja.objects.filter(
            pk=pk, licorera=request.user.licorera).first()
        if cierre is None:
            return Response({"detalle": "Ese cierre no existe."},
                            status=status.HTTP_404_NOT_FOUND)

        serializador = ExplicacionSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)

        try:
            explicar_diferencia(cierre=cierre,
                                texto=serializador.validated_data["observacion"])
        except ErrorDeValidacion as error:
            return rechazo(error)

        return Response(CierreSerializer(cierre).data, status=status.HTTP_200_OK)


class ResumenDeVentasView(APIView):
    """
    Lo que el panel principal enseña de las ventas.

    Tres cosas en una respuesta: lo vendido en la jornada en curso, la utilidad
    del mes y las jornadas que cerraron descuadradas y sin explicar. Van juntas
    por lo mismo que el resumen del inventario: se pintan juntas, y tres
    peticiones para una fila de tarjetas son tres ocasiones de que llegue media.

    El aviso de las jornadas sin explicar solo se le da a quien administra. Un
    vendedor no puede escribir la explicación —esa es la mitad de la razón por
    la que el aviso existe—, de modo que enseñárselo sería ponerle delante algo
    que no puede resolver.
    """

    def get(self, request):
        licorera = request.user.licorera
        sede = Sede.principal_de(licorera)
        jornada = jornada_actual()

        del_dia = de_la_jornada(licorera, sede, jornada)
        mes = utilidad_del_mes(licorera, jornada)

        sin_explicar = []
        sin_cerrar = []
        if request.user.rol.nombre == Rol.ADMINISTRADOR_LICORERA:
            sin_explicar = [
                {"id": c.id, "fecha": c.fecha, "sede_nombre": c.sede.nombre,
                 "diferencia": c.diferencia}
                for c in jornadas_sin_explicar(licorera)
            ]
            # Una noche que nadie contó no deja fila en el cierre, de modo que
            # el aviso anterior no la ve. Esta es la única forma que tiene el
            # sistema de decir que no se contó.
            sin_cerrar = jornadas_sin_cerrar(licorera, sede)

        return Response({
            "jornada": jornada,
            "vendido_en_la_jornada": del_dia.aggregate(t=Sum("total"))["t"] or 0,
            "transacciones_de_la_jornada": del_dia.count(),
            "utilidad_del_mes": mes["utilidad"],
            "vendido_en_el_mes": mes["vendido"],
            "jornadas_sin_explicar": sin_explicar,
            "jornadas_sin_cerrar": sin_cerrar,
        })
