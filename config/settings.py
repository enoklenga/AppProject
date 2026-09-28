from pathlib import Path
import os
import sys

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "unsafe-development-key")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "django_filters",
    "drf_spectacular",
    "apps.accounts",
    "apps.projects",
    "apps.timesheets",
    "apps.operations",
    "apps.api",
    "apps.planning.apps.PlanningConfig",
    "apps.tasks.apps.TasksConfig",
    "apps.notifications.apps.NotificationsConfig",
    "apps.documents.apps.DocumentsConfig",
    "apps.phases.apps.PhasesConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.api.middleware.ApiSecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.middleware.ForcePasswordChangeMiddleware",
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
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB", "lef_timesheet"),
        "USER": os.getenv("POSTGRES_USER", "lef_timesheet"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
        "HOST": os.getenv("POSTGRES_HOST", "db"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {
            "connect_timeout": 10,
        },
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        )
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "MinimumLengthValidator"
        ),
        "OPTIONS": {"min_length": 10},
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "CommonPasswordValidator"
        )
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "NumericPasswordValidator"
        )
    },
]

AUTH_USER_MODEL = "accounts.User"

LANGUAGE_CODE = "it-it"
TIME_ZONE = "Europe/Rome"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Cartella SEPARATA da MEDIA_ROOT per i documenti di commessa (contratti,
# obiettivi): a differenza di MEDIA_ROOT, questa NON viene mai servita
# direttamente da nginx (vedi deploy/nginx/default.conf, che serve solo
# /media/) — ogni file passa sempre da una view Django che verifica i
# permessi prima di inviarlo. Non usare mai questa cartella per file che
# devono essere pubblici.
PRIVATE_MEDIA_ROOT = BASE_DIR / "private_media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",
)
DEFAULT_FROM_EMAIL = os.getenv(
    "DEFAULT_FROM_EMAIL",
    "timesheet@lef-digital.com",
)

# In staging è possibile usare un backend di sicurezza che recapita tutte le
# email a uno o più indirizzi di test, pur utilizzando un trasporto SMTP reale.
EMAIL_REAL_BACKEND = os.getenv(
    "EMAIL_REAL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_REDIRECT_ALL_TO = [
    value.strip()
    for value in os.getenv("EMAIL_REDIRECT_ALL_TO", "").split(",")
    if value.strip()
]
EMAIL_STAGING_SUBJECT_PREFIX = os.getenv(
    "EMAIL_STAGING_SUBJECT_PREFIX",
    "[LEFTRACK STAGING]",
)

if (
    EMAIL_BACKEND
    == "apps.common.email_backend.StagingRedirectEmailBackend"
    and not EMAIL_REDIRECT_ALL_TO
):
    raise ValueError(
        "In staging EMAIL_REDIRECT_ALL_TO deve contenere almeno un "
        "destinatario di test."
    )


# Configurazione SMTP e URL applicativo
SITE_URL = os.getenv("SITE_URL", "http://localhost:8000").rstrip("/")

EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "20"))

if EMAIL_USE_TLS and EMAIL_USE_SSL:
    raise ValueError(
        "EMAIL_USE_TLS e EMAIL_USE_SSL non possono essere entrambi True."
    )



# Impostazioni di sicurezza configurabili per il rilascio.
def env_list(name: str, default: str = "") -> list[str]:
    return [
        value.strip()
        for value in os.getenv(name, default).split(",")
        if value.strip()
    ]


SESSION_COOKIE_NAME = (
    os.getenv("DJANGO_SESSION_COOKIE_NAME")
    or "lef_timesheet_sessionid"
).strip()

CSRF_COOKIE_NAME = (
    os.getenv("DJANGO_CSRF_COOKIE_NAME")
    or "lef_timesheet_csrftoken"
).strip()

CSRF_USE_SESSIONS = False
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_PATH = "/"
CSRF_COOKIE_SAMESITE = "Lax"

SESSION_COOKIE_PATH = "/"
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", False)
SESSION_COOKIE_SECURE = env_bool("DJANGO_SESSION_COOKIE_SECURE", False)
CSRF_COOKIE_SECURE = env_bool("DJANGO_CSRF_COOKIE_SECURE", False)
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool(
    "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS",
    False,
)
SECURE_HSTS_PRELOAD = env_bool("DJANGO_SECURE_HSTS_PRELOAD", False)
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
SESSION_COOKIE_HTTPONLY = True
DATA_UPLOAD_MAX_MEMORY_SIZE = int(
    os.getenv("DJANGO_DATA_UPLOAD_MAX_MEMORY_SIZE", str(12 * 1024 * 1024))
)
FILE_UPLOAD_MAX_MEMORY_SIZE = int(
    os.getenv("DJANGO_FILE_UPLOAD_MAX_MEMORY_SIZE", str(5 * 1024 * 1024))
)
DOCUMENTS_MAX_UPLOAD_SIZE_MB = int(
    os.getenv("DOCUMENTS_MAX_UPLOAD_SIZE_MB", "10")
)
IMPORT_MAX_UPLOAD_SIZE_MB = int(
    os.getenv("IMPORT_MAX_UPLOAD_SIZE_MB", "5")
)

# Protezione login web. Il bucket principale è per IP+email; il secondo
# limita anche tentativi distribuiti su molte email dallo stesso IP.
WEB_LOGIN_RATE_LIMIT = int(os.getenv("WEB_LOGIN_RATE_LIMIT", "5"))
WEB_LOGIN_IP_RATE_LIMIT = int(os.getenv("WEB_LOGIN_IP_RATE_LIMIT", "30"))
WEB_LOGIN_RATE_WINDOW_SECONDS = int(
    os.getenv("WEB_LOGIN_RATE_WINDOW_SECONDS", "300")
)

