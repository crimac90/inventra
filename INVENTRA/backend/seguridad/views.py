"""
Vistas del módulo de seguridad.

Una vista recibe la petición que llega por una dirección de la API, decide qué
hacer con ella y devuelve la respuesta.
"""

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import CierreSesionSerializer, InicioSesionSerializer, UsuarioSerializer


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
