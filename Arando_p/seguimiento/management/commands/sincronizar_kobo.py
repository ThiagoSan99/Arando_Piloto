
from django.core.management.base import BaseCommand, CommandError

from seguimiento.services import sincronizar_asistencias_kobo
from seguimiento.kobo_client import KoboClient
from seguimiento.models import FormularioKobo


class Command(BaseCommand):
    help = "Sincroniza por defecto todos los formularios Kobo registrados y activos."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limite",
            type=int,
            default=100,
            help="Tamaño de cada página; se recorren todas las respuestas."
        )
        seleccion = parser.add_mutually_exclusive_group()
        seleccion.add_argument(
            "--formulario-uid", action="append", dest="formularios",
            help="UID de origen. Repite esta opción para consultar varios formularios.",
        )
        seleccion.add_argument(
            "--todos", action="store_true", help="Todos los registrados activos (comportamiento predeterminado).",
        )

    def handle(self, *args, **options):
        limite = options["limite"]

        if limite < 1:
            raise CommandError("El límite debe ser mayor que cero.")

        if options["formularios"]:
            formularios = list(dict.fromkeys(options["formularios"]))
            # Comprobar todo el lote antes de consultar respuestas de Kobo.
            for uid in formularios:
                configuracion = FormularioKobo.objects.filter(formulario_uid=uid).first()
                if configuracion is None and uid != KoboClient.LEGACY_FORM_UID:
                    raise CommandError(
                        f"Formulario {uid} sin grupo registrado. Usa configurar_formulario_kobo."
                    )
                if configuracion is not None and not configuracion.activo:
                    raise CommandError(f"El formulario {uid} está desactivado.")
        else:
            formularios = list(FormularioKobo.objects.filter(activo=True).values_list("formulario_uid", flat=True))
            if not formularios:
                raise CommandError("No hay formularios activos registrados. Usa configurar_formulario_kobo.")

        self.stdout.write("Iniciando sincronización con KoboToolbox...")
        self.stdout.write(f"Formularios seleccionados: {len(formularios)}")

        hubo_errores = False
        for uid in formularios:
            self.stdout.write(f"Formulario: {uid}")
            try:
                resumen = sincronizar_asistencias_kobo(limite=limite, formulario_uid=uid)
            except Exception as error:
                # No mostrar respuestas, credenciales ni texto arbitrario del servidor.
                hubo_errores = True
                self.stderr.write(f"Error de consulta/procesamiento: {type(error).__name__}")
                continue
            self.mostrar_resumen(resumen)
            hubo_errores = hubo_errores or bool(resumen["errores"])
            hubo_errores = hubo_errores or any(resumen.get(f"correos_{estado}", 0)
                                             for estado in ("fallidas", "inciertas", "bloqueadas"))

        if hubo_errores:
            raise CommandError("Hubo fallos de importación o correo; revisa los resúmenes. Las asistencias confirmadas se conservan.")
        self.stdout.write(self.style.SUCCESS("Sincronización finalizada correctamente."))

    def mostrar_resumen(self, resumen):
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
            f"Errores de importación: {len(resumen['errores'])}"
        )
        for estado in ("programadas", "aceptadas", "fallidas", "inciertas", "bloqueadas"):
            etiqueta = {"programadas": "programados", "aceptadas": "aceptados", "fallidas": "fallidos",
                        "inciertas": "inciertos", "bloqueadas": "bloqueados"}[estado]
            self.stdout.write(f"Correos {etiqueta}: {resumen.get(f'correos_{estado}', 0)}")

        if resumen["errores"]:
            for error in resumen["errores"]:
                self.stderr.write(str(error))
