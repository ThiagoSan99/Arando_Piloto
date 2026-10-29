
import os

from django.core.mail import send_mail

from .models import Alerta


def enviar_correo_alerta(alerta_id):
    """
    Envía una notificación de alerta de ausentismo
    al correo configurado para el prototipo Arando.
    """

    destinatarios = [
        correo.strip()
        for correo in os.environ.get(
            "ARANDO_ALERT_EMAIL", ""
        ).split(",")
        if correo.strip()
    ]

    if not destinatarios:
        raise ValueError(
            "No se ha configurado ARANDO_ALERT_EMAIL."
        )

    alerta = Alerta.objects.select_related(
        "estudiante"
    ).get(pk=alerta_id)

    asunto = (
        f"[ARANDO] Alerta {alerta.nivel} - "
        f"{alerta.estudiante.codigo}"
    )

    mensaje = (
        "SISTEMA ARANDO LA EDUCACIÓN\n"
        "Notificación de seguimiento académico\n\n"
        f"Código del estudiante: {alerta.estudiante.codigo}\n"
        f"Nivel de alerta: {alerta.nivel}\n"
        f"Ausencias acumuladas: {alerta.cantidad_ausencias}\n"
        f"Estado de la alerta: {alerta.estado}\n\n"
        "Se recomienda revisar la situación académica "
        "del estudiante y realizar el seguimiento correspondiente.\n\n"
        "Este mensaje corresponde a una prueba del "
        "prototipo Arando la Educación."
    )

    return send_mail(
        subject=asunto,
        message=mensaje,
        from_email=None,
        recipient_list=destinatarios,
        fail_silently=False
    )



def construir_correo_caso_alerta(caso_id, asistencia_id):
    """
    Construye el contenido de una notificación por cada nueva ausencia
    registrada desde KoboToolbox.

    Incluye:
    - Zona
    - Institución educativa
    - Aula
    - Código del estudiante
    - Fecha de la sesión
    - Identificador de asistencia
    - Nivel de riesgo actual
    - Ausencias históricas y efectivas
    - Estado administrativo del caso

    Esta función no crea casos de alerta,
    no modifica asistencias y no evita duplicados.
    La validación de duplicados debe realizarse
    en el proceso de sincronización de KoboToolbox.
    """

    import os

    from django.core.mail import send_mail
    from .models import CasoAlerta, Asistencia

    # 1. Obtener destinatarios configurados
    destinatarios = [
        correo.strip()
        for correo in os.environ.get(
            "ARANDO_ALERT_EMAIL", ""
        ).split(",")
        if correo.strip()
    ]

    # 2. Obtener el caso y su información institucional
    caso = CasoAlerta.objects.select_related(
        "estudiante__aula__institucion__zona"
    ).get(pk=caso_id)

    estudiante = caso.estudiante

    # 3. Obtener la asistencia que generó la notificación
    asistencia = Asistencia.objects.select_related(
        "sesion__aula__institucion__zona"
    ).get(pk=asistencia_id)
    aula = asistencia.sesion.aula
    institucion = aula.institucion
    zona = institucion.zona

    # Comprobar que la asistencia pertenece al estudiante
    if asistencia.estudiante_id != estudiante.id:
        raise ValueError(
            "La asistencia no pertenece al estudiante "
            "asociado al caso de alerta."
        )

    if asistencia.estado != "AUSENTE":
        raise ValueError(
            "Solo se pueden notificar asistencias AUSENTES."
        )

    # 4. Consultar el total histórico de ausencias
    ausencias_historicas = Asistencia.objects.filter(
        estudiante=estudiante,
        estado="AUSENTE",
        sesion__estado="REALIZADA"
    ).count()

    # 5. Obtener el riesgo actual del caso
    nivel = caso.nivel_actual or "SIN RIESGO"

    # 6. Obtener la fecha de la sesión
    fecha_sesion = asistencia.sesion.fecha.strftime(
        "%d/%m/%Y"
    )

    # 7. Construir asunto del correo
    asunto = (
        f"[ARANDO] Nueva ausencia - "
        f"Riesgo {nivel} - "
        f"{estudiante.codigo}"
    )

    # 8. Construir contenido del correo
    mensaje = (
        "ARANDO LA EDUCACIÓN\n"
        "NOTIFICACIÓN DE AUSENCIA ACADÉMICA\n"
        "========================================\n\n"

        "INFORMACIÓN INSTITUCIONAL\n\n"
        f"Zona: {zona.nombre}\n"
        f"Institución educativa: {institucion.nombre}\n"
        f"Aula: {aula.nombre}\n\n"

        "INFORMACIÓN DEL ESTUDIANTE\n\n"
        f"Código: {estudiante.codigo}\n"
        f"Fecha de la sesión: {fecha_sesion}\n"
        f"Hora de inicio: {asistencia.sesion.hora_inicio:%H:%M}\n"
        f"Hora de finalización: {asistencia.sesion.hora_fin:%H:%M}\n"
        f"ID de asistencia: {asistencia.id}\n\n"

        "ESTADO DE ALERTA ACADÉMICA\n\n"
        f"Nivel de riesgo actual: {nivel}\n"
        f"Ausencias históricas: {ausencias_historicas}\n"
        f"Ausencias efectivas: {caso.ausencias_efectivas}\n"
        f"Estado del caso: {caso.estado}\n\n"

        "ACCIÓN REQUERIDA\n\n"
        "Se ha registrado una nueva ausencia académica.\n"
        "Se solicita revisar la situación del estudiante, "
        "realizar el seguimiento correspondiente y "
        "registrar las acciones tomadas en el sistema.\n\n"

        "IMPORTANTE\n\n"
        "Las ausencias históricas incluyen los registros "
        "que posteriormente fueron revalidados. "
        "Las ausencias efectivas excluyen las "
        "revalidaciones aprobadas.\n\n"

        "========================================\n"
        "ARANDO LA EDUCACIÓN\n"
        "Sistema de Seguimiento Académico\n"
        "Notificación automática del prototipo Arando.\n"
    )

    return {"subject": asunto, "message": mensaje, "recipient_list": destinatarios}


def enviar_correo_caso_alerta(caso_id, asistencia_id):
    """Compatibilidad para llamadas individuales; el importador usa el registro persistente."""
    correo = construir_correo_caso_alerta(caso_id, asistencia_id)
    if not correo["recipient_list"]:
        raise ValueError("No hay destinatarios configurados en ARANDO_ALERT_EMAIL.")
    return send_mail(**correo, from_email=None, fail_silently=False)
