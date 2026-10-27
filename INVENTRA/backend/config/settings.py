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
    "sedes",                         # SED: solo la tabla y la sede principal 
    "inventario",                    # INV: catálogo, lotes y kardex
    "ventas",                        # VEN: punto de venta, anulación y cierre de caja
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    # Los dos siguientes entran con el despliegue, cuando este servidor pasa a
    # entregar también la página de la interfaz y no solo JSON.
    #
    # El de clickjacking impide que esa página se dibuje dentro de un marco en
    # otro sitio, que es como se engaña a alguien para que pulse un botón que
    # no está viendo.
    #
    # El de CSRF no cambia nada para la API: las vistas de REST framework
    # nacen exentas y la sesión viaja en el encabezado de autorización, no en
    # una galleta que el navegador mande sola. Se pone porque la comprobación
    # de despliegue de Django lo exige y porque el día que algo de aquí use
    # una galleta, la protección ya está puesta.
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

# Carpeta donde Vite deja la interfaz compilada. El servidor publicado sirve la
# API y la interfaz desde la MISMA dirección: así no hay dos dominios que
# coordinar, no hace falta CORS y lo que se entrega es una URL y no dos.
INTERFAZ_COMPILADA = BASE_DIR.parent / "frontend" / "dist"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # El `index.html` que genera Vite se busca aquí. En desarrollo esa
        # carpeta no existe —la interfaz la sirve Vite en su propio puerto— y
        # no pasa nada: solo se consulta al pedir una dirección que no es de
        # la API.
        "DIRS": [INTERFAZ_COMPILADA],
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

# Tipo de llave primaria por defecto para los modelos.
#
# OJO CON ESTA LÍNEA. Cada aplicación puede declarar su propio
# `default_auto_field` en su archivo apps.py, y el de la aplicación PREVALECE
# sobre este. `startapp` genera ese archivo con BigAutoField, que es el valor por
# defecto de Django, así que durante los primeros bloques aquí decía AutoField
# mientras las tablas se creaban con BIGINT: la línea no hacía nada y engañaba a
# quien la leyera.
#
# Se adopta BigAutoField, que es lo que ya tienen las migraciones y el valor que
# recomienda Django para no agotar el rango de identificadores en tablas que
# crecen, como el kardex y las ventas. Ahora configuración y realidad coinciden.
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

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
    # Propio del proyecto: exige combinar letras y números (RF-SEG-01)
    {"NAME": "seguridad.validators.LetrasYNumerosValidator"},
]


# ---------------------------------------------------------------------------
# Correo electrónico y recuperación de contraseña
# ---------------------------------------------------------------------------

# Vigencia del enlace de recuperación, en segundos. La especificación fija treinta
# minutos (RF-SEG-04). Django usa este valor al comprobar el token, de modo que el
# vencimiento no hay que programarlo ni guardarlo en ninguna tabla.
PASSWORD_RESET_TIMEOUT = 30 * 60

# El enlace que confirma el correo dura tres días, no treinta minutos: se lee
# cuando la persona abre su bandeja, que puede ser al día siguiente, y mientras
# tanto la cuenta funciona igual. El de la contraseña es corto porque
# abre la puerta de una cuenta; este solo confirma una dirección.
EMAIL_VERIFICATION_TIMEOUT = 3 * 24 * 60 * 60

# Dirección del frontend: el enlace del correo lleva a una pantalla, no a la API.
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

