"""Pruebas locales aisladas; no utilizan la base PostgreSQL del piloto.

No usar para comprobar concurrencia ni comportamientos propios de PostgreSQL.
"""

from .settings import *  # noqa: F403


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    },
}

MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.locmem.EmailBackend",
    },
}
