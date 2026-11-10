import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

# Load .env file from project root
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ImproperlyConfigured(
            f"Environment variable {name!r} is required but not set."
        )
    return value


BASE_DIR = Path(__file__).resolve().parent.parent

# --- Core ---

SECRET_KEY = _require_env("SECRET_KEY")

DEBUG = os.environ.get("DEBUG", "False").lower() in ("1", "true", "yes")

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]

# --- Applications ---

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "submissions",
]

# --- Middleware ---

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

# --- Templates ---

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- Database ---
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.sqlite3',
#         'NAME': BASE_DIR / 'db.sqlite3',
#     }
# }

DATABASES = {
    "default": dj_database_url.parse(
        _require_env("DATABASE_URL"),
        conn_max_age=600,
    )
}

# --- Password validation ---

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Internationalisation ---

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --- Static files ---

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "submissions" / "static"]

# --- Default primary key ---

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Authentication ---

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/login/"

# --- Telegram logging ---

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "loggers": {
        # Catches all submissions app logs (Telegram errors, success, etc.)
        "submissions": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
        # Catches all accounts app logs (PayHero errors, subscription events, etc.)
        "accounts": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
        # Django request-level errors (500s, etc.)
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}

# --- PayHero ---
# API credentials — from the PayHero dashboard under API Keys.
# Either set USERNAME + PASSWORD (the library base64-encodes them), or paste
# the finished Basic token directly as PAYHERO_BASIC_AUTH_TOKEN.

PAYHERO_USERNAME = os.environ.get("PAYHERO_USERNAME", "")
PAYHERO_PASSWORD = os.environ.get("PAYHERO_PASSWORD", "")
PAYHERO_BASIC_AUTH_TOKEN = os.environ.get("PAYHERO_BASIC_AUTH_TOKEN", "")

# Numeric channel ID — from PayHero dashboard → Payment Channels → My Payment Channels
PAYHERO_CHANNEL_ID = os.environ.get("PAYHERO_CHANNEL_ID", "")

# --- Security headers (production only) ---

if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = "DENY"
    SECURE_CONTENT_TYPE_NOSNIFF = True
