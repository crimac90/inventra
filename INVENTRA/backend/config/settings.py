"""
Configuración del proyecto INVENTRA.

Los valores que cambian entre equipos (credenciales, direcciones, modo de
depuración) no se escriben aquí: se leen del archivo .env, que no se publica.
"""

from pathlib import Path
import os

from dotenv import load_dotenv

# Carpeta raíz del backend: la que contiene manage.py
BASE_DIR = Path(__file__).resolve().parent.parent

# Carga las variables del archivo .env en el entorno del proceso
load_dotenv(BASE_DIR / ".env")


# ---------------------------------------------------------------------------
# Seguridad
# ---------------------------------------------------------------------------

# Clave criptográfica: firma las sesiones y los tokens. Nunca se publica.
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")

# En modo depuración Django muestra el detalle de los errores. Solo en desarrollo.
DEBUG = os.getenv("DJANGO_DEBUG", "False") == "True"

# Direcciones desde las que se permite servir la aplicación
ALLOWED_HOSTS = [h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()]


# ---------------------------------------------------------------------------
# Aplicaciones
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    # Del propio Django
    "django.contrib.contenttypes",   # registro de los tipos de modelo
    "django.contrib.auth",           # cifrado de contraseñas y autenticación
    "django.contrib.staticfiles",    # archivos estáticos

    # De terceros
    "rest_framework",                # publicación de la API REST
    "corsheaders",                   # permite que el frontend consuma la API
    "rest_framework_simplejwt.token_blacklist",  # invalida los tokens al cerrar sesión

    # Del proyecto, una por módulo funcional
    "suscripciones",                 # SUS: licoreras, planes y suscripciones
    "seguridad",                     # SEG: usuarios y roles
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# ---------------------------------------------------------------------------
# Base de datos
# ---------------------------------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.getenv("DB_NOMBRE"),
        "USER": os.getenv("DB_USUARIO"),
        "PASSWORD": os.getenv("DB_CONTRASENA"),
        "HOST": os.getenv("DB_HOST", "127.0.0.1"),
        "PORT": os.getenv("DB_PUERTO", "3306"),
        "OPTIONS": {
            "charset": "utf8mb4",
            # Hace que MySQL rechace datos inválidos en lugar de truncarlos
            "sql_mode": "STRICT_TRANS_TABLES",
        },
    }
}

# Tipo de llave primaria por defecto para los modelos
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

# Modelo de usuario propio del proyecto, en lugar del que trae Django
AUTH_USER_MODEL = "seguridad.Usuario"


# ---------------------------------------------------------------------------
# Validación de contraseñas
# ---------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ---------------------------------------------------------------------------
# Idioma y zona horaria
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True


# ---------------------------------------------------------------------------
# Archivos estáticos
# ---------------------------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"


# ---------------------------------------------------------------------------
# API REST
# ---------------------------------------------------------------------------

REST_FRAMEWORK = {
    # Por defecto, toda vista exige un token válido
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    # Los listados se entregan por páginas
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
}

from datetime import timedelta  # noqa: E402

SIMPLE_JWT = {
    # Token de acceso de vida corta y token de refresco para renovarlo
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=8),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "usuario_id",
    # Al renovar, el token anterior deja de servir: si alguien lo robó, caduca pronto
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}


# ---------------------------------------------------------------------------
# Acceso desde el frontend
# ---------------------------------------------------------------------------

CORS_ALLOWED_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGENES", "").split(",") if o.strip()]
