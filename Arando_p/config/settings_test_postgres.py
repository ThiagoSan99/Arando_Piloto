"""Pruebas en una base PostgreSQL nueva y temporal; correo solo en memoria."""

from uuid import uuid4

from . import settings as piloto
from .settings_test import *  # noqa: F403


# La conexión de mantenimiento usa postgres; nunca ejecuta las pruebas en arando_db.
# Django crea y elimina exclusivamente la base con este nombre aleatorio.
DATABASES = {
    "default": {
        **piloto.DATABASES["default"],
        "NAME": "postgres",
        "TEST": {"NAME": f"test_arando_sesiones_{uuid4().hex}"},
    },
}
