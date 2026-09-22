"""
Vistas del módulo de seguridad.

Una vista recibe la petición que llega por una dirección de la API, decide qué
hacer con ella y devuelve la respuesta.
"""

import logging

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .correo import enviar_correo_recuperacion
from .models import Rol, Usuario
from .permissions import EsAdministradorDeLicorera
from .serializers import (
    CambiarContrasenaSerializer,
    CierreSesionSerializer,
    InicioSesionSerializer,
    PerfilActualizarSerializer,
    RenovacionSerializer,
    RestablecerContrasenaSerializer,
    RolSerializer,
    SolicitarRecuperacionSerializer,
    UsuarioActualizarSerializer,
    UsuarioCrearSerializer,
    UsuarioSerializer,
)

registro = logging.getLogger(__name__)


class InicioSesionView(TokenObtainPairView):
    """
    Inicio de sesión (RF-SEG-02).

    Recibe correo y contraseña; si son correctos devuelve el token de acceso, el
    de refresco y los datos del usuario. No exige autenticación previa, por
    razones obvias.
    """

    permission_classes = [AllowAny]
    serializer_class = InicioSesionSerializer

    # Límite de peticiones por origen (D-11). Es distinto del bloqueo de cinco
    # intentos: aquel es POR CUENTA, y no impide probar una misma contraseña
    # contra miles de correos sin bloquear ninguna. Este cuenta por origen.
    throttle_scope = "ingreso"


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


class RenovacionView(APIView):
    """
    Entrega un token de acceso nuevo a partir del de refresco (RF-SEG-02).

    No exige sesión, y tiene que ser así: quien la llama es justamente alguien
    cuyo token de acceso venció. Lo que hace de credencial es el refresco.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializador = RenovacionSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)
        return Response(serializador.validated_data, status=status.HTTP_200_OK)


class PerfilView(APIView):
    """
    Perfil del usuario que tiene la sesión abierta (RF-SEG-06).

    El frontend la consulta al arrancar para saber quién entró, con qué rol y a
    qué licorera pertenece, y la usa también para que cada quien corrija sus
    propios datos.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UsuarioSerializer(request.user).data)

    def patch(self, request):
        """
        Actualización parcial: solo llegan los campos que cambiaron.

        No hace falta comprobar de quién es el perfil: se toma siempre del usuario
        de la petición, así que nadie puede editar el de otra persona aunque envíe
        un identificador ajeno.
        """
        serializador = PerfilActualizarSerializer(
            request.user, data=request.data, partial=True
        )
        serializador.is_valid(raise_exception=True)
        serializador.save()
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


class CambiarContrasenaView(APIView):
    """Cambio de contraseña con la sesión abierta (RF-SEG-06)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializador = CambiarContrasenaSerializer(
            data=request.data, context={"request": request}
        )
        serializador.is_valid(raise_exception=True)
        serializador.guardar()
        return Response(
            {"detalle": "Contraseña actualizada. Vuelve a ingresar con la nueva."},
            status=status.HTTP_200_OK,
        )


class SolicitarRecuperacionView(APIView):
    """
    Solicitud del enlace de recuperación (RF-SEG-04).

    Responde siempre lo mismo, exista o no la cuenta. Si el mensaje cambiara según
    el caso, cualquiera podría averiguar qué correos están registrados enviando
    direcciones al azar y mirando la respuesta.
    """

    permission_classes = [AllowAny]
    # Sin límite, esta dirección sirve para bombardear de correos a un tercero.
    throttle_scope = "recuperacion"

    RESPUESTA = {
        "detalle": (
            "Si el correo corresponde a una cuenta registrada, "
            "enviamos un enlace para restablecer la contraseña."
        )
    }

    def post(self, request):
        serializador = SolicitarRecuperacionSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)

        usuario = Usuario.objects.filter(
            correo=serializador.validated_data["correo"], activo=True
        ).first()

        if usuario is not None:
            try:
                enviar_correo_recuperacion(usuario)
            except Exception:
                # Un fallo del servicio de correo no debe revelarle nada al cliente
                # ni tumbar la petición: queda en el registro del servidor.
                registro.exception("No se pudo enviar el correo de recuperación")

        return Response(self.RESPUESTA, status=status.HTTP_200_OK)


class RestablecerContrasenaView(APIView):
    """
    Definición de la contraseña nueva desde el enlace recibido (RF-SEG-04).

    Es pública por necesidad: quien la usa no puede iniciar sesión, que es
    precisamente el problema que viene a resolver. Lo que hace las veces de
    credencial es el token del enlace.
    """

    permission_classes = [AllowAny]
    throttle_scope = "restablecimiento"

    def post(self, request):
        serializador = RestablecerContrasenaSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)
        serializador.guardar()
        return Response(
            {"detalle": "Contraseña actualizada. Ya puedes ingresar con la nueva."},
            status=status.HTTP_200_OK,
        )
