from datetime import date
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from seguimiento.kobo_client import KoboClient
from seguimiento.models import AsignacionDocenteCLEI, FormularioKobo, MatriculaCLEI, FormatoRegistroKobo


class Command(BaseCommand):
    help = "Diagnóstico local de recepción de un formulario, sin procesar respuestas ni modificar datos."

    def add_arguments(self, parser):
        parser.add_argument("--formulario-uid", default=KoboClient.FORM_UID)
        parser.add_argument("--fecha", help="Fecha de clase a verificar; por defecto hoy en Colombia.")

    def handle(self, *args, **options):
        try:
            fecha = date.fromisoformat(options["fecha"]) if options["fecha"] else timezone.localdate(
                timezone=ZoneInfo("America/Bogota")
            )
        except ValueError as error:
            raise CommandError("La fecha debe ser válida, en formato YYYY-MM-DD.") from error
        formulario = FormularioKobo.objects.select_related(
            "docente", "aula__institucion", "clei"
        ).filter(formulario_uid=options["formulario_uid"]).first()
        if formulario is None:
            raise CommandError(
                "El UID no está registrado. Cambiar .env no crea la vinculación: "
                "ejecuta configurar_formulario_kobo con docente, aula y CLEI existentes."
            )
        self.stdout.write(f"UID: {formulario.formulario_uid}")
        self.stdout.write(f"Docente: {formulario.docente.codigo}")
        self.stdout.write(f"Institución: {formulario.aula.institucion.codigo_kobo}")
        self.stdout.write(f"Aula: {formulario.aula.codigo_kobo}; CLEI: {formulario.clei.codigo}; fecha: {fecha}")
        problemas = []
        if not all((formulario.activo, formulario.docente.activo, formulario.aula.activa,
                    formulario.aula.institucion.activa, formulario.clei.activo)):
            problemas.append("El formulario o parte de su contexto institucional está inactivo.")
        if formulario.docente.institucion_id != formulario.aula.institucion_id:
            problemas.append("El docente y el aula pertenecen a instituciones diferentes.")
        if fecha > timezone.localdate(timezone=ZoneInfo("America/Bogota")):
            problemas.append("La fecha está en el futuro.")
        vigencia = Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fecha)
        asignaciones = AsignacionDocenteCLEI.objects.filter(
            docente=formulario.docente, aula=formulario.aula, clei=formulario.clei,
            activa=True, fecha_inicio__lte=fecha,
        ).filter(vigencia).count()
        matriculas = MatriculaCLEI.objects.filter(
            aula=formulario.aula, clei=formulario.clei, estado="EN_CURSO", fecha_inicio__lte=fecha,
            estudiante__aula=formulario.aula, estudiante__clei=formulario.clei,
        ).filter(vigencia).count()
        self.stdout.write(f"Asignaciones vigentes: {asignaciones}; matrículas compatibles vigentes: {matriculas}")
        self.stdout.write(f"Formato: {formulario.formato}")
        if formulario.formato == FormatoRegistroKobo.GRUPAL_V1:
            mapas = list(formulario.campos_asistencia.select_related("estudiante"))
            compatibles = MatriculaCLEI.objects.filter(
                aula=formulario.aula, clei=formulario.clei, estado="EN_CURSO", fecha_inicio__lte=fecha,
                estudiante_id__in=[mapa.estudiante_id for mapa in mapas],
                estudiante__aula=formulario.aula, estudiante__clei=formulario.clei,
            ).filter(vigencia).count()
            self.stdout.write(f"Campos de asistencia autorizados: {len(mapas)}; con matrícula compatible: {compatibles}")
            if not mapas or compatibles != len(mapas):
                problemas.append("La lista grupal está vacía o incluye estudiantes sin matrícula compatible.")
        if asignaciones != 1:
            problemas.append("Debe existir una asignación activa y vigente para ese docente y grupo.")
        if not matriculas:
            problemas.append("No hay estudiantes con matrícula compatible y vigente en ese grupo.")
        if problemas:
            for problema in problemas:
                self.stderr.write(problema)
            raise CommandError("La configuración local requiere correcciones.")
        self.stdout.write(self.style.SUCCESS(
            "Configuración local válida. Falta comprobar campos y estudiantes de cada envío; "
            "este diagnóstico no consulta Kobo ni garantiza entrega SMTP."
        ))
