import hashlib
import json
from collections import Counter

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from seguimiento.correo_persistente import (
    enviar_notificacion, motivo_no_pertinente, preparar_contenido, preparar_notificaciones,
)
from seguimiento.models import Asistencia, CasoAlerta, NotificacionAusencia


class Command(BaseCommand):
    help = "Previsualiza y reintenta correos pendientes/fallidos sin reimportar asistencias."

    def add_arguments(self, parser):
        grupo = parser.add_mutually_exclusive_group(required=True)
        grupo.add_argument("--asistencia-id", action="append", type=int, dest="asistencias")
        grupo.add_argument("--pendientes", action="store_true")
        parser.add_argument("--ejecutar", action="store_true")
        parser.add_argument("--confirmar-plan")
        parser.add_argument("--confirmar-fallos-historicos", action="store_true",
                            help="Confirma que los IDs sin registro de correo tuvieron entrega fallida conocida.")

    def construir_plan(self, ids):
        plan = []
        for pk in ids:
            asistencia = Asistencia.objects.select_related("sesion").filter(pk=pk).first()
            caso = CasoAlerta.objects.filter(
                estudiante_id=asistencia.estudiante_id if asistencia else None,
                estado__in=["ABIERTA", "EN_SEGUIMIENTO"],
            ).first()
            motivo = motivo_no_pertinente(asistencia, caso)
            registros = list(NotificacionAusencia.objects.filter(asistencia_referencia=pk).order_by("pk").values(
                "pk", "estado", "destinatario", "intentos", "fecha_actualizacion",
            ))
            correo, destinatarios = ({}, []) if motivo else preparar_contenido(caso.pk, pk, "RECUPERACION_HISTORICA")
            utiles = [registro for registro in registros if registro["destinatario"]]
            plan.append({
                "asistencia_id": pk, "caso_id": caso.pk if caso else None, "motivo": motivo,
                "registros": registros, "crear": destinatarios if not utiles and not motivo else [],
                "contenido": correo if not utiles and not motivo else {},
                "sin_auditoria_previa": not registros and not motivo,
                "configuracion_incompleta": not motivo and not utiles and not destinatarios,
                "sesion_id": asistencia.sesion_id if asistencia else None,
                "estado_asistencia": asistencia.estado if asistencia else None,
                "riesgo_actual": caso.nivel_actual if caso else None,
                "ausencias_efectivas": caso.ausencias_efectivas if caso else None,
            })
        datos = {"base": settings.DATABASES["default"]["NAME"],
                 "remitente": settings.DEFAULT_FROM_EMAIL, "plan": plan}
        huella = hashlib.sha256(json.dumps(datos, sort_keys=True, default=str).encode()).hexdigest()
        return plan, huella

    def handle(self, *args, **options):
        if options["pendientes"]:
            ids = sorted(set(NotificacionAusencia.objects.filter(
                estado__in=["PENDIENTE", "FALLIDA"]
            ).values_list("asistencia_referencia", flat=True)))
        else:
            ids = sorted(set(options["asistencias"]))
        plan, huella = self.construir_plan(ids)
        for fila in plan:
            estados = dict(Counter(registro["estado"] for registro in fila["registros"]))
            self.stdout.write(
                f"Asistencia {fila['asistencia_id']}; caso {fila['caso_id']}; "
                f"motivo: {fila['motivo'] or 'PERTINENTE'}; nuevos destinatarios: {len(fila['crear'])}; estados: {estados}"
            )
        self.stdout.write(f"Huella del plan: {huella}")
        if not options["ejecutar"]:
            self.stdout.write("VISTA PREVIA: no se registraron ni enviaron correos.")
            return
        if options["confirmar_plan"] != huella:
            raise CommandError("La huella no coincide. Revisa una nueva vista previa.")
        if any(fila["configuracion_incompleta"] for fila in plan):
            raise CommandError("Faltan destinatarios válidos. No se inició ningún envío.")
        if any(fila["sin_auditoria_previa"] and fila["crear"] for fila in plan) and not options["confirmar_fallos_historicos"]:
            raise CommandError("Se requiere --confirmar-fallos-historicos: no hay evidencia persistente de la entrega anterior.")
        resultados = Counter()
        for fila in plan:
            if fila["crear"]:
                preparar_notificaciones(fila["caso_id"], fila["asistencia_id"], origen="RECUPERACION_HISTORICA")
            for registro in NotificacionAusencia.objects.filter(asistencia_referencia=fila["asistencia_id"]).order_by("pk"):
                estado = enviar_notificacion(registro.pk)
                resultados[estado] += 1
                self.stdout.write(f"Notificación {registro.pk}; asistencia {fila['asistencia_id']}: {estado}")
        self.stdout.write(f"Resultado del control: {dict(resultados)}")
        if any(resultados[estado] for estado in ("FALLIDA", "INCIERTA", "ENVIANDO", "BLOQUEADA")):
            raise CommandError("Hay notificaciones sin aceptación SMTP confirmada. Revisa su estado antes de reintentar.")
