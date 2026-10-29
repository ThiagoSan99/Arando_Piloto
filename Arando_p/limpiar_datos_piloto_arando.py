
import os
import sys
import argparse

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings"
)

import django
django.setup()

from django.db import connection, transaction

from seguimiento.models import (
    Proyecto,
    Departamento,
    Zona,
    Institucion,
    Aula,
    CLEI,
    Docente,
    Estudiante,
    Horario,
    MatriculaCLEI,
    AsignacionDocenteCLEI,
    SesionClase,
    Asistencia,
    Alerta,
    CasoAlerta,
    Seguimiento,
    RevalidacionAsistencia,
    RegistroImportacionKobo,
)

# Registros operativos que se eliminarán
BORRAR = [
    Seguimiento,
    RevalidacionAsistencia,
    RegistroImportacionKobo,
    Alerta,
    CasoAlerta,
    Asistencia,
    SesionClase,
]

# Registros institucionales que se conservarán
CONSERVAR = [
    Proyecto,
    Departamento,
    Zona,
    Institucion,
    Aula,
    CLEI,
    Docente,
    Estudiante,
    Horario,
    MatriculaCLEI,
    AsignacionDocenteCLEI,
]


def mostrar_conteos(titulo, modelos):
    print(f"\n{titulo}")
    print("-" * 45)

    for modelo in modelos:
        print(
            f"{modelo.__name__}: "
            f"{modelo.objects.count()}"
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true"
    )
    args = parser.parse_args()

    nombre_bd = connection.settings_dict["NAME"]

    print("Base de datos:", nombre_bd)

    if nombre_bd != "arando_db":
        sys.exit(
            "Cancelado: la base de datos no es arando_db."
        )

    mostrar_conteos(
        "REGISTROS QUE SE ELIMINARAN",
        BORRAR
    )

    mostrar_conteos(
        "REGISTROS QUE SE CONSERVARAN",
        CONSERVAR
    )

    if not args.apply:
        print(
            "\nMODO VISTA PREVIA: "
            "No se eliminó ningún registro."
        )
        return

    print(
        "\nADVERTENCIA: se eliminarán los "
        "registros operativos del piloto."
    )

    confirmacion = input(
        "Escribe ELIMINAR DATOS PILOTO: "
    ).strip()

    if confirmacion != "ELIMINAR DATOS PILOTO":
        print("Operación cancelada.")
        return

    with transaction.atomic():

        conteos_originales = {
            modelo: modelo.objects.count()
            for modelo in CONSERVAR
        }

        for modelo in BORRAR:
            eliminados, _ = modelo.objects.all().delete()

            print(
                f"{modelo.__name__}: "
                f"{eliminados} eliminaciones"
            )

        # Verificar que los registros
        # institucionales permanezcan intactos
        for modelo, cantidad in conteos_originales.items():

            if modelo.objects.count() != cantidad:
                raise RuntimeError(
                    "Se detectó un cambio inesperado "
                    f"en {modelo.__name__}. "
                    "La transacción será revertida."
                )

    print("\nLIMPIEZA COMPLETADA CORRECTAMENTE")

    mostrar_conteos(
        "REGISTROS OPERATIVOS RESTANTES",
        BORRAR
    )


if __name__ == "__main__":
    main()
