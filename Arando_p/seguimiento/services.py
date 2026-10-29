from .models import Asistencia, Alerta
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from zoneinfo import ZoneInfo

import logging
logger = logging.getLogger(__name__)


from .notificaciones import enviar_correo_alerta

from .models import (CasoAlerta,
                     RevalidacionAsistencia,
                     MatriculaCLEI
)

def determinar_nivel_alerta(cantidad_ausencias):
    """
    Determina el nivel de alerta según
    la cantidad de ausencias acumuladas.
    """

    if cantidad_ausencias >= 3:
        return Alerta.Nivel.ROJA

    if cantidad_ausencias == 2:
        return Alerta.Nivel.AMARILLA

    if cantidad_ausencias == 1:
        return Alerta.Nivel.TEMPRANA

    return None


def contar_ausencias_historicas(estudiante):
    """
    Cuenta todas las ausencias históricas del estudiante,
    incluyendo las que fueron revalidadas.
    """

    return Asistencia.objects.filter(
        estudiante=estudiante,
        estado=Asistencia.Estado.AUSENTE,
        sesion__estado=SesionClase.Estado.REALIZADA
    ).count()


def contar_ausencias(estudiante):
    """
    Cuenta las ausencias efectivas del estudiante.

    Excluye las ausencias con revalidación aprobada.
    No reinicia el conteo al cerrar alertas.
    """

    return (
        Asistencia.objects.filter(
            estudiante=estudiante,
            estado=Asistencia.Estado.AUSENTE,
            sesion__estado=SesionClase.Estado.REALIZADA
        )
        .exclude(
            revalidaciones__decision=(
                RevalidacionAsistencia.Decision.APROBADA
            )
        )
        .count()
    )


def calcular_riesgo_actual(estudiante):
    """
    Calcula el riesgo académico vigente sin modificar
    ni eliminar las alertas históricas.
    """

    historicas = contar_ausencias_historicas(estudiante)
    efectivas = contar_ausencias(estudiante)

    nivel = determinar_nivel_alerta(efectivas)

    return {
        "estudiante": estudiante.codigo,
        "ausencias_historicas": historicas,
        "ausencias_revalidadas": historicas - efectivas,
        "ausencias_efectivas": efectivas,
        "nivel_riesgo_actual": nivel,
    }


@transaction.atomic
def generar_alerta_automatica(estudiante):
    """
    Genera una alerta a partir de las ausencias
    acumuladas de un estudiante.

    Evita duplicar alertas con el mismo nivel
    y la misma cantidad de ausencias.
    """

    ausencias = contar_ausencias(estudiante)
    nivel = determinar_nivel_alerta(ausencias)

    if nivel is None:
        return None, False

    alerta, creada = Alerta.objects.get_or_create(
        estudiante=estudiante,
        nivel=nivel,
        cantidad_ausencias=ausencias,
        defaults={
            "estado": Alerta.Estado.ABIERTA,
            "descripcion": (
                f"Alerta automática generada por "
                f"{ausencias} ausencia(s) registrada(s)."
            )
        }
    )

    return alerta, creada


from datetime import date, time
from django.core.exceptions import ValidationError

from .models import (
    Institucion,
    Aula,
    CLEI,
    Docente,
    Estudiante,
    SesionClase,
    Asistencia,
    FormularioKobo,
    AsignacionDocenteCLEI,
)


