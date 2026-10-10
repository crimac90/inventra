"""
Vistas del catálogo (RF-INV-01 a 04).

El permiso de escritura es el mismo que estrenó SUS: `PuedeRegistrarOperaciones`
deja consultar siempre y solo deja registrar con el correo confirmado y la
suscripción vigente (D-29). Se engancha con una línea, y por eso la regla no hay
que volver a escribirla aquí.
"""

from django.core.exceptions import ValidationError as ErrorDeValidacion
from django.db.models import F, Q
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import ListAPIView
from rest_framework.response import Response

from seguridad.permissions import EsAdministradorDeLicorera
from suscripciones.permissions import PuedeRegistrarOperaciones

from .existencias import con_existencias
from .models import Categoria, EntradaMercancia, MovimientoInventario, Producto
from .operaciones import ajustar_existencias, registrar_entrada
from .serializers import (
    AjusteSerializer, CategoriaSerializer, EntradaCrearSerializer,
    EntradaSerializer, MovimientoSerializer, ProductoGuardarSerializer,
    ProductoSerializer)


class CategoriasView(ListAPIView):
    """
    Las categorías de la licorera, para el desplegable del formulario.

    Solo se listan: no hay pantalla de categorías ni requisito que permita
    crearlas o editarlas. Se siembran al registrar el negocio.
    """

    serializer_class = CategoriaSerializer
    pagination_class = None

    def get_queryset(self):
        return Categoria.objects.filter(
            licorera=self.request.user.licorera, activo=True).order_by("id")


