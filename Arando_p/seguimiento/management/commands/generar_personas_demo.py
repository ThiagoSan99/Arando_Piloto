
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from seguimiento.models import (
    Institucion,
    Aula,
    CLEI,
    Docente,
    Estudiante,
)


class Command(BaseCommand):
    help = "Genera 4 docentes y 20 estudiantes ficticios para Arando."

    @transaction.atomic
    def handle(self, *args, **options):

        # Cuatro instituciones de demostración
        codigos_instituciones = [
            "DEMO-NAR-Z1-I1",
            "DEMO-NAR-Z2-I1",
            "DEMO-CAU-Z1-I1",
            "DEMO-PUT-Z1-I1",
        ]

        # Verificar que las instituciones y aulas existan
        instituciones = []
        aulas = []

        for codigo in codigos_instituciones:
            try:
                institucion = Institucion.objects.get(
                    codigo_kobo=codigo
                )

                aula = Aula.objects.get(
                    codigo_kobo=f"{codigo}-A1",
                    institucion=institucion
                )

            except (Institucion.DoesNotExist, Aula.DoesNotExist):
                raise CommandError(
                    f"Falta la institución o el aula: {codigo}. "
                    "Ejecuta primero generar_datos_demo."
                )

            instituciones.append(institucion)
            aulas.append(aula)

        # CLEI para distribuir los estudiantes
        clei_iii, _ = CLEI.objects.get_or_create(
            codigo="III",
            defaults={
                "nombre": "CLEI III",
                "descripcion": "Nivel para demostración",
                "activo": True,
            }
        )

        clei_iv, _ = CLEI.objects.get_or_create(
            codigo="IV",
            defaults={
                "nombre": "CLEI IV",
                "descripcion": "Nivel para demostración",
                "activo": True,
            }
        )

        docentes_creados = 0
        estudiantes_creados = 0

        for i in range(4):

            docente, creado = Docente.objects.get_or_create(
                codigo=f"DOC-DEMO-{i+1:03d}",
                defaults={
                    "nombres": "Docente",
                    "apellidos": f"Demo {i+1}",
                    "correo": f"docente.demo{i+1}@example.com",
                    "telefono": f"30000000{i+1:02d}",
                    "institucion": instituciones[i],
                    "activo": True,
                }
            )

            if creado:
                docentes_creados += 1

            # Cinco estudiantes por docente/institución
            for j in range(5):
                numero = i * 5 + j + 1

                clei = clei_iii if j < 3 else clei_iv

                estudiante, creado = Estudiante.objects.get_or_create(
                    codigo=f"EST-DEMO-{numero:03d}",
                    defaults={
                        "aula": aulas[i],
                        "clei": clei,
                        "fecha_ingreso": date(2026, 9, 1),
                    }
                )

                if creado:
                    estudiantes_creados += 1

        self.stdout.write(
            f"Docentes creados: {docentes_creados}"
        )

        self.stdout.write(
            f"Estudiantes creados: {estudiantes_creados}"
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Datos ficticios generados correctamente."
            )
        )