def validar_contexto_formulario_kobo(registro, formulario_uid):
    """Contrasta los códigos recibidos con la configuración del backend.

    Solo el formulario original conserva la compatibilidad sin vinculación.
    No acredita la identidad de quien tiene acceso al enlace de Kobo.
    """
    formulario = FormularioKobo.objects.select_related(
        "docente", "aula__institucion", "clei"
    ).filter(formulario_uid=formulario_uid).first()

    if formulario is None:
        if formulario_uid == KoboClient.LEGACY_FORM_UID:
            return None
        raise ValidationError(
            "El formulario Kobo no tiene un grupo autorizado configurado."
        )

    if not formulario.activo:
        raise ValidationError("El formulario Kobo está desactivado.")

    formulario.full_clean()
    if not all((
        formulario.docente.activo,
        formulario.aula.activa,
        formulario.aula.institucion.activa,
        formulario.clei.activo,
    )):
        raise ValidationError("El contexto institucional del formulario está inactivo.")

    esperados = {
        "codigo_docente": formulario.docente.codigo,
        "codigo_institucion": formulario.aula.institucion.codigo_kobo,
        "codigo_aula": formulario.aula.codigo_kobo,
        "clei": formulario.clei.codigo,
    }
    for campo, esperado in esperados.items():
        if not esperado or registro.get(campo) != esperado:
            raise ValidationError({
                campo: "El dato no corresponde al grupo autorizado del formulario."
            })

    return formulario


def validar_fecha_horas_kobo(registro):
    """Valida los valores completos y conserva la hora local enviada por Kobo."""
    try:
        fecha = date.fromisoformat(registro["fecha_sesion"])
    except (ValueError, TypeError):
        raise ValidationError({"fecha_sesion": "La fecha de sesión no es válida."})

    if fecha > timezone.localdate(timezone=ZoneInfo("America/Bogota")):
        raise ValidationError({"fecha_sesion": "No se admiten clases con fechas futuras."})

    horas = {}
    for campo in ("hora_inicio", "hora_fin"):
        valor = registro.get(campo)
        if campo == "hora_fin" and valor in (None, ""):
            horas[campo] = None
            continue
        try:
            # Kobo puede incluir segundos, fracciones y desplazamiento horario.
            # Los TimeField existentes almacenan la hora local sin zona.
            horas[campo] = time.fromisoformat(valor).replace(tzinfo=None)
        except (ValueError, TypeError):
            raise ValidationError({campo: "La hora de sesión no es válida."})

    if horas["hora_fin"] is not None and horas["hora_inicio"] >= horas["hora_fin"]:
        raise ValidationError({
            "hora_fin": "La hora de finalización debe ser posterior a la de inicio."
        })

    return fecha, horas["hora_inicio"], horas["hora_fin"]


def obtener_matricula_kobo(estudiante, aula, clei, fecha, bloquear=False):
    matriculas = MatriculaCLEI.objects.filter(
        estudiante=estudiante,
        aula=aula,
        clei=clei,
        estado=MatriculaCLEI.Estado.EN_CURSO,
        fecha_inicio__lte=fecha,
    ).filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fecha))
    if bloquear:
        matriculas = matriculas.select_for_update()
    matricula = matriculas.first()

    if matricula is None:
        raise ValidationError(
            "No se encontró una matrícula CLEI vigente para el estudiante, "
            "aula y fecha de la sesión."
        )
    return matricula


