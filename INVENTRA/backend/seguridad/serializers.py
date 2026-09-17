"""
Traductores entre los modelos de seguridad y el formato JSON de la API.

Un serializador cumple dos funciones: convierte objetos de Python en JSON para
responderle al frontend, y valida los datos que llegan del frontend antes de
que toquen la base de datos.
"""

from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as ErrorDeValidacion
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Rol, Usuario

# Mensaje único para credenciales incorrectas. Es deliberadamente genérico: si
# dijera «el correo no existe», cualquiera podría averiguar qué cuentas hay
# registradas probando correos (RF-SEG-02).
CREDENCIALES_INVALIDAS = "El correo o la contraseña no son correctos."

# Mensaje único para cualquier problema del enlace de recuperación: vencido, ya
# usado, manipulado o de una cuenta que no existe. Distinguirlos ayudaría a quien
# estuviera probando enlaces al azar (RF-SEG-04).
ENLACE_INVALIDO = "El enlace no es válido o ya venció. Solicita uno nuevo."


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

        # Todos los rechazos de esta validación usan AuthenticationFailed y no
        # ValidationError. La diferencia no es de estilo: ValidationError
        # significa «los datos que enviaste están mal formados» y responde 400,
        # mientras que aquí los datos llegaron bien y lo que falla es la
        # identidad de quien pide entrar, que es exactamente lo que significa el
        # código 401. El frontend distingue los dos casos: ante un 400 resalta
        # el campo con el error, ante un 401 muestra el mensaje de acceso
        # denegado.

        # Cuenta inexistente: mismo mensaje que contraseña equivocada
        if usuario is None:
            raise AuthenticationFailed(CREDENCIALES_INVALIDAS)

        if usuario.esta_bloqueado():
            raise AuthenticationFailed(
                "La cuenta está bloqueada temporalmente por varios intentos fallidos. "
                "Intenta de nuevo en unos minutos."
            )

        if not usuario.activo:
            raise AuthenticationFailed(
                "La cuenta está inactiva. Comunícate con el administrador de tu licorera."
            )

        if not usuario.check_password(contrasena):
            usuario.registrar_intento_fallido()
            raise AuthenticationFailed(CREDENCIALES_INVALIDAS)

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


class RolSerializer(serializers.ModelSerializer):
    """Catálogo de roles que el administrador puede asignar."""

    class Meta:
        model = Rol
        fields = ["id", "nombre", "descripcion"]


class UsuarioCrearSerializer(serializers.ModelSerializer):
    """
    Alta de un usuario dentro de una licorera (RF-SEG-01).

    La licorera no se recibe del cliente: se toma del usuario que hace la
    petición. Así nadie puede crear cuentas en un negocio ajeno, ni siquiera
    manipulando los datos enviados.
    """

    password = serializers.CharField(write_only=True)
    rol = serializers.PrimaryKeyRelatedField(
        queryset=Rol.objects.exclude(nombre=Rol.ADMINISTRADOR_INVENTRA)
    )

    class Meta:
        model = Usuario
        fields = ["id", "nombre_completo", "correo", "telefono", "rol", "password"]

    def validate_correo(self, valor):
        correo = valor.strip().lower()
        if Usuario.objects.filter(correo=correo).exists():
            raise serializers.ValidationError("Ya existe una cuenta registrada con este correo.")
        return correo

    def validate_password(self, valor):
        try:
            validate_password(valor)
        except ErrorDeValidacion as error:
            raise serializers.ValidationError(list(error.messages))
        return valor

    def create(self, datos_validados):
        contrasena = datos_validados.pop("password")
        return Usuario.objects.create_user(
            password=contrasena,
            licorera=self.context["request"].user.licorera,
            **datos_validados,
        )


class UsuarioActualizarSerializer(serializers.ModelSerializer):
    """
    Modificación de un usuario por parte del administrador (RF-SEG-05 y RF-SEG-06).

    El correo sí se puede editar aquí, porque la especificación reserva ese cambio
    al administrador de la licorera: es el identificador de acceso, así que el
    propio usuario no puede alterarlo desde su perfil. La contraseña no se toca
    desde aquí; tiene su propio procedimiento.
    """

    rol = serializers.PrimaryKeyRelatedField(
        queryset=Rol.objects.exclude(nombre=Rol.ADMINISTRADOR_INVENTRA),
        required=False,
    )

    class Meta:
        model = Usuario
        fields = ["id", "nombre_completo", "correo", "telefono", "rol", "activo"]

    def validate_correo(self, valor):
        """El correo identifica la cuenta en toda la plataforma, así que sigue siendo único."""
        correo = valor.strip().lower()
        if Usuario.objects.filter(correo=correo).exclude(pk=self.instance.pk).exists():
            raise serializers.ValidationError("Ya existe una cuenta registrada con este correo.")
        return correo


