"""
Production settings.

Every secret/host-specific value comes from an environment variable so
the same codebase deploys anywhere (school's own server, Railway,
Render, PythonAnywhere, ...) without code changes — only env vars change.

Required environment variables:
    DJANGO_SECRET_KEY        - a long random string, keep it secret
    DJANGO_ALLOWED_HOSTS     - comma-separated, e.g. "materdominischool.com.ng,www.materdominischool.com.ng"
    DATABASE_URL             - e.g. "postgres://user:pass@host:5432/dbname"

Optional:
    DJANGO_DEBUG             - "False" by default; never set "True" in production
"""
import os
from .base import *  # noqa: F401,F403

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

DEBUG = os.environ.get("DJANGO_DEBUG", "False") == "True"

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",")

# --------------------------------------------------------------------------
# Database — Postgres in production. We parse DATABASE_URL by hand to
# avoid adding the dj-database-url dependency for a single line of parsing.
# --------------------------------------------------------------------------
import urllib.parse as _urlparse

_db_url = _urlparse.urlparse(os.environ["DATABASE_URL"])
_db_query = _urlparse.parse_qs(_db_url.query)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _urlparse.unquote(_db_url.path.lstrip("/")),
        "USER": _urlparse.unquote(_db_url.username or ""),
        "PASSWORD": _urlparse.unquote(_db_url.password or ""),
        "HOST": _db_url.hostname,
        "PORT": _db_url.port or 5432,
        "CONN_MAX_AGE": 60,
        # Supabase PostgreSQL requires TLS for production connections.
        "OPTIONS": {"sslmode": _db_query.get("sslmode", ["require"])[0]},
    }
}

# --------------------------------------------------------------------------
# Security hardening for production only
# --------------------------------------------------------------------------
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Keep teacher logins across browser restarts, while expiring sessions after
# 14 days of inactivity. Active sessions are refreshed on each request.
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_SAVE_EVERY_REQUEST = True

# Optional persistent media storage (Supabase Storage S3-compatible API).
# Configure all five AWS_* variables in Render to enable it. Without these,
# Django falls back to local disk, which is NOT persistent on Render free.
_media_env = (
    "AWS_STORAGE_BUCKET_NAME", "AWS_S3_ENDPOINT_URL", "AWS_S3_REGION_NAME",
    "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
)
if all(os.environ.get(key) for key in _media_env):
    INSTALLED_APPS = [*INSTALLED_APPS, "storages"]
    STORAGES = {
        **STORAGES,
        "default": {"BACKEND": "storages.backends.s3.S3Storage"},
    }
    AWS_STORAGE_BUCKET_NAME = os.environ["AWS_STORAGE_BUCKET_NAME"]
    AWS_S3_ENDPOINT_URL = os.environ["AWS_S3_ENDPOINT_URL"].rstrip("/")
    AWS_S3_REGION_NAME = os.environ["AWS_S3_REGION_NAME"]
    AWS_ACCESS_KEY_ID = os.environ["AWS_ACCESS_KEY_ID"]
    AWS_SECRET_ACCESS_KEY = os.environ["AWS_SECRET_ACCESS_KEY"]
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = False
    AWS_S3_ADDRESSING_STYLE = "path"
    AWS_S3_SIGNATURE_VERSION = "s3v4"
    AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age=86400"}
