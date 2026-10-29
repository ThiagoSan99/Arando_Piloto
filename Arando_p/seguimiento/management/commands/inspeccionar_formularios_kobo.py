"""Contrasta metadatos del formulario con configuración local; no lee respuestas."""
import ast
from datetime import date
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from seguimiento.kobo_client import KoboClient
from seguimiento.models import AsignacionDocenteCLEI, FormularioKobo, MatriculaCLEI, FormatoRegistroKobo


class Command(BaseCommand):
    help = "Inspecciona códigos precargados y cantidades de matrículas, sin leer ni importar respuestas."

    def add_arguments(self, parser):
        parser.add_argument("--formulario-uid", action="append", required=True, dest="formularios")
        parser.add_argument("--fecha")

    def handle(self, *args, **options):
        try:
            fecha = date.fromisoformat(options["fecha"]) if options["fecha"] else timezone.localdate(
                timezone=ZoneInfo("America/Bogota")
            )
        except ValueError as error:
            raise CommandError("Fecha no válida; usa YYYY-MM-DD.") from error

        for uid in dict.fromkeys(options["formularios"]):
            self.stdout.write(f"UID: {uid}; fecha de validación: {fecha}")
            try:
                contenido = KoboClient(formulario_uid=uid).obtener_formulario().get("content", {})
            except Exception as error:
                raise CommandError(f"No fue posible consultar metadatos: {type(error).__name__}") from error
            campos = {campo.get("name"): campo for campo in contenido.get("survey", [])}
            try:
                marcador = ast.literal_eval(campos.get("formato_registro", {}).get("calculation", "'INDIVIDUAL'"))
            except (ValueError, SyntaxError, TypeError):
                raise CommandError("No se pudo verificar el marcador de formato precargado.")
            grupal = marcador == FormatoRegistroKobo.GRUPAL_V1
            if grupal and {"codigo_estudiante", "estado_asistencia"} & campos.keys():
                raise CommandError("El contrato grupal no debe mezclar campos individuales.")
            esperados = {"codigo_docente", "codigo_institucion", "codigo_aula", "clei",
                         "fecha_sesion", "hora_inicio", "hora_fin"}
            if not grupal:
                esperados |= {"codigo_estudiante", "estado_asistencia"}
            if not esperados.issubset(campos):
                raise CommandError("Faltan campos del contrato individual: " + ", ".join(sorted(esperados - campos.keys())))
            contexto = {}
            for campo in ("codigo_docente", "codigo_institucion", "codigo_aula", "clei"):
                try:
                    valor = ast.literal_eval(campos[campo].get("calculation", ""))
                except (ValueError, SyntaxError, TypeError):
                    raise CommandError(f"No se puede verificar {campo} como constante precargada.")
                if not isinstance(valor, str) or not valor:
                    raise CommandError(f"El campo {campo} no tiene un código de texto precargado.")
                contexto[campo] = valor
                self.stdout.write(f"{campo}: {valor}")
            vinculo = FormularioKobo.objects.filter(formulario_uid=uid).first()
            if grupal:
                if vinculo is None or vinculo.formato != FormatoRegistroKobo.GRUPAL_V1:
                    raise CommandError("Configura el UID como GRUPAL_V1 y registra sus campos de asistencia.")
                mapas = list(vinculo.campos_asistencia.select_related("estudiante"))
                recibidos = {nombre for nombre in campos if nombre and nombre.startswith("asistencia_")}
                if not mapas or recibidos != {mapa.campo for mapa in mapas}:
                    raise CommandError("Los campos del formulario no coinciden con el mapeo autorizado.")
                for nombre in recibidos:
                    campo = campos[nombre]
                    lista = campo.get("select_from_list_name")
                    estados = {fila.get("name") for fila in contenido.get("choices", []) if fila.get("list_name") == lista}
                    if campo.get("type") != "select_one" or estados != {"PRESENTE", "AUSENTE"}:
                        raise CommandError("Cada asistencia grupal debe ofrecer PRESENTE/AUSENTE.")
                opciones = [mapa.estudiante.codigo for mapa in mapas]
            else:
                selector = campos["codigo_estudiante"]
                if selector.get("type") != "select_one":
                    raise CommandError("Este diagnóstico espera un selector de estudiante por envío.")
                lista = selector.get("select_from_list_name")
                opciones = [fila.get("name") for fila in contenido.get("choices", []) if fila.get("list_name") == lista]
                if not lista or not opciones or any(not isinstance(codigo, str) or not codigo for codigo in opciones):
                    raise CommandError("No se pudo identificar un listado válido de códigos de estudiantes.")
            if len(opciones) != len(set(opciones)):
                raise CommandError("El selector contiene códigos de estudiante repetidos.")
            vigencia = Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fecha)
            matriculados = set(MatriculaCLEI.objects.filter(
                aula__codigo_kobo=contexto["codigo_aula"], clei__codigo=contexto["clei"],
                aula__institucion__codigo_kobo=contexto["codigo_institucion"],
                estudiante__aula__codigo_kobo=contexto["codigo_aula"], estudiante__clei__codigo=contexto["clei"],
                estado="EN_CURSO", fecha_inicio__lte=fecha,
            ).filter(vigencia).values_list("estudiante__codigo", flat=True))
            asignaciones = AsignacionDocenteCLEI.objects.filter(
                docente__codigo=contexto["codigo_docente"], aula__codigo_kobo=contexto["codigo_aula"],
                clei__codigo=contexto["clei"], activa=True, fecha_inicio__lte=fecha,
            ).filter(vigencia).count()
            estado_vinculo = "no registrada" if vinculo is None else ("activa" if vinculo.activo else "inactiva")
            self.stdout.write(f"Vinculación local: {estado_vinculo}")
            if vinculo and any((vinculo.docente.codigo != contexto["codigo_docente"],
                               vinculo.aula.codigo_kobo != contexto["codigo_aula"],
                               vinculo.clei.codigo != contexto["clei"],
                               vinculo.aula.institucion.codigo_kobo != contexto["codigo_institucion"])):
                raise CommandError("La vinculación existente contradice los códigos precargados.")
            self.stdout.write(f"Asignaciones vigentes: {asignaciones}")
            etiqueta = "Estudiantes por envío grupal" if grupal else "Opciones de estudiante"
            self.stdout.write(f"{etiqueta}: {len(opciones)}; con matrícula compatible: {len(set(opciones) & matriculados)}")
            faltantes = len(set(opciones) - matriculados)
            self.stdout.write(f"Opciones sin matrícula compatible: {faltantes}")
            self.stdout.write("Modo: una sesión con varias asistencias por envío." if grupal else
                              "Modo: un estudiante por envío; varios envíos pueden compartir una sesión.")
            if faltantes or asignaciones != 1:
                self.stderr.write("Hay estudiantes sin matrícula o falta una asignación vigente para la fecha consultada.")
