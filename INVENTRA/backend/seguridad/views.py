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

from suscripciones.permissions import PuedeRegistrarOperaciones

from .correo import enviar_correo_recuperacion, enviar_correo_verificacion
from .models import Rol, Usuario
from .permissions import EsAdministradorDeLicorera
from .serializers import (
    CambiarContrasenaSerializer, CierreSesionSerializer,
    CorregirCorreoSerializer, InicioSesionSerializer,
    PerfilActualizarSerializer, RenovacionSerializer,
    RestablecerContrasenaSerializer, RolSerializer,
    SolicitarRecuperacionSerializer, UsuarioActualizarSerializer,
    UsuarioCrearSerializer, UsuarioSerializer, VerificarCorreoSerializer)

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


class CorregirCorreoView(APIView):
    """
    Corrección del propio correo, solo mientras la cuenta no esté confirmada.

    Lleva límite por origen aunque exija sesión: cada cambio dispara un correo
    a una dirección que escribe quien pide, y sin tope sería una forma de
    mandarle mensajes a un tercero uno detrás de otro. El tope es el mismo de
    la recuperación, que es el otro botón del sistema con esa forma.
    """

    permission_classes = [IsAuthenticated]
    throttle_scope = "recuperacion"

    def patch(self, request):
        if request.user.correo_verificado:
            return Response(
                {"detalle": "Tu correo ya está confirmado. Para cambiarlo, pídeselo "
                            "al administrador de tu licorera."},
                status=status.HTTP_409_CONFLICT,
            )

        serializador = CorregirCorreoSerializer(
            data=request.data, context={"usuario": request.user}
        )
        serializador.is_valid(raise_exception=True)
        usuario = serializador.guardar()
        # Fuera de cualquier transacción y después de guardar: si el servicio de
        # correo está caído, la corrección no se pierde y el enlace se puede
        # pedir otra vez con el botón de reenviar.
        enviar_correo_verificacion(usuario)
        return Response(
            {"detalle": "Correo actualizado. Te enviamos el enlace de confirmación "
                        "a la dirección nueva."},
            status=status.HTTP_200_OK,
        )


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

    Dos permisos y no uno: el primero dice quién —solo el administrador de la
    licorera—, y el segundo dice cuándo —solo con la suscripción vigente
    (RF-SUS-03)—. Consultar la lista sigue funcionando con la cuenta suspendida;
    crear, modificar e inactivar, no. Es el primer sitio donde se aplica la regla
    del módulo SUS, y el mismo par se repetirá en INV y en VEN.
    """

    permission_classes = [EsAdministradorDeLicorera, PuedeRegistrarOperaciones]

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

    def perform_update(self, serializador):
        """
        Si el administrador cambió el correo de alguien, esa cuenta vuelve a
        quedar pendiente de confirmación y hay que enviarle el enlace nuevo
        (decisión D-29).

        El serializador es quien sabe si el correo cambió —compara con el valor
        anterior antes de guardarlo—; aquí solo se manda el correo, porque
        enviar no es tarea suya.
        """
        usuario = serializador.save()
        if getattr(serializador, "cambio_de_correo", False):
            enviar_correo_verificacion(usuario)

    def create(self, request, *args, **kwargs):
        """Antes de crear, comprueba que el plan contratado admita un usuario más."""
        if not request.user.licorera.puede_agregar_usuario():
            plan = request.user.licorera.plan_vigente()
            return Response(
                {
                    # «1 usuario(s)» es una cadena de programación, no español.
                    # El documento de diseño prohíbe que el usuario vea rastros
                    # técnicos, y el mensaje los tenía.
                    "detalle": (
                        f"El plan {plan.nombre} permite "
                        f"{'un usuario' if plan.maximo_usuarios == 1 else f'{plan.maximo_usuarios} usuarios'}. "
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


class VerificarCorreoView(APIView):
    """
    Confirmación del correo desde el enlace recibido (D-10).

    Es pública por la misma razón que el restablecimiento: quien abre el enlace
    puede estar en otro navegador o en el teléfono, sin sesión iniciada. Lo que
    autoriza la operación es la firma del token.

    Abrir dos veces el mismo enlace responde lo mismo la segunda vez. No es un
    descuido: el resultado que el usuario pidió —su correo confirmado— es el
    mismo, y un error ahí solo lo confundiría.
    """

    permission_classes = [AllowAny]
    throttle_scope = "verificacion"

    def post(self, request):
        serializador = VerificarCorreoSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)
        serializador.save()
        return Response(
            {"detalle": "Tu correo quedó confirmado."},
            status=status.HTTP_200_OK,
        )


class ReenviarVerificacionView(APIView):
    """
    Reenvío del enlace de confirmación (D-10).

    Esta sí exige sesión, y por eso no necesita responder de forma ambigua como
    la recuperación de contraseña: el correo se manda a la dirección de quien
    está autenticado, así que no sirve para averiguar qué cuentas existen ni
    para bombardear a un tercero. Aun así lleva límite por origen, porque es un
    botón que se puede pulsar muchas veces seguidas.
    """

    permission_classes = [IsAuthenticated]
    throttle_scope = "verificacion"

    def post(self, request):
        usuario = request.user
        if usuario.correo_verificado:
            return Response(
                {"detalle": "Tu correo ya está confirmado."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            enviar_correo_verificacion(usuario)
        except Exception:
            # Igual que en la recuperación: si el servicio de correo falla, se
            # deja el rastro en el registro del servidor y no se le muestra al
            # usuario un error técnico que no puede resolver.
            registro.exception("No se pudo reenviar el correo de verificación")
        return Response(
            {"detalle": "Te enviamos un enlace nuevo a %s." % usuario.correo},
            status=status.HTTP_200_OK,
        )
