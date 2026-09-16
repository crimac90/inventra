"""
Módulo SEG — Seguridad.

Contiene el catálogo de roles y el modelo de usuario del sistema.

El usuario es propio del proyecto y no el que trae Django de fábrica, porque
necesita pertenecer a una licorera, tener un rol y llevar el control de
intentos fallidos y bloqueo. Corresponde a las tablas rol y usuario del
diccionario de datos.
"""

from datetime import timedelta

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.utils import timezone


class Rol(models.Model):
    """Catálogo de roles del sistema (RF-SEG-05)."""

    ADMINISTRADOR_LICORERA = "administrador_licorera"
    VENDEDOR = "vendedor"
    ADMINISTRADOR_INVENTRA = "administrador_inventra"

    nombre = models.CharField(max_length=30, unique=True)
    descripcion = models.CharField(
        max_length=150,
        help_text="Qué puede hacer el rol, en lenguaje claro.",
    )

    class Meta:
        db_table = "rol"
        verbose_name = "rol"
        verbose_name_plural = "roles"

    def __str__(self):
        return self.nombre


class UsuarioManager(BaseUserManager):
    """
    Encargado de crear usuarios. Centraliza aquí la creación para que la
    contraseña siempre se guarde cifrada y nunca en texto plano (RNF-02).
    """

    use_in_migrations = True

    def create_user(self, correo, nombre_completo, password=None, **extras):
        if not correo:
            raise ValueError("El correo electrónico es obligatorio.")
        correo = self.normalize_email(correo).lower()
        usuario = self.model(correo=correo, nombre_completo=nombre_completo, **extras)
        usuario.set_password(password)   # cifra la contraseña
        usuario.save(using=self._db)
        return usuario

    def create_superuser(self, correo, nombre_completo, password=None, **extras):
        """
        Crea la cuenta del personal de la plataforma: sin licorera asociada y
        con el rol de administrador de INVENTRA.
        """
        rol, _ = Rol.objects.get_or_create(
            nombre=Rol.ADMINISTRADOR_INVENTRA,
            defaults={"descripcion": "Administra la plataforma, las licoreras y los planes."},
        )
        extras.setdefault("rol", rol)
        extras.setdefault("licorera", None)
        return self.create_user(correo, nombre_completo, password, **extras)


class Usuario(AbstractBaseUser):
    """Cuentas de acceso al sistema (RF-SEG-01, 02, 04, 06 y 07)."""

    licorera = models.ForeignKey(
        "suscripciones.Licorera", on_delete=models.PROTECT,
        null=True, blank=True, related_name="usuarios", db_column="licorera_id",
        help_text="Licorera a la que pertenece. Vacío para el personal de INVENTRA.",
    )
    rol = models.ForeignKey(
        Rol, on_delete=models.PROTECT, related_name="usuarios", db_column="rol_id",
        help_text="Rol que define sus permisos.",
    )
    nombre_completo = models.CharField(max_length=100)
    correo = models.EmailField(
        max_length=100, unique=True,
        help_text="Identificador de acceso; único en toda la plataforma.",
    )
    telefono = models.CharField(max_length=20, null=True, blank=True)

    # Contraseña cifrada. Django la administra en el campo password; aquí se
    # guarda en la columna contrasena_hash, como está en el diccionario de datos.
    password = models.CharField(max_length=255, db_column="contrasena_hash")

    intentos_fallidos = models.PositiveSmallIntegerField(
        default=0,
        help_text="Contador para el bloqueo tras cinco intentos (RF-SEG-02).",
    )
    bloqueado_hasta = models.DateTimeField(
        null=True, blank=True,
        help_text="Fin del bloqueo temporal. Vacío si no está bloqueado.",
    )
    activo = models.BooleanField(
        default=True,
        help_text="Baja lógica: el inactivo no entra, su historial permanece.",
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    # Django registra aquí la última entrada; en la base se llama ultimo_acceso.
    last_login = models.DateTimeField(null=True, blank=True, db_column="ultimo_acceso")

    objects = UsuarioManager()

    # Campo con el que se inicia sesión y datos que pide createsuperuser
    USERNAME_FIELD = "correo"
    REQUIRED_FIELDS = ["nombre_completo"]

    class Meta:
        db_table = "usuario"
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"

    def __str__(self):
        return f"{self.nombre_completo} ({self.correo})"

    # Política de bloqueo por intentos fallidos (RF-SEG-02). La especificación
    # exige bloquear tras cinco intentos; la duración se fija aquí, en un solo
    # lugar, para poder ajustarla sin tocar el resto del código.
    MAXIMO_INTENTOS = 5
    MINUTOS_DE_BLOQUEO = 15

    @property
    def is_active(self):
        """Django consulta este nombre para decidir si la cuenta puede entrar."""
        return self.activo

    @property
    def es_administrador_inventra(self):
        return self.rol_id is not None and self.rol.nombre == Rol.ADMINISTRADOR_INVENTRA

    def esta_bloqueado(self):
        """Indica si la cuenta está en período de bloqueo en este momento."""
        return self.bloqueado_hasta is not None and self.bloqueado_hasta > timezone.now()

    def registrar_intento_fallido(self):
        """
        Suma un intento fallido y, al llegar al máximo, bloquea la cuenta por el
        tiempo definido. El contador se guarda en la base para que el bloqueo
        funcione aunque el usuario cambie de equipo o de navegador.
        """
        self.intentos_fallidos += 1
        if self.intentos_fallidos >= self.MAXIMO_INTENTOS:
            self.bloqueado_hasta = timezone.now() + timedelta(minutes=self.MINUTOS_DE_BLOQUEO)
            self.intentos_fallidos = 0
        self.save(update_fields=["intentos_fallidos", "bloqueado_hasta"])

    def registrar_ingreso_exitoso(self):
        """Limpia el contador y el bloqueo, y deja registrada la fecha de ingreso."""
        self.intentos_fallidos = 0
        self.bloqueado_hasta = None
        self.last_login = timezone.now()
        self.save(update_fields=["intentos_fallidos", "bloqueado_hasta", "last_login"])
