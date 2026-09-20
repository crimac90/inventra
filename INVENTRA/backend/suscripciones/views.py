"""Vistas del módulo de suscripciones."""

from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from seguridad.serializers import InicioSesionSerializer, UsuarioSerializer

from .models import Plan
from .serializers import LicoreraSerializer, PlanSerializer, RegistroLicoreraSerializer


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

        return Response(
            {
                "licorera": LicoreraSerializer(creado["licorera"]).data,
                "usuario": UsuarioSerializer(usuario).data,
                "acceso": str(tokens.access_token),
                "refresco": str(tokens),
            },
            status=status.HTTP_201_CREATED,
        )