def validar_asistencia_kobo(registro, formulario_uid=None):
    """
    Valida una respuesta de KoboToolbox.

    Identifica los registros relacionados en PostgreSQL,
    pero NO crea ni modifica información.
    """

    campos_obligatorios = [
        "codigo_docente",
        "codigo_institucion",
        "codigo_aula",
        "clei",
        "fecha_sesion",
        "hora_inicio",
        "codigo_estudiante",
        "estado_asistencia",
    ]

    for campo in campos_obligatorios:
        if not registro.get(campo):
            raise ValidationError(
                f"Falta el campo obligatorio: {campo}"
            )

    formulario_uid = (
        formulario_uid if formulario_uid is not None else KoboClient.FORM_UID
    )
    formulario = validar_contexto_formulario_kobo(registro, formulario_uid)
    fecha, hora, hora_fin = validar_fecha_horas_kobo(registro)

    asignacion = None
    if formulario is not None:
        if hora_fin is None:
            raise ValidationError({"hora_fin": "Falta la hora de finalización."})
        asignacion = AsignacionDocenteCLEI.objects.filter(
            docente=formulario.docente,
            aula=formulario.aula,
            clei=formulario.clei,
            activa=True,
            fecha_inicio__lte=fecha,
        ).filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fecha)).first()
        if asignacion is None:
            raise ValidationError(
                "El docente no tiene una asignación activa y vigente "
                "para el grupo y la fecha de la sesión."
            )

    # Identificar institución y aula
    institucion = Institucion.objects.get(
        codigo_kobo=registro["codigo_institucion"]
    )

    aula = Aula.objects.get(
        codigo_kobo=registro["codigo_aula"],
        institucion=institucion
    )

    # Identificar CLEI, docente y estudiante
    clei = CLEI.objects.get(
        codigo=registro["clei"]
    )

    docente = Docente.objects.get(
        codigo=registro["codigo_docente"],
        institucion=institucion
    )

    estudiante = Estudiante.objects.get(
        codigo=registro["codigo_estudiante"],
        aula=aula,
        clei=clei
    )

    # Validar el estado recibido
    estado = registro["estado_asistencia"]

    if estado not in [
        Asistencia.Estado.PRESENTE,
        Asistencia.Estado.AUSENTE,
    ]:
        raise ValidationError(
            f"Estado de asistencia no permitido: {estado}"
        )

    # Identificar la sesión correspondiente
    sesiones = SesionClase.objects.filter(
        fecha=fecha,
        hora_inicio=hora,
        aula=aula,
        clei=clei,
        docente=docente,
    )
    sesion = sesiones.first()
    if sesion is None and formulario is None:
        # Sin hora final ni contexto autorizado no se inventa una clase histórica.
        raise SesionClase.DoesNotExist("No existe la sesión del formulario original.")

    permitidos = [SesionClase.Estado.REALIZADA]
    if formulario is not None:
        permitidos.append(SesionClase.Estado.PROGRAMADA)
    if sesion is not None and sesion.estado not in permitidos:
        raise ValidationError(
            "La sesión no está marcada como REALIZADA."
        )

    if sesion is not None and hora_fin is not None and sesion.hora_fin != hora_fin:
        raise ValidationError({
            "hora_fin": "La hora final no coincide con la sesión existente."
        })

    if formulario is not None:
        obtener_matricula_kobo(estudiante, aula, clei, fecha)

    # Comprobar si la asistencia ya existe
    asistencia_existente = Asistencia.objects.filter(
        estudiante=estudiante,
        sesion=sesion
    ).first() if sesion is not None else None

    if asistencia_existente:
        if asistencia_existente.estado != estado:
            raise ValidationError(
                "Conflicto: la asistencia existente tiene "
                "un estado diferente al enviado por Kobo."
            )

        resultado = "EXISTENTE"
    else:
        resultado = "NUEVA"

    return {
        "envio_id": registro.get("_id"),
        "estudiante_id": estudiante.id,
        "sesion_id": sesion.id if sesion is not None else None,
        "aula_id": aula.pk,
        "clei_id": clei.pk,
        "docente_id": docente.pk,
        "asignacion_id": asignacion.pk if asignacion is not None else None,
        "fecha": fecha,
        "hora_inicio": hora,
        "hora_fin": hora_fin,
        "estado": estado,
        "resultado": resultado,
    }


from .models import RegistroImportacionKobo
from .kobo_client import KoboClient