# En desarrollo los correos no salen a internet: se imprimen en la terminal donde
# corre el servidor, así se puede copiar el enlace y probar el flujo completo sin
# contratar un servicio de correo. En el servidor publicado se cambia en el .env a
# django.core.mail.backends.smtp.EmailBackend y se completan los datos del proveedor.
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_SERVIDOR", "")
EMAIL_PORT = int(os.getenv("EMAIL_PUERTO", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_TLS", "True") == "True"
EMAIL_HOST_USER = os.getenv("EMAIL_USUARIO", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_CONTRASENA", "")
DEFAULT_FROM_EMAIL = os.getenv("EMAIL_REMITENTE", "INVENTRA <no-responder@inventra.co>")


# ---------------------------------------------------------------------------
# Almacén temporal
# ---------------------------------------------------------------------------

# Aquí lleva la cuenta el límite de peticiones. En desarrollo basta con la
# memoria del propio proceso.
#
# LIMITACIÓN QUE HAY QUE CONOCER: si el servidor publicado corre varios procesos,
# cada uno lleva su propio contador, así que el límite real se multiplica por el
# número de procesos; y al reiniciar el servidor los contadores se ponen en cero.
# En producción esto se cambia por una caché compartida (Redis o la propia base
# de datos) sin tocar ninguna otra línea del proyecto.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "inventra-contadores",
    }
}


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

# Los archivos que Vite compila entran al mismo almacen de estaticos que los de
# Django, bajo el prefijo «assets» que la propia compilacion usa. Asi el
# servidor publicado necesita UNA sola regla —/static/ a la carpeta
# recolectada— en vez de dos, y `collectstatic` se los lleva con todo lo demas.
#
# La carpeta se incluye solo si existe: en un equipo donde nunca se ha
# compilado la interfaz, Django avisaria de un directorio inexistente en cada
# orden que se ejecute, incluidas las pruebas.
_ASSETS = INTERFAZ_COMPILADA / "assets"
STATICFILES_DIRS = [("assets", _ASSETS)] if _ASSETS.is_dir() else []


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

    # Límite de peticiones por origen. Se declara «con ámbito»: solo se aplica a
    # las vistas que declaran un `throttle_scope`, y las demás no se tocan. Así
    # el límite queda en las tres puertas públicas y no estorba en el resto.
    "DEFAULT_THROTTLE_CLASSES": ("rest_framework.throttling.ScopedRateThrottle",),
    "DEFAULT_THROTTLE_RATES": {
        "registro": "5/hour",          # nadie abre cinco licoreras en una hora
        "ingreso": "20/hour",          # frena la prueba de contraseñas por fuerza bruta
        "recuperacion": "5/hour",      # evita usar el sistema para bombardear a un tercero
        "restablecimiento": "10/hour",
        "verificacion": "10/hour",     # el botón de reenviar se puede pulsar muchas veces
    },
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

# En el servidor publicado esta lista queda vacía a propósito: la interfaz se
# sirve desde la misma dirección que la API, de modo que el navegador no hace
# ninguna petición entre orígenes y no hay nada que autorizar.


# ---------------------------------------------------------------------------
# Lo que cambia cuando el sistema está publicado
# ---------------------------------------------------------------------------
#
# Estas protecciones cuelgan de DEBUG y no de una variable propia porque solo
# tienen sentido detrás de HTTPS: con la redirección puesta, el servidor de
# desarrollo mandaría el navegador a `https://127.0.0.1:8000`, donde no hay
# nada escuchando. Una variable aparte sería una cosa más que acordarse de
# poner el día del despliegue, y el día del despliegue se olvidan cosas.

if not DEBUG:
    # El alojamiento termina el TLS en su propio servidor y reenvía la petición
    # por HTTP con esta cabecera. Sin la línea, Django cree que la conexión es
    # insegura, redirige a HTTPS, el proxy vuelve a entregarla por HTTP y el
    # navegador acaba en un bucle de redirecciones.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True

    # Un año. La cabecera le dice al navegador que no vuelva a intentar HTTP
    # con este dominio ni aunque el usuario escriba la dirección a mano.
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    # `preload` es solo una declaración: no hace nada hasta que alguien
    # inscribe el dominio en la lista que mantienen los navegadores.
    SECURE_HSTS_PRELOAD = True

    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # La sesión viaja en el encabezado de autorización y no en una galleta, de
    # modo que esto protege poco; se pone igual, porque el día que algo use una
    # galleta nadie va a volver a este archivo.
    X_FRAME_OPTIONS = "DENY"

    # Direcciones desde las que se aceptan formularios. La API no usa
    # formularios —todo va por JSON con su token—, pero la comprobación de
    # despliegue de Django la exige y cuesta una línea.
    CSRF_TRUSTED_ORIGINS = [
        "https://%s" % h for h in ALLOWED_HOSTS if not h.startswith(".")
    ]
