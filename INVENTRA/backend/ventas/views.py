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
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from seguridad.permissions import EsAdministradorDeLicorera
from suscripciones.permissions import PuedeRegistrarOperaciones

from .caja import cerrar_jornada, explicar_diferencia, resumen_de
from .consultas import filtrar
from .jornada import jornada_actual
from .models import CierreCaja, MedioPago
from .operaciones import anular_venta, registrar_venta
from .serializers import (AnulacionSerializer, CierreCrearSerializer,
                          CierreSerializer, ExplicacionSerializer,
                          MedioPagoSerializer, VentaCrearSerializer,
                          VentaDeLaListaSerializer, VentaSerializer)
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
    """

    def get_permissions(self):
        permisos = list(self.permission_classes)
        if self.request.method == "POST":
            permisos += [PuedeRegistrarOperaciones]
        return [permiso() for permiso in permisos]

    def get(self, request):
        licorera = request.user.licorera
        sede = Sede.principal_de(licorera)
        jornada = jornada_actual()
        cierre = CierreCaja.objects.filter(sede=sede, fecha=jornada).first()

        resumen = resumen_de(licorera, sede, jornada)
        return Response({
            "jornada": jornada,
            "transacciones": resumen["transacciones"],
            "total_efectivo": resumen["efectivo"],
            "total_transferencia": resumen["transferencia"],
            "total_tarjeta": resumen["tarjeta"],
            "cierre": CierreSerializer(cierre).data if cierre else None,
        })

    def post(self, request):
        serializador = CierreCrearSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)

        try:
            cierre, creado = cerrar_jornada(
                licorera=request.user.licorera, usuario=request.user,
                efectivo_contado=serializador.validated_data["efectivo_contado"],
                observacion=serializador.validated_data.get("observacion"),
            )
        except ErrorDeValidacion as error:
            return rechazo(error)

        return Response(CierreSerializer(cierre).data,
                        status=status.HTTP_201_CREATED if creado else status.HTTP_200_OK)


class ExplicacionDelCierreView(APIView):
    """
    Escribe o corrige la explicación de una diferencia (D-37).

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