@transaction.atomic
def obtener_o_crear_sesion_validada(datos):
    """Servicio interno: recibe el resultado validado, con sus bloqueos adquiridos."""
    identidad = {campo: datos[campo] for campo in (
        "aula_id", "clei_id", "docente_id", "fecha", "hora_inicio"
    )}
    sesion = SesionClase.objects.select_for_update().filter(**identidad).first()
    creada = False
    if sesion is None:
        if datos["asignacion_id"] is None or datos["hora_fin"] is None:
            raise ValidationError("Crear una sesión requiere asignación y hora final.")
        candidata = SesionClase(
            **identidad, hora_fin=datos["hora_fin"],
            asignacion_id=datos["asignacion_id"], estado=SesionClase.Estado.REALIZADA,
        )
        candidata.full_clean(validate_unique=False, validate_constraints=False)
        try:
            with transaction.atomic():
                candidata.save(force_insert=True)
            sesion, creada = candidata, True
        except IntegrityError:
            # Una escritura concurrente puede haber ganado la clave única.
            # El savepoint mantiene utilizable la transacción exterior.
            sesion = SesionClase.objects.select_for_update().filter(**identidad).first()
            if sesion is None:
                raise

    if datos["hora_fin"] is not None and sesion.hora_fin != datos["hora_fin"]:
        raise ValidationError({"hora_fin": "La sesión existente tiene otra hora final."})
    if sesion.estado == SesionClase.Estado.PROGRAMADA and datos["asignacion_id"]:
        # El envío válido constituye la confirmación aprobada de clase impartida.
        sesion.estado = SesionClase.Estado.REALIZADA
        sesion.asignacion_id = datos["asignacion_id"]
        sesion.full_clean()
        sesion.save(update_fields=["estado", "asignacion", "fecha_actualizacion"])
    if sesion.estado != SesionClase.Estado.REALIZADA:
        raise ValidationError("La sesión cancelada o reprogramada no admite asistencia.")
    return sesion, creada


def procesar_respuesta_kobo(registro, formulario_uid=None):
    """Procesa un envío individual o grupal mediante el importador transaccional."""
    from .kobo_importador import procesar
    return procesar(registro, formulario_uid=formulario_uid)


def sincronizar_asistencias_kobo(limite=100, formulario_uid=None):
    """
    Sincroniza todas las respuestas de KoboToolbox.

    El parámetro limite controla el tamaño de cada página,
    no la cantidad total de respuestas procesadas.
    """

    cliente = KoboClient(formulario_uid=formulario_uid) if formulario_uid is not None else KoboClient()

    resumen = {
        "respuestas_consultadas": 0,
        "asistencias_creadas": 0,
        "envios_ya_procesados": 0,
        "asistencias_existentes": 0,
        "errores": []
    }

    for registro in cliente.iterar_respuestas(
        tamano_pagina=limite
    ):
        resumen["respuestas_consultadas"] += 1

        try:
            resultado = procesar_respuesta_kobo(
                registro, formulario_uid=cliente.FORM_UID
            )

            if not resultado["importacion_creada"]:
                resumen["envios_ya_procesados"] += 1
            else:
                resumen["asistencias_creadas"] += resultado["asistencias_creadas"]
                resumen["asistencias_existentes"] += resultado["asistencias_existentes"]
            for campo, cantidad in resultado.get("notificaciones", {}).items():
                clave = f"correos_{campo}"
                resumen[clave] = resumen.get(clave, 0) + cantidad

        except Exception as error:
            resumen["errores"].append({
                "envio_id": registro.get("_id"),
                "tipo_error": type(error).__name__
            })

    return resumen



def notificar_alerta_segura(alerta_id):
    """
    Envía el correo y registra cualquier fallo
    sin revertir la asistencia ya almacenada.
    """
    try:
        enviar_correo_alerta(alerta_id)
        logger.info(
            "Correo enviado para la alerta %s",
            alerta_id
        )

    except Exception:
        logger.exception(
            "No se pudo enviar el correo de la alerta %s",
            alerta_id
        )