class ProductoViewSet(viewsets.ModelViewSet):
    """
    Catálogo de productos (RF-INV-01, 02, 03 y 04).

    Consultar lo puede hacer cualquiera con sesión en la licorera —el vendedor
    necesita ver el catálogo—; registrar y modificar, solo el administrador.
    """

    serializer_class = ProductoSerializer

    def get_permissions(self):
        """
        Consultar y registrar no exigen lo mismo.

        Leer el catálogo lo necesita también el vendedor, así que basta con
        tener sesión. Registrar y modificar son del administrador, y además
        pasan por el permiso de escritura de SUS, que mira el correo y la
        suscripción (D-29). Se añade `list(...)` a propósito: la lista que
        viene de la configuración no es siempre del mismo tipo, y concatenar
        una tupla con una lista falla.
        """
        permisos = list(self.permission_classes)
        if self.request.method not in ("GET", "HEAD", "OPTIONS"):
            permisos += [EsAdministradorDeLicorera, PuedeRegistrarOperaciones]
        return [permiso() for permiso in permisos]

    def get_queryset(self):
        """
        Aislamiento entre negocios y los filtros de RF-INV-02.

        El filtro por nivel de existencias llega con los lotes, en el bloque 4:
        hoy no hay de dónde sacar la existencia, y un filtro que no filtra sería
        peor que no tenerlo.
        """
        # El `order_by` es explícito y no heredado del modelo a propósito: al
        # agrupar para sumar los lotes, Django deja de considerar ordenada la
        # consulta aunque el modelo declare su orden, y la paginación avisa de
        # que las páginas podrían salir barajadas.
        consulta = con_existencias(
            Producto.objects
            .filter(licorera=self.request.user.licorera)
            .select_related("categoria")
        ).order_by("nombre")

        parametros = self.request.query_params

        buscar = (parametros.get("buscar") or "").strip()
        if buscar:
            # Las tres formas que pide el requisito: nombre, categoría o código.
            consulta = consulta.filter(
                Q(nombre__icontains=buscar)
                | Q(categoria__nombre__icontains=buscar)
                | Q(codigo_barras__icontains=buscar)
            )

        categoria = parametros.get("categoria")
        if categoria:
            consulta = consulta.filter(categoria_id=categoria)

        estado = parametros.get("estado")
        if estado in ("activo", "inactivo"):
            consulta = consulta.filter(activo=(estado == "activo"))

        # Los dos filtros rápidos que dibuja el prototipo sobre la tabla. Se
        # separan «agotado» de «bajo» a propósito: agotado es cero, y bajo es
        # «queda algo, pero igual o menos que el mínimo». Mezclarlos escondería
        # lo urgente —lo que ya no se puede vender— entre lo que solo hay que
        # reponer.
        nivel = parametros.get("existencias")
        if nivel == "agotado":
            consulta = consulta.filter(disponibles=0)
        elif nivel == "bajo":
            consulta = consulta.filter(disponibles__gt=0,
                                       disponibles__lte=F("stock_minimo"))

        return consulta

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return ProductoGuardarSerializer
        return ProductoSerializer

    def get_serializer_context(self):
        """
        La licorera sale de la sesión, nunca de la petición.

        Las existencias ya no viajan por aquí: vienen calculadas dentro de la
        propia consulta (`con_existencias`), que es una sola para toda la lista.
        """
        contexto = super().get_serializer_context()
        contexto["licorera"] = self.request.user.licorera
        return contexto

    def create(self, request, *args, **kwargs):
        serializador = self.get_serializer(data=request.data)
        serializador.is_valid(raise_exception=True)
        producto = serializador.save()
        return Response(ProductoSerializer(producto).data,
                        status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        producto = self.get_object()
        serializador = self.get_serializer(
            producto, data=request.data, partial=kwargs.pop("partial", False))
        serializador.is_valid(raise_exception=True)
        serializador.save()
        return Response(ProductoSerializer(producto).data)

    @action(detail=True, methods=["get"])
    def kardex(self, request, pk=None):
        """
        El historial de movimientos de una referencia (RF-INV-09).

        Va aquí, colgando del producto, y no como una dirección suelta: el
        kardex no se consulta en abstracto, se consulta de algo. Es de solo
        lectura para todos, incluido el administrador: un kardex que se puede
        editar no sirve para rendir cuentas de nada.
        """
        producto = self.get_object()
        movimientos = (
            MovimientoInventario.objects
            .filter(producto=producto)
            .select_related("usuario")
        )
        pagina = self.paginate_queryset(movimientos)
        serializador = MovimientoSerializer(pagina, many=True)
        return self.get_paginated_response(serializador.data)

    @action(detail=True, methods=["post"])
    def ajustar(self, request, pk=None):
        """
        Corrige las existencias de una referencia (RF-INV-06).

        Cuelga del producto, como el kardex: un ajuste no existe en abstracto.
        """
        producto = self.get_object()
        serializador = AjusteSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)

        try:
            ajustar_existencias(
                producto=producto, usuario=request.user,
                cantidad=serializador.validated_data["cantidad"],
                motivo=serializador.validated_data["motivo"],
            )
        except ErrorDeValidacion as error:
            return Response({"detalle": "; ".join(error.messages)},
                            status=status.HTTP_400_BAD_REQUEST)

        producto.refresh_from_db()
        return Response(ProductoSerializer(producto).data, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        """
        Baja lógica (RF-INV-04).

        Un producto descontinuado no se borra: desaparece del punto de venta y
        conserva su historial en el kardex y en los reportes. Borrarlo dejaría
        ventas apuntando a una referencia que ya no existe.
        """
        producto = self.get_object()
        producto.activo = False
        producto.save(update_fields=["activo"])
        return Response({"detalle": "Producto inactivado."}, status=status.HTTP_200_OK)


class EntradaMercanciaViewSet(mixins.CreateModelMixin,
                              mixins.ListModelMixin,
                              mixins.RetrieveModelMixin,
                              viewsets.GenericViewSet):
    """
    Entradas de mercancía (RF-INV-05).

    NO HAY EDITAR NI BORRAR, y es a propósito. Una entrada ya registrada movió
    existencias y dejó su rastro en el kardex; cambiarla a posteriori haría que
    el saldo guardado de los movimientos posteriores dejara de cuadrar. Lo que
    corrige una entrada equivocada es un ajuste con su motivo (RF-INV-06), que
    es lo que hace un sistema de inventario serio y lo que deja ver qué pasó.
    """

    serializer_class = EntradaSerializer

    def get_permissions(self):
        permisos = list(self.permission_classes)
        if self.request.method not in ("GET", "HEAD", "OPTIONS"):
            permisos += [EsAdministradorDeLicorera, PuedeRegistrarOperaciones]
        return [permiso() for permiso in permisos]

    def get_queryset(self):
        return (
            EntradaMercancia.objects
            .filter(licorera=self.request.user.licorera)
            .select_related("usuario")
            .prefetch_related("lotes__producto")
        )

    def get_serializer_context(self):
        contexto = super().get_serializer_context()
        contexto["licorera"] = self.request.user.licorera
        return contexto

    def create(self, request, *args, **kwargs):
        serializador = EntradaCrearSerializer(data=request.data,
                                              context=self.get_serializer_context())
        serializador.is_valid(raise_exception=True)
        datos = serializador.validated_data

        try:
            entrada = registrar_entrada(
                licorera=request.user.licorera,
                usuario=request.user,
                lineas=datos["lineas"],
                proveedor=datos.get("proveedor"),
                observacion=datos.get("observacion"),
            )
        except ErrorDeValidacion as error:
            # Las reglas que vigila la operación —sede inexistente, producto
            # ajeno, cantidad o costo imposibles— se devuelven como lo que son:
            # datos rechazados, no un fallo del servidor.
            return Response({"detalle": "; ".join(error.messages)},
                            status=status.HTTP_400_BAD_REQUEST)

        return Response(EntradaSerializer(entrada).data, status=status.HTTP_201_CREATED)


class AlertasDeInventarioView(ListAPIView):
    """
    Las referencias que hay que reponer (RF-INV-07).

    El requisito pide una alerta «cuando la existencia sea igual o inferior a
    su mínimo configurado», así que incluye las agotadas: una referencia en
    cero es el caso más urgente del mismo problema, no uno distinto.

    Solo mira productos activos: avisar de que hay que reponer una referencia
    descontinuada sería ruido, y el ruido es lo que hace que una alerta se
    deje de leer.
    """

    serializer_class = ProductoSerializer
    pagination_class = None

    def get_queryset(self):
        return (
            con_existencias(
                Producto.objects
                .filter(licorera=self.request.user.licorera, activo=True)
                .select_related("categoria")
            )
            .filter(disponibles__lte=F("stock_minimo"))
            .order_by("disponibles", "nombre")
        )
