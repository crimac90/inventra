"""Vistas del módulo de suscripciones."""

import logging

from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from seguridad.correo import enviar_correo_verificacion
from seguridad.serializers import InicioSesionSerializer, UsuarioSerializer

from .models import Plan
from .modulos import estado_de_los_modulos
from .serializers import (
    LicoreraSerializer,
    MiSuscripcionSerializer,
    PlanSerializer,
    RegistroLicoreraSerializer,
)

registro_log = logging.getLogger(__name__)


class PlanesView(ListAPIView):
    """Catálogo de planes disponibles. Es público: se muestra antes de registrarse."""

    permission_classes = [AllowAny]
    serializer_class = PlanSerializer
    pagination_class = None

    def get_queryset(self):
        return Plan.objects.filter(activo=True).order_by("precio_mensual")


class RegistroLicoreraView(APIView):
    """
    Registro de una licorera y su administrador (CU-SUS-01).

    No exige autenticación, porque quien se registra todavía no tiene cuenta. Al
    terminar devuelve los tokens, de modo que el usuario entra directamente al
    panel sin tener que iniciar sesión otra vez.
    """

    permission_classes = [AllowAny]
    # Límite de peticiones por origen (D-11): sin él, esta dirección permite
    # crear cuentas en masa.
    throttle_scope = "registro"

    def post(self, request):
        serializador = RegistroLicoreraSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)
        creado = serializador.save()

        usuario = creado["usuario"]
        tokens = InicioSesionSerializer.get_token(usuario)
        usuario.registrar_ingreso_exitoso()

        # El enlace de confirmación sale aquí y no dentro del serializador: crear
        # la licorera es una operación de base de datos y mandar un correo es una
        # llamada a un servicio de fuera. Si el correo falla, la cuenta ya existe
        # y la persona puede pedir otro enlace desde su perfil; lo que no puede
        # pasar es que un servicio caído impida registrarse (D-10).
        try:
            enviar_correo_verificacion(usuario)
        except Exception:
            registro_log.exception("No se pudo enviar el correo de verificación")

        return Response(
            {
                "licorera": LicoreraSerializer(creado["licorera"]).data,
                "usuario": UsuarioSerializer(usuario).data,
                "acceso": str(tokens.access_token),
                "refresco": str(tokens),
            },
            status=status.HTTP_201_CREATED,
        )


class MiSuscripcionView(APIView):
    """
    Suscripción vigente de la licorera de quien consulta (RF-SUS-03).

    No recibe ningún identificador: la licorera se toma del usuario de la
    petición. Es el mismo criterio que el perfil, y por la misma razón: si el
    identificador viniera en la dirección, habría que comprobar en cada llamada
    que es el suyo, y bastaría olvidarlo una vez para que un negocio viera la
    suscripción de otro.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        licorera = request.user.licorera
        if licorera is None:
            # El Administrador INVENTRA no pertenece a ninguna licorera.
            return Response({"detalle": "Tu cuenta no pertenece a una licorera."},
                            status=status.HTTP_404_NOT_FOUND)

        suscripcion = licorera.suscripcion_vigente()
        if suscripcion is None:
            # Sin suscripción vigente el negocio consulta pero no registra. Se
            # responde 200 con el dato, no un error: la falta de suscripción es
            # una situación normal del negocio, no un fallo de la petición.
            return Response({"plan": None, "estado": None, "puede_operar": False})

        return Response(MiSuscripcionSerializer(suscripcion).data)


class MisModulosView(APIView):
    """
    Qué módulos puede usar hoy la licorera de quien consulta (RF-SUS-04).

    El menú lateral tenía la lista escrita a mano, con la marca «Pronto» puesta
    a ojo. Esa lista no puede vivir en el navegador: el plan contratado lo sabe
    el servidor, y una licorera con plan Básico no debe leer que Sedes llegará
    «Pronto» cuando para ella no va a llegar.

    El plan sale de la suscripción **actual** y no de la vigente: una cuenta
    suspendida sigue teniendo un plan contratado, y su menú tiene que seguir
    diciendo la verdad sobre lo que ese plan incluye. Lo que no puede hacer
    mientras está suspendida —registrar— lo corta el permiso de escritura, que
    es otra cosa.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        licorera = request.user.licorera
        plan = None
        if licorera is not None:
            suscripcion = licorera.suscripcion_actual()
            plan = suscripcion.plan if suscripcion else None
        return Response({"modulos": estado_de_los_modulos(plan)})

