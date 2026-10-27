
from django.core.management.base import BaseCommand, CommandError

from seguimiento.services import sincronizar_asistencias_kobo


class Command(BaseCommand):
    help = "Sincroniza las asistencias de KoboToolbox con PostgreSQL."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limite",
            type=int,
            default=100,
            help="Cantidad máxima de respuestas a consultar."
        )

    def handle(self, *args, **options):
        limite = options["limite"]

        if limite < 1:
            raise ValueError("El límite debe ser mayor que cero.")

        self.stdout.write("Iniciando sincronización con KoboToolbox...")

        resumen = sincronizar_asistencias_kobo(limite=limite)

        self.stdout.write("\nResumen de sincronización:")
        self.stdout.write(
            f"Respuestas consultadas: {resumen['respuestas_consultadas']}"
        )
        self.stdout.write(
            f"Asistencias creadas: {resumen['asistencias_creadas']}"
        )
        self.stdout.write(
            f"Envíos ya procesados: {resumen['envios_ya_procesados']}"
        )
        self.stdout.write(
            f"Asistencias existentes: {resumen['asistencias_existentes']}"
        )
        self.stdout.write(
            f"Errores: {len(resumen['errores'])}"
        )

        if resumen["errores"]:
            for error in resumen["errores"]:
                self.stderr.write(str(error))

            raise CommandError(
                "La sincronización terminó con "
                f"{len(resumen['errores'])} error(es)."
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Sincronización finalizada correctamente."
            )
        )