# ---------------------------------------------------------------------------
# Recuperación de contraseña (RF-SEG-04)
# ---------------------------------------------------------------------------

class SolicitarRecuperacionSerializer(serializers.Serializer):
    """
    Primer paso: el usuario escribe su correo y pide el enlace.

    Aquí solo se valida que el dato tenga forma de correo. Si la cuenta existe o
    no, y si se envía o no el mensaje, lo decide la vista, porque la respuesta al
    cliente debe ser idéntica en ambos casos.
    """

    correo = serializers.EmailField()

    def validate_correo(self, valor):
        return valor.strip().lower()


class RestablecerContrasenaSerializer(serializers.Serializer):
    """
    Segundo paso: el usuario abre el enlace y define la contraseña nueva.

    El enlace lleva dos datos: el identificador del usuario codificado y el token.
    El token NO se guarda en ninguna tabla; es un valor firmado que se calcula a
    partir del identificador, la contraseña actual, el último acceso y el momento
    en que se generó. De ahí salen gratis las dos condiciones que exige la
    especificación: vence a los treinta minutos, porque el momento va dentro del
    cálculo, y solo sirve una vez, porque al cambiar la contraseña cambia también
    el valor con el que se comprobaría.
    """

    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        usuario = self._buscar_usuario(attrs["uid"])

        if usuario is None or not usuario.activo:
            raise serializers.ValidationError({"token": ENLACE_INVALIDO})

        if not default_token_generator.check_token(usuario, attrs["token"]):
            raise serializers.ValidationError({"token": ENLACE_INVALIDO})

        try:
            validate_password(attrs["password"], usuario)
        except ErrorDeValidacion as error:
            raise serializers.ValidationError({"password": list(error.messages)})

        attrs["usuario"] = usuario
        return attrs

    @staticmethod
    def _buscar_usuario(uid):
        """Deshace la codificación del enlace y busca la cuenta. Devuelve None si algo no cuadra."""
        try:
            identificador = urlsafe_base64_decode(uid).decode()
            return Usuario.objects.select_related("rol", "licorera").get(pk=identificador)
        except (TypeError, ValueError, OverflowError, Usuario.DoesNotExist):
            return None

    def guardar(self):
        """
        Asigna la contraseña nueva y libera el bloqueo por intentos fallidos: quien
        olvidó su contraseña y agotó los intentos debe poder volver a entrar.
        """
        usuario = self.validated_data["usuario"]
        usuario.set_password(self.validated_data["password"])
        usuario.intentos_fallidos = 0
        usuario.bloqueado_hasta = None
        usuario.save(update_fields=["password", "intentos_fallidos", "bloqueado_hasta"])
        return usuario


# ---------------------------------------------------------------------------
# Perfil propio (RF-SEG-06)
# ---------------------------------------------------------------------------

class PerfilActualizarSerializer(serializers.ModelSerializer):
    """
    Datos que cada usuario puede cambiarse a sí mismo.

    Ni el correo, ni el rol, ni el estado de la cuenta: eso lo administra el
    dueño de la licorera. Si cualquiera pudiera cambiarse el rol, los permisos
    del sistema no valdrían nada.
    """

    class Meta:
        model = Usuario
        fields = ["nombre_completo", "telefono"]


class CambiarContrasenaSerializer(serializers.Serializer):
    """
    Cambio de contraseña con la sesión abierta.

    Se pide la contraseña actual aunque el usuario ya esté autenticado. El motivo
    es el equipo desatendido: si alguien encuentra una sesión abierta, no debe
    poder apropiarse de la cuenta cambiando la contraseña.
    """

    contrasena_actual = serializers.CharField(write_only=True)
    contrasena_nueva = serializers.CharField(write_only=True)

    def validate_contrasena_actual(self, valor):
        usuario = self.context["request"].user
        if not usuario.check_password(valor):
            raise serializers.ValidationError("La contraseña actual no es correcta.")
        return valor

    def validate_contrasena_nueva(self, valor):
        try:
            validate_password(valor, self.context["request"].user)
        except ErrorDeValidacion as error:
            raise serializers.ValidationError(list(error.messages))
        return valor

    def validate(self, attrs):
        if attrs["contrasena_actual"] == attrs["contrasena_nueva"]:
            raise serializers.ValidationError(
                {"contrasena_nueva": "La contraseña nueva debe ser distinta de la actual."}
            )
        return attrs

    def guardar(self):
        usuario = self.context["request"].user
        usuario.set_password(self.validated_data["contrasena_nueva"])
        usuario.save(update_fields=["password"])
        return usuario
