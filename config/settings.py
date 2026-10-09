"""
Configuración del Libro de Reclamaciones.

Base de datos: SQLite por defecto. Para migrar a PostgreSQL basta con definir
DB_ENGINE=postgres y las variables DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT
(ver README.md).
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).lower() in ("1", "true", "yes", "si")


# --- Seguridad -------------------------------------------------------------
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-cambiar-en-produccion-solo-para-desarrollo",
)
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = [h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]
CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o]

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True

# --- Aplicaciones ----------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "reclamaciones",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "reclamaciones.context_processors.empresa",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- Base de datos ---------------------------------------------------------
if os.environ.get("DATABASE_URL"):
    import dj_database_url
    DATABASES = {"default": dj_database_url.config(conn_max_age=600)}
elif os.environ.get("DB_ENGINE", "sqlite").lower() in ("postgres", "postgresql"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("DB_NAME", "libro_reclamaciones"),
            "USER": os.environ.get("DB_USER", "postgres"),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", "localhost"),
            "PORT": os.environ.get("DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Internacionalización --------------------------------------------------
LANGUAGE_CODE = "es-pe"
TIME_ZONE = "America/Lima"
USE_I18N = True
USE_TZ = True

# --- Archivos estáticos y media -------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Autenticación del panel ----------------------------------------------
LOGIN_URL = "reclamaciones:login"
LOGIN_REDIRECT_URL = "reclamaciones:panel"
LOGOUT_REDIRECT_URL = "reclamaciones:inicio"

# --- Correo (consola en desarrollo) ---------------------------------------
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "25"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", False)
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "reclamos@example.com")

# --- Datos de la empresa (se muestran en la hoja de reclamación) -----------
EMPRESA = {
    "razon_social": os.environ.get("EMPRESA_RAZON_SOCIAL", "RAZÓN SOCIAL DE LA EMPRESA S.A.C."),
    "nombre_comercial": os.environ.get("EMPRESA_NOMBRE", "Nombre Comercial"),
    "ruc": os.environ.get("EMPRESA_RUC", "00000000000"),
    "domicilio_fiscal": os.environ.get("EMPRESA_DOMICILIO", "Dirección fiscal de la empresa"),
}

# Plazo legal de atención (días hábiles). Verificar vigencia con el área legal.
PLAZO_RESPUESTA_DIAS_HABILES = int(os.environ.get("PLAZO_RESPUESTA_DIAS_HABILES", "15"))

# URL base del servidor (para generar QR). Ej: http://192.168.1.50:8000
SITE_URL = os.environ.get("SITE_URL", "")