if env_bool("DJANGO_TRUST_PROXY_SSL_HEADER", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

if not DEBUG:
    if SECRET_KEY == "unsafe-development-key":
        raise ImproperlyConfigured(
            "In produzione è obbligatorio impostare DJANGO_SECRET_KEY."
        )
    if not ALLOWED_HOSTS:
        raise ImproperlyConfigured(
            "In produzione è obbligatorio impostare DJANGO_ALLOWED_HOSTS."
        )



# Policy di sicurezza API
API_TOKEN_TTL_HOURS = int(os.getenv("API_TOKEN_TTL_HOURS", "720"))
API_TOKEN_TOUCH_INTERVAL_MINUTES = int(
    os.getenv("API_TOKEN_TOUCH_INTERVAL_MINUTES", "5")
)
API_ROTATE_TOKEN_ON_LOGIN = env_bool(
    "API_ROTATE_TOKEN_ON_LOGIN",
    False,
)
IS_TESTING = "test" in sys.argv

# In staging/produzione queste policy restano governate dall'ambiente.
# Durante la suite generale vengono disattivate per non trasformare ogni
# test funzionale in un test del cambio password; i test dedicati le
# riattivano esplicitamente con override_settings.
WEB_REQUIRE_PASSWORD_CHANGED = (
    False
    if IS_TESTING
    else env_bool("WEB_REQUIRE_PASSWORD_CHANGED", False)
)

API_REQUIRE_PASSWORD_CHANGED = (
    False
    if IS_TESTING
    else env_bool("API_REQUIRE_PASSWORD_CHANGED", False)
)
API_SECURITY_LOG_MUTATIONS = env_bool(
    "API_SECURITY_LOG_MUTATIONS",
    True,
)

for _name, _value in (
    ("DOCUMENTS_MAX_UPLOAD_SIZE_MB", DOCUMENTS_MAX_UPLOAD_SIZE_MB),
    ("IMPORT_MAX_UPLOAD_SIZE_MB", IMPORT_MAX_UPLOAD_SIZE_MB),
    ("WEB_LOGIN_RATE_LIMIT", WEB_LOGIN_RATE_LIMIT),
    ("WEB_LOGIN_IP_RATE_LIMIT", WEB_LOGIN_IP_RATE_LIMIT),
    ("WEB_LOGIN_RATE_WINDOW_SECONDS", WEB_LOGIN_RATE_WINDOW_SECONDS),
):
    if _value < 1:
        raise ImproperlyConfigured(f"{_name} deve essere maggiore di zero.")

API_TRUST_X_FORWARDED_FOR = env_bool(
    "API_TRUST_X_FORWARDED_FOR",
    not DEBUG,
)

if API_TOKEN_TTL_HOURS < 1:
    raise ImproperlyConfigured(
        "API_TOKEN_TTL_HOURS deve essere maggiore di zero."
    )

CACHES = {
    "default": {
        "BACKEND": (
            "django.core.cache.backends.filebased.FileBasedCache"
        ),
        "LOCATION": os.getenv(
            "API_THROTTLE_CACHE_DIR",
            "/tmp/lef-api-throttle-cache",
        ),
        "TIMEOUT": 300,
        "OPTIONS": {
            "MAX_ENTRIES": 10000,
        },
    }
}

# ===========================================================================
# API REST
# ===========================================================================

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.api.authentication.ExpiringTokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": (
        [
            "rest_framework.renderers.JSONRenderer",
            "rest_framework.renderers.BrowsableAPIRenderer",
        ]
        if DEBUG
        else ["rest_framework.renderers.JSONRenderer"]
    ),
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.api.pagination.ApiPagination",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "apps.api.throttles.UserBurstRateThrottle",
        "apps.api.throttles.UserSustainedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": os.getenv("API_ANON_THROTTLE_RATE", "20/min"),
        "user_burst": os.getenv(
            "API_USER_BURST_THROTTLE_RATE",
            "120/min",
        ),
        "user_sustained": os.getenv(
            "API_USER_SUSTAINED_THROTTLE_RATE",
            "2000/day",
        ),
        "api_login": os.getenv(
            "API_LOGIN_THROTTLE_RATE",
            "5/min",
        ),
        "api_mutation": os.getenv(
            "API_MUTATION_THROTTLE_RATE",
            "240/hour",
        ),
        "api_sensitive": os.getenv(
            "API_SENSITIVE_THROTTLE_RATE",
            "30/hour",
        ),
        "api_import": os.getenv(
            "API_IMPORT_THROTTLE_RATE",
            "20/hour",
        ),
        "api_export": os.getenv(
            "API_EXPORT_THROTTLE_RATE",
            "120/hour",
        ),
    },
    "NUM_PROXIES": int(
        os.getenv("API_NUM_PROXIES", "1" if not DEBUG else "0")
    ),
    "EXCEPTION_HANDLER": "apps.api.exceptions.api_exception_handler",
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "LEF Timesheet API",
    "DESCRIPTION": (
        "API REST del sistema LEF Timesheet: dati operativi, "
        "dashboard, report, promemoria, importazioni e audit."
    ),
    "VERSION": "1.5.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
    "COMPONENT_SPLIT_REQUEST": True,
    "SORT_OPERATIONS": True,
}


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "lef": {
            "format": (
                "%(asctime)s %(levelname)s %(name)s %(message)s"
            ),
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "lef",
        },
    },
    "loggers": {
        "lef.api": {
            "handlers": ["console"],
            "level": os.getenv("API_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
        "lef.health": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        "django.security.csrf": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },    

}
