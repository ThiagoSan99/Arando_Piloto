
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from seguimiento.models import (
    Proyecto,
    Departamento,
    Zona,
    Institucion,
    Aula,
)


class Command(BaseCommand):
    help = "Genera datos ficticios para el dashboard Arando."

    @transaction.atomic
    def handle(self, *args, **options):

        try:
            proyecto = Proyecto.objects.get(
                nombre="Arando - Pruebas"
            )
        except Proyecto.DoesNotExist:
            raise CommandError(
                "No existe el proyecto Arando - Pruebas."
            )

        departamentos = [
            ("Nariño", "NAR"),
            ("Cauca", "CAU"),
            ("Putumayo", "PUT"),
        ]

        instituciones_creadas = 0
        aulas_creadas = 0

        for nombre_departamento, prefijo in departamentos:

            departamento, _ = Departamento.objects.get_or_create(
                nombre=nombre_departamento
            )

            for numero_zona in range(1, 3):

                zona, _ = Zona.objects.get_or_create(
                    proyecto=proyecto,
                    departamento=departamento,
                    nombre=f"Zona DEMO {numero_zona}",
                    defaults={
                        "descripcion": "Zona ficticia de demostración.",
                        "activa": True,
                    }
                )

                for numero_institucion in range(1, 3):

                    codigo_institucion = (
                        f"DEMO-{prefijo}-Z{numero_zona}"
                        f"-I{numero_institucion}"
                    )

                    institucion, creada = Institucion.objects.get_or_create(
                        codigo_kobo=codigo_institucion,
                        defaults={
                            "zona": zona,
                            "nombre": (
                                f"Institución DEMO {prefijo} "
                                f"Z{numero_zona}-I{numero_institucion}"
                            ),
                            "municipio": "Municipio ficticio",
                            "direccion": "Información de demostración",
                            "activa": True,
                        }
                    )

                    if creada:
                        instituciones_creadas += 1

                    for numero_aula in range(1, 3):

                        codigo_aula = (
                            f"{codigo_institucion}"
                            f"-A{numero_aula}"
                        )

                        aula, creada_aula = Aula.objects.get_or_create(
                            codigo_kobo=codigo_aula,
                            defaults={
                                "institucion": institucion,
                                "nombre": f"Aula DEMO {numero_aula}",
                                "descripcion": (
                                    "Aula ficticia para el dashboard."
                                ),
                                "activa": True,
                            }
                        )

                        if creada_aula:
                            aulas_creadas += 1

        self.stdout.write(
            f"Instituciones creadas: {instituciones_creadas}"
        )

        self.stdout.write(
            f"Aulas creadas: {aulas_creadas}"
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Datos de instituciones y aulas preparados."
            )
        )
