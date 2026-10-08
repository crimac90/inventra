"""
Vistas del catálogo (RF-INV-01 a 04).

El permiso de escritura es el mismo que estrenó SUS: `PuedeRegistrarOperaciones`
deja consultar siempre y solo deja registrar con el correo confirmado y la
suscripción vigente (D-29). Se engancha con una línea, y por eso la regla no hay
que volver a escribirla aquí.
"""

from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.generics import ListAPIView
from rest_framework.response import Response

from seguridad.permissions import EsAdministradorDeLicorera
from suscripciones.permissions import PuedeRegistrarOperaciones

from .models import Categoria, Producto
from .serializers import CategoriaSerializer, ProductoGuardarSerializer, ProductoSerializer


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
        consulta = (
            Producto.objects
            .filter(licorera=self.request.user.licorera)
            .select_related("categoria")
        )

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

        return consulta

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return ProductoGuardarSerializer
        return ProductoSerializer

    def get_serializer_context(self):
        """La licorera sale de la sesión, nunca de la petición."""
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