def calcular_horas_presenciales(matricula):
    """
    Calcula las horas presenciales reconocidas
    para una matrícula CLEI.

    Se reconocen 5 horas por sesión REALIZADA cuando:
    - El estudiante estuvo PRESENTE.
    - La ausencia tiene una revalidación APROBADA.

    Cada sesión se contabiliza una sola vez.
    """

    asistencias_validas = Asistencia.objects.filter(
        matricula=matricula,
        sesion__estado=SesionClase.Estado.REALIZADA
    ).filter(
        Q(estado=Asistencia.Estado.PRESENTE)
        |
        Q(
            estado=Asistencia.Estado.AUSENTE,
            revalidaciones__decision=(
                RevalidacionAsistencia.Decision.APROBADA
            )
        )
    )

    sesiones_reconocidas = (
        asistencias_validas
        .values("sesion_id")
        .distinct()
        .count()
    )

    horas_cumplidas = sesiones_reconocidas * 5

    horas_requeridas = (
        matricula.clei.horas_presenciales_requeridas
    )

    porcentaje = (
        round(
            horas_cumplidas / horas_requeridas * 100,
            2
        )
        if horas_requeridas > 0
        else 0
    )

    horas_pendientes = max(
        horas_requeridas - horas_cumplidas,
        0
    )

    return {
        "matricula_id": matricula.id,
        "estudiante": matricula.estudiante.codigo,
        "clei": matricula.clei.codigo,
        "sesiones_reconocidas": sesiones_reconocidas,
        "horas_cumplidas": horas_cumplidas,
        "horas_requeridas": horas_requeridas,
        "horas_pendientes": horas_pendientes,
        "porcentaje_cumplimiento": porcentaje
    }


from .models import CasoAlerta


@transaction.atomic
def actualizar_caso_alerta(estudiante, crear_si_no_existe=False):
    """
    Recalcula el riesgo y actualiza el caso activo.

    - No elimina alertas históricas.
    - No reinicia las ausencias.
    - No reabre casos cerrados.
    - No envía correos.
    """

    # Bloquear el estudiante durante la actualización.
    estudiante = Estudiante.objects.select_for_update().get(
        pk=estudiante.pk
    )

    riesgo = calcular_riesgo_actual(estudiante)

    casos_activos = CasoAlerta.objects.filter(
        estudiante=estudiante,
        estado__in=[
            CasoAlerta.Estado.ABIERTA,
            CasoAlerta.Estado.EN_SEGUIMIENTO,
        ]
    )

    caso = casos_activos.first()

    # No crear un caso durante una simple consulta
    # o revalidación si ya no hay caso activo.
    if caso is None:

        if (
            not crear_si_no_existe
            or riesgo["nivel_riesgo_actual"] is None
        ):
            return None, False, False

        caso = CasoAlerta(
            estudiante=estudiante,
            nivel_actual=riesgo["nivel_riesgo_actual"],
            ausencias_efectivas=riesgo["ausencias_efectivas"],
            estado=CasoAlerta.Estado.ABIERTA,
            observaciones="Caso generado automáticamente."
        )

        caso.full_clean()
        caso.save()

        return caso, True, False

    # Actualizar únicamente si el riesgo ha cambiado.
    cambio = (
        caso.nivel_actual != riesgo["nivel_riesgo_actual"]
        or caso.ausencias_efectivas != riesgo["ausencias_efectivas"]
    )

    if cambio:
        caso.nivel_actual = riesgo["nivel_riesgo_actual"]
        caso.ausencias_efectivas = riesgo["ausencias_efectivas"]

        caso.full_clean()
        caso.save(
            update_fields=[
                "nivel_actual",
                "ausencias_efectivas",
                "fecha_actualizacion",
            ]
        )

    return caso, False, cambio


def notificar_caso_alerta_segura(caso_id, asistencia_id):
    """
    Envía el correo correspondiente a una nueva
    ausencia, sin interrumpir la sincronización
    si ocurre un error de correo.
    """

    import logging
    from .correo_persistente import enviar_pendientes_de_asistencia

    logger = logging.getLogger(__name__)

    try:
        return enviar_pendientes_de_asistencia(asistencia_id)

    except Exception:
        logger.exception(
            "Error al enviar notificación del caso %s "
            "por la asistencia %s.",
            caso_id,
            asistencia_id
        )
        return {"ERROR_INTERNO": 1}

