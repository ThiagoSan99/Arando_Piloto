"""Limpieza delimitada de datos de prueba. La ejecución predeterminada solo muestra un plan."""

import hashlib
import json
from datetime import date

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, connection, transaction
from django.db.migrations.loader import MigrationLoader
from django.db.models import Q


class Command(BaseCommand):
    help = "Previsualiza o limpia sesiones de prueba de un docente/aula/CLEI explícitos."

    def add_arguments(self, parser):
        parser.add_argument("--docente", required=True)
        parser.add_argument("--aula", required=True, help="Código Kobo del aula.")
        parser.add_argument("--clei", required=True)
        parser.add_argument("--desde", help="Fecha inclusiva YYYY-MM-DD.")
        parser.add_argument("--hasta", help="Fecha inclusiva YYYY-MM-DD.")
        parser.add_argument("--incluir-horarios", action="store_true")
        parser.add_argument("--reiniciar-alertas", action="store_true")
        parser.add_argument("--permitir-reimportacion", action="store_true")
        parser.add_argument("--ejecutar", action="store_true")
        parser.add_argument("--confirmar-base")
        parser.add_argument("--confirmar-plan", help="Huella mostrada por la vista previa.")

    def modelos_aplicados(self):
        # Permite limpiar el piloto antes de 0024–0026 si su histórico impide migrar.
        loader = MigrationLoader(connection)
        aplicadas = sorted(
            nodo for nodo in loader.applied_migrations if nodo[0] == "seguimiento"
        )
        if not aplicadas or aplicadas[-1][1] < "0022_casoalerta":
            raise CommandError("La limpieza requiere como mínimo seguimiento.0022 aplicada.")
        apps = loader.project_state([aplicadas[-1]]).apps
        nombres = (
            "SesionClase", "Horario", "Asistencia", "RegistroImportacionKobo",
            "RevalidacionAsistencia", "Seguimiento", "Alerta", "CasoAlerta",
            "Docente", "Aula", "CLEI",
        )
        modelos = {nombre: apps.get_model("seguimiento", nombre) for nombre in nombres}
        try:
            modelos["DetalleImportacionKobo"] = apps.get_model("seguimiento", "DetalleImportacionKobo")
        except LookupError:
            pass
        return modelos

    def planificar(self, modelos, opciones):
        try:
            docente = modelos["Docente"].objects.get(codigo=opciones["docente"])
            aula = modelos["Aula"].objects.get(codigo_kobo=opciones["aula"])
            clei = modelos["CLEI"].objects.get(codigo=opciones["clei"])
        except ObjectDoesNotExist as error:
            raise CommandError("No existe el docente, aula o CLEI indicado.") from error
        if docente.institucion_id != aula.institucion_id:
            raise CommandError("Docente y aula no pertenecen a la misma institución.")

        grupo = {"docente_id": docente.pk, "aula_id": aula.pk, "clei_id": clei.pk}
        sesiones = modelos["SesionClase"].objects.all()
        campos = {campo.name for campo in modelos["SesionClase"]._meta.fields}
        for campo, valor in grupo.items():
            filtro = Q(**{f"horario__{campo}": valor})
            if campo.removesuffix("_id") in campos:
                filtro = Q(**{campo: valor}) | (Q(**{campo: None}) & filtro)
            sesiones = sesiones.filter(filtro)
        for opcion, lookup in (("desde", "fecha__gte"), ("hasta", "fecha__lte")):
            if opciones[opcion]:
                sesiones = sesiones.filter(**{lookup: opciones[opcion]})

        ids = {"SesionClase": sorted(sesiones.values_list("pk", flat=True))}
        asistencias = modelos["Asistencia"].objects.filter(sesion_id__in=ids["SesionClase"])
        ids["Asistencia"] = sorted(asistencias.values_list("pk", flat=True))
        estudiantes = sorted(set(asistencias.values_list("estudiante_id", flat=True)))
        bloqueos = []
        filtro_importacion = Q(asistencia_id__in=ids["Asistencia"])
        if "DetalleImportacionKobo" in modelos:
            filtro_importacion |= Q(detalles__asistencia_id__in=ids["Asistencia"])
        ids["RegistroImportacionKobo"] = sorted(modelos["RegistroImportacionKobo"].objects.filter(
            filtro_importacion
        ).values_list("pk", flat=True).distinct())
        if "DetalleImportacionKobo" in modelos:
            detalles = modelos["DetalleImportacionKobo"].objects.filter(importacion_id__in=ids["RegistroImportacionKobo"])
            ids["DetalleImportacionKobo"] = sorted(detalles.values_list("pk", flat=True))
            if detalles.exclude(asistencia_id__in=ids["Asistencia"]).exists():
                bloqueos.append("Una importación grupal incluye asistencias fuera del alcance; no se puede limpiar parcialmente.")
        ids["RevalidacionAsistencia"] = sorted(
            modelos["RevalidacionAsistencia"].objects.filter(
                asistencia_id__in=ids["Asistencia"]
            ).values_list("pk", flat=True)
        )
        alertas = modelos["Alerta"].objects.filter(estudiante_id__in=estudiantes)
        casos = modelos["CasoAlerta"].objects.filter(estudiante_id__in=estudiantes)
        if alertas.exists() or casos.exists():
            if not opciones["reiniciar_alertas"]:
                bloqueos.append("Hay alertas/casos: revisa el plan con --reiniciar-alertas.")
            elif modelos["Asistencia"].objects.filter(
                estudiante_id__in=estudiantes
            ).exclude(pk__in=ids["Asistencia"]).exists():
                bloqueos.append(
                    "Hay asistencias del estudiante fuera del alcance; no se puede reiniciar su historial global."
                )
        ids["Alerta"] = sorted(alertas.values_list("pk", flat=True))
        ids["CasoAlerta"] = sorted(casos.values_list("pk", flat=True))
        ids["Seguimiento"] = sorted(
            modelos["Seguimiento"].objects.filter(alerta_id__in=ids["Alerta"]).values_list("pk", flat=True)
        )
        ids["Horario"] = []
        if opciones["incluir_horarios"]:
            horarios = modelos["Horario"].objects.filter(**grupo)
            utilizados = modelos["SesionClase"].objects.exclude(
                pk__in=ids["SesionClase"]
            ).filter(horario_id__in=horarios.values("pk")).values("horario_id")
            ids["Horario"] = sorted(horarios.exclude(pk__in=utilizados).values_list("pk", flat=True))

        # La huella incluye valores, no solo IDs: un cambio de estado/relaciones
        # posterior a la vista previa obliga a revisar el plan nuevamente.
        filas = {
            nombre: list(modelos[nombre].objects.filter(pk__in=claves).order_by("pk").values())
            for nombre, claves in ids.items()
        }
        contenido = {
            "base": connection.settings_dict["NAME"],
            "host": connection.settings_dict.get("HOST"),
            "port": connection.settings_dict.get("PORT"),
            "opciones": {clave: opciones[clave] for clave in (
                "docente", "aula", "clei", "desde", "hasta", "incluir_horarios",
                "reiniciar_alertas", "permitir_reimportacion",
            )},
            "filas": filas, "grupo": grupo, "bloqueos": bloqueos,
        }
        huella = hashlib.sha256(json.dumps(
            contenido, sort_keys=True, default=str, ensure_ascii=True,
        ).encode()).hexdigest()
        return ids, bloqueos, huella

    def handle(self, *args, **opciones):
        try:
            for campo in ("desde", "hasta"):
                if opciones[campo]:
                    opciones[campo] = date.fromisoformat(opciones[campo])
        except ValueError as error:
            raise CommandError("Usa fechas válidas con formato YYYY-MM-DD.") from error
        if opciones["desde"] and opciones["hasta"] and opciones["desde"] > opciones["hasta"]:
            raise CommandError("La fecha desde no puede ser posterior a hasta.")

        try:
            with transaction.atomic():
                modelos = self.modelos_aplicados()
                if opciones["ejecutar"]:
                    if str(connection.settings_dict["NAME"]) != opciones["confirmar_base"]:
                        raise CommandError("--confirmar-base debe coincidir con la base de datos configurada.")
                    if connection.vendor == "postgresql":
                        tablas = [modelos[nombre]._meta.db_table for nombre in (
                            "SesionClase", "Horario", "Asistencia", "RegistroImportacionKobo",
                            "RevalidacionAsistencia", "Seguimiento", "Alerta", "CasoAlerta",
                        )]
                        if "DetalleImportacionKobo" in modelos:
                            tablas.append(modelos["DetalleImportacionKobo"]._meta.db_table)
                        tablas.sort()
                        with connection.cursor() as cursor:
                            cursor.execute("SET LOCAL lock_timeout = '5s'")
                            cursor.execute("LOCK TABLE " + ", ".join(
                                connection.ops.quote_name(tabla) for tabla in tablas
                            ) + " IN SHARE ROW EXCLUSIVE MODE")

                ids, bloqueos, huella = self.planificar(modelos, opciones)
                self.stdout.write(f"Base: {connection.settings_dict['NAME']}")
                for nombre, claves in ids.items():
                    accion = "eliminar"
                    if nombre == "RegistroImportacionKobo" and not opciones["permitir_reimportacion"]:
                        accion = "conservar marca y desvincular asistencia"
                    if nombre in ("Alerta", "CasoAlerta", "Seguimiento") and not opciones["reiniciar_alertas"]:
                        accion = "dependencia que bloquea la limpieza"
                    self.stdout.write(f"{nombre}: {len(claves)} ({accion})")
                self.stdout.write(f"Huella del plan: {huella}")
                for bloqueo in bloqueos:
                    self.stdout.write(f"BLOQUEO: {bloqueo}")
                if not opciones["ejecutar"]:
                    self.stdout.write("VISTA PREVIA: no se modificó ningún registro.")
                    return
                if bloqueos:
                    raise CommandError("El plan tiene bloqueos. No se modificó ningún registro.")
                if huella != opciones["confirmar_plan"]:
                    raise CommandError("La huella no coincide. Genera y revisa una nueva vista previa.")

                importaciones = modelos["RegistroImportacionKobo"].objects.filter(
                    pk__in=ids["RegistroImportacionKobo"]
                )
                if opciones["permitir_reimportacion"]:
                    importaciones.delete()
                else:
                    importaciones.update(
                        asistencia_id=None, estado="EXISTENTE",
                        detalle_error="Limpieza de prueba: marca conservada para impedir reimportación.",
                    )
                orden = (["DetalleImportacionKobo"] if "DetalleImportacionKobo" in modelos else [])
                orden += ["RevalidacionAsistencia"]
                if opciones["reiniciar_alertas"]:
                    orden += ["Seguimiento", "Alerta", "CasoAlerta"]
                orden += ["Asistencia", "SesionClase", "Horario"]
                for nombre in orden:
                    modelos[nombre].objects.filter(pk__in=ids[nombre]).delete()
        except DatabaseError as error:
            raise CommandError(
                "La base rechazó la limpieza; se revirtió la operación. Detén sincronizadores y revisa dependencias."
            ) from error
        self.stdout.write(self.style.SUCCESS("Limpieza confirmada. Se conservaron personas y estructura institucional."))
