"""Registro por ausencia/destinatario y reintentos conservadores de SMTP."""
import smtplib

from django.conf import settings
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

from .models import Asistencia, CasoAlerta, IntentoNotificacionAusencia, NotificacionAusencia
from .notificaciones import construir_correo_caso_alerta


def motivo_no_pertinente(asistencia, caso):
    if asistencia is None:
        return "ASISTENCIA_RETIRADA"
    if asistencia.estado != "AUSENTE" or asistencia.sesion.estado != "REALIZADA":
        return "NO_ES_AUSENCIA_REALIZADA"
    if asistencia.revalidaciones.filter(decision="APROBADA").exists():
        return "AUSENCIA_REVALIDADA"
    if caso is None or caso.estudiante_id != asistencia.estudiante_id:
        return "SIN_CASO_CORRESPONDIENTE"
    if caso.estado == "CERRADA":
        return "CASO_CERRADO"
    return ""


def preparar_contenido(caso_id, asistencia_id, origen):
    correo = construir_correo_caso_alerta(caso_id, asistencia_id)
    if origen == "RECUPERACION_HISTORICA":
        correo["message"] = (
            "RECUPERACIÓN DE NOTIFICACIÓN DE AUSENCIA\n"
            "Este aviso corresponde a una ausencia registrada anteriormente. "
            "Los datos de seguimiento reflejan el estado al preparar este aviso.\n\n"
        ) + correo["message"]
    destinatarios = list(dict.fromkeys(valor.strip().casefold() for valor in correo["recipient_list"] if valor.strip()))
    try:
        for destinatario in destinatarios:
            if len(destinatario) > 254:
                raise ValidationError("Destinatario demasiado largo.")
            validate_email(destinatario)
    except ValidationError:
        destinatarios = []
    return correo, destinatarios


@transaction.atomic
def preparar_notificaciones(caso_id, asistencia_id, origen="AUTOMATICA"):
    asistencia = Asistencia.objects.select_related("sesion").get(pk=asistencia_id)
    caso = CasoAlerta.objects.get(pk=caso_id)
    if motivo_no_pertinente(asistencia, caso):
        return []
    correo, destinatarios = preparar_contenido(caso_id, asistencia_id, origen)
    registros = []
    for destinatario in destinatarios or [""]:
        notificacion, _ = NotificacionAusencia.objects.get_or_create(
            asistencia_referencia=asistencia_id, destinatario=destinatario,
            defaults={
                "asistencia": asistencia, "caso": caso, "asunto": correo["subject"],
                "cuerpo": correo["message"], "origen": origen,
                "estado": "PENDIENTE" if destinatario else "BLOQUEADA",
                "ultimo_error": "" if destinatario else "DESTINATARIOS_NO_CONFIGURADOS_O_INVALIDOS",
            },
        )
        registros.append(notificacion)
    return registros


def enviar_notificacion(notificacion_id):
    """Reclama antes del acceso a red; ENVIANDO/INCIERTA nunca se reenvían solas."""
    with transaction.atomic():
        notificacion = NotificacionAusencia.objects.select_for_update().get(pk=notificacion_id)
        if notificacion.estado not in ("PENDIENTE", "FALLIDA"):
            return notificacion.estado
        motivo = motivo_no_pertinente(notificacion.asistencia, notificacion.caso)
        if motivo:
            notificacion.estado = "OMITIDA"
            notificacion.ultimo_error = motivo
            notificacion.save(update_fields=["estado", "ultimo_error", "fecha_actualizacion"])
            return "OMITIDA"
        notificacion.estado = "ENVIANDO"
        notificacion.intentos += 1
        notificacion.ultimo_error = ""
        notificacion.save(update_fields=["estado", "intentos", "ultimo_error", "fecha_actualizacion"])
        intento = IntentoNotificacionAusencia.objects.create(
            notificacion=notificacion, numero=notificacion.intentos, estado="ENVIANDO", fase="CONEXION",
        )

    conexion = None
    fase = "CONEXION"
    estado = "FALLIDA"
    tipo_error = ""
    codigo = None
    try:
        conexion = mail.mailers.create_connection("default")
        conexion.open()
        mensaje = mail.EmailMessage(
            subject=notificacion.asunto, body=notificacion.cuerpo,
            from_email=settings.DEFAULT_FROM_EMAIL, to=[notificacion.destinatario],
            headers={"Message-ID": f"<arando.{notificacion.identificador}@arando.local>"},
        )
        fase = "ENVIO"
        cantidad = conexion.send_messages([mensaje])
        estado = "ENVIADA" if cantidad == 1 else "FALLIDA"
        tipo_error = "" if cantidad == 1 else "SMTP_SIN_ACEPTACION"
    except Exception as error:
        tipo_error = type(error).__name__
        codigo = getattr(error, "smtp_code", None)
        if not isinstance(codigo, int) or not 100 <= codigo <= 599:
            codigo = None
        rechazo_explicito = isinstance(error, (
            smtplib.SMTPResponseException, smtplib.SMTPRecipientsRefused,
        ))
        estado = "FALLIDA" if fase == "CONEXION" or rechazo_explicito else "INCIERTA"
    finally:
        if conexion is not None:
            try:
                conexion.close()
            except Exception:
                # Un fallo de QUIT no invalida una aceptación ya confirmada.
                pass

    with transaction.atomic():
        registro = NotificacionAusencia.objects.select_for_update().get(pk=notificacion_id)
        registro.estado = estado
        registro.ultimo_error = tipo_error
        if estado == "ENVIADA":
            registro.fecha_envio = timezone.now()
        registro.save(update_fields=["estado", "ultimo_error", "fecha_envio", "fecha_actualizacion"])
        intento.estado, intento.fase = estado, fase
        intento.tipo_error, intento.codigo_smtp = tipo_error, codigo
        intento.fecha_fin = timezone.now()
        intento.save(update_fields=["estado", "fase", "tipo_error", "codigo_smtp", "fecha_fin"])
    return estado


def enviar_pendientes_de_asistencia(asistencia_id):
    resultados = {}
    for pk in NotificacionAusencia.objects.filter(asistencia_referencia=asistencia_id).values_list("pk", flat=True):
        estado = enviar_notificacion(pk)
        resultados[estado] = resultados.get(estado, 0) + 1
    return resultados
