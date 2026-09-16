"""
Vistas del módulo de seguridad.

Una vista recibe la petición que llega por una dirección de la API, decide qué
hacer con ella y devuelve la respuesta.
"""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import Rol, Usuario
from .permissions import EsAdministradorDeLicorera
from .serializers import (
    CierreSesionSerializer,
    InicioSesionSerializer,
    RolSerializer,
    UsuarioActualizarSerializer,
    UsuarioCrearSerializer,
    UsuarioSerializer,
)


class InicioSesionView(TokenObtainPairView):
    """
    Inicio de sesión (RF-SEG-02).

    Recibe correo y contraseña; si son correctos devuelve el token de acceso, el
    de refresco y los datos del usuario. No exige autenticación previa, por
    razones obvias.
    """

    permission_classes = [AllowAny]
    serializer_class = InicioSesionSerializer


class CierreSesionView(APIView):
    """
    Cierre de sesión (RF-SEG-03).

    Con autenticación por token no existe una sesión en el servidor que se pueda
    destruir: lo que se hace es invalidar el token de refresco, de modo que la
    sesión no se pueda renovar. El token de acceso que ya tenga el usuario deja
    de servir cuando vence.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializador = CierreSesionSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)
        serializador.guardar()
        return Response({"detalle": "Sesión cerrada."}, status=status.HTTP_200_OK)


class PerfilView(APIView):
    """
    Datos del usuario que tiene la sesión abierta.

    El frontend la consulta al arrancar para saber quién entró, con qué rol y a
    qué licorera pertenece.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UsuarioSerializer(request.user).data)


class RolesView(APIView):
    """Catálogo de roles asignables dentro de una licorera (RF-SEG-05)."""

    permission_classes = [EsAdministradorDeLicorera]

    def get(self, request):
        roles = Rol.objects.exclude(nombre=Rol.ADMINISTRADOR_INVENTRA)
        return Response(RolSerializer(roles, many=True).data)


class UsuarioViewSet(viewsets.ModelViewSet):
    """
    Gestión de los usuarios de una licorera (RF-SEG-01, 05, 06 y 07).

    Un conjunto de vistas agrupa en una sola clase las operaciones habituales
    sobre un recurso: listar, consultar, crear, modificar y dar de baja.
    """

    permission_classes = [EsAdministradorDeLicorera]

    def get_queryset(self):
        """
        Aislamiento entre negocios: la consulta se limita siempre a la licorera
        del usuario que pide. No es un filtro opcional que la vista pueda
        olvidar; es el único conjunto de datos que existe para esta petición.
        """
        return (
            Usuario.objects
            .filter(licorera=self.request.user.licorera)
            .select_related("rol", "licorera")
            .order_by("nombre_completo")
        )

    def get_serializer_class(self):
        if self.action == "create":
            return UsuarioCrearSerializer
        if self.action in ("update", "partial_update"):
            return UsuarioActualizarSerializer
        return UsuarioSerializer

    def create(self, request, *args, **kwargs):
        """Antes de crear, comprueba que el plan contratado admita un usuario más."""
        if not request.user.licorera.puede_agregar_usuario():
            plan = request.user.licorera.plan_vigente()
            return Response(
                {
                    "detalle": (
                        f"El plan {plan.nombre} permite {plan.maximo_usuarios} usuario(s). "
                        "Para agregar más, cambia de plan."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )
        return super().create(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """
        Baja lógica (RF-SEG-07).

        Los usuarios no se borran: se marcan como inactivos. Sus ventas, sus
        movimientos de inventario y su rastro en la auditoría deben seguir
        existiendo y siendo atribuibles.
        """
        usuario = self.get_object()

        if usuario.id == request.user.id:
            return Response(
                {"detalle": "No puedes inactivar tu propia cuenta."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        usuario.activo = False
        usuario.save(update_fields=["activo"])
        return Response(
            {"detalle": "Usuario inactivado."},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"])
    def reactivar(self, request, pk=None):
        """Vuelve a habilitar una cuenta dada de baja, si el plan lo permite."""
        usuario = self.get_object()

        if not request.user.licorera.puede_agregar_usuario():
            return Response(
                {"detalle": "El plan contratado no admite más usuarios activos."},
                status=status.HTTP_409_CONFLICT,
            )

        usuario.activo = True
        usuario.intentos_fallidos = 0
        usuario.bloqueado_hasta = None
        usuario.save(update_fields=["activo", "intentos_fallidos", "bloqueado_hasta"])
        return Response(UsuarioSerializer(usuario).data, status=status.HTTP_200_OK)
