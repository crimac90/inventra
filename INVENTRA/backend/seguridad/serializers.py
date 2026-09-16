"""
Traductores entre los modelos de seguridad y el formato JSON de la API.

Un serializador cumple dos funciones: convierte objetos de Python en JSON para
responderle al frontend, y valida los datos que llegan del frontend antes de
que toquen la base de datos.
"""

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Usuario

# Mensaje único para credenciales incorrectas. Es deliberadamente genérico: si
# dijera «el correo no existe», cualquiera podría averiguar qué cuentas hay
# registradas probando correos (RF-SEG-02).
CREDENCIALES_INVALIDAS = "El correo o la contraseña no son correctos."


class UsuarioSerializer(serializers.ModelSerializer):
    """Datos del usuario que se devuelven al frontend. Nunca incluye la contraseña."""

    rol = serializers.CharField(source="rol.nombre", read_only=True)
    licorera_nombre = serializers.CharField(source="licorera.nombre", read_only=True, default=None)

    class Meta:
        model = Usuario
        fields = [
            "id", "nombre_completo", "correo", "telefono",
            "rol", "licorera_id", "licorera_nombre", "activo",
        ]


class InicioSesionSerializer(TokenObtainPairSerializer):
    """
    Valida el ingreso al sistema (RF-SEG-02).

    Se reemplaza la validación que trae la librería porque aquí hacen falta tres
    comportamientos propios: identificarse con el correo, contar los intentos
    fallidos y respetar el bloqueo temporal de la cuenta.
    """

    username_field = Usuario.USERNAME_FIELD   # el campo de acceso es el correo

    @classmethod
    def get_token(cls, usuario):
        """
        Agrega al token los datos que el frontend necesita en cada petición para
        saber qué mostrar, sin tener que consultarlos otra vez.
        """
        token = super().get_token(usuario)
        token["rol"] = usuario.rol.nombre
        token["licorera_id"] = usuario.licorera_id
        token["nombre"] = usuario.nombre_completo
        return token

    def validate(self, attrs):
        correo = (attrs.get("correo") or "").strip().lower()
        contrasena = attrs.get("password") or ""

        usuario = Usuario.objects.filter(correo=correo).select_related("rol", "licorera").first()

        # Cuenta inexistente: mismo mensaje que contraseña equivocada
        if usuario is None:
            raise serializers.ValidationError(CREDENCIALES_INVALIDAS)

        if usuario.esta_bloqueado():
            raise serializers.ValidationError(
                "La cuenta está bloqueada temporalmente por varios intentos fallidos. "
                f"Intenta de nuevo en unos minutos."
            )

        if not usuario.activo:
            raise serializers.ValidationError(
                "La cuenta está inactiva. Comunícate con el administrador de tu licorera."
            )

        if not usuario.check_password(contrasena):
            usuario.registrar_intento_fallido()
            raise serializers.ValidationError(CREDENCIALES_INVALIDAS)

        # Ingreso correcto: se limpia el contador y se entregan los tokens
        usuario.registrar_ingreso_exitoso()
        refresh = self.get_token(usuario)

        return {
            "acceso": str(refresh.access_token),
            "refresco": str(refresh),
            "usuario": UsuarioSerializer(usuario).data,
        }


class CierreSesionSerializer(serializers.Serializer):
    """Recibe el token de refresco que se va a invalidar al cerrar sesión (RF-SEG-03)."""

    refresco = serializers.CharField()

    def guardar(self):
        """
        Envía el token a la lista negra. A partir de ese momento ya no sirve para
        obtener tokens nuevos, aunque alguien lo haya copiado.
        """
        try:
            RefreshToken(self.validated_data["refresco"]).blacklist()
        except Exception:
            raise serializers.ValidationError("El token de la sesión no es válido.")
