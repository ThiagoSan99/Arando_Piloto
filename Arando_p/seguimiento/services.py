from .models import Asistencia, Alerta
from django.db import transaction
from django.db.models import Q

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
)


def validar_asistencia_kobo(registro):
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
    fecha = date.fromisoformat(registro["fecha_sesion"])

    hora = time.fromisoformat(
        registro["hora_inicio"][:8]
    )

    sesion = SesionClase.objects.get(
        fecha=fecha,
        hora_inicio=hora,
        horario__aula=aula,
        horario__clei=clei,
        horario__docente=docente
    )

    if sesion.estado != SesionClase.Estado.REALIZADA:
        raise ValidationError(
            "La sesión no está marcada como REALIZADA."
        )

    # Comprobar si la asistencia ya existe
    asistencia_existente = Asistencia.objects.filter(
        estudiante=estudiante,
        sesion=sesion
    ).first()

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
        "sesion_id": sesion.id,
        "estado": estado,
        "resultado": resultado,
    }


from .models import RegistroImportacionKobo
from .kobo_client import KoboClient


@transaction.atomic
def procesar_respuesta_kobo(registro):
    """
    Procesa una respuesta de KoboToolbox.

    - Valida los datos recibidos.
    - Evita asistencias duplicadas.
    - Crea asistencias nuevas.
    - Registra la trazabilidad de la importación.
    - Actualiza el caso único de alerta.
    - Notifica por cada nueva ausencia.
    """

    formulario_uid = KoboClient.FORM_UID
    envio_id = registro.get("_id")

    if envio_id is None:
        raise ValueError(
            "La respuesta no contiene el identificador _id."
        )

    envio_id = int(envio_id)

    # 1. Verificar si el envío ya fue procesado
    importacion = RegistroImportacionKobo.objects.filter(
        formulario_uid=formulario_uid,
        envio_id=envio_id
    ).first()

    if importacion:
        return {
            "envio_id": envio_id,
            "estado": importacion.estado,
            "asistencia_id": importacion.asistencia_id,
            "importacion_creada": False,
            "asistencia_creada": False,
        }

    # 2. Validar los datos recibidos
    resultado = validar_asistencia_kobo(registro)

    # 3. Bloquear al estudiante durante la transacción
    estudiante = Estudiante.objects.select_for_update().get(
        pk=resultado["estudiante_id"]
    )

    sesion = SesionClase.objects.get(
        pk=resultado["sesion_id"]
    )

    estado_recibido = resultado["estado"]

    # 4. Comprobar nuevamente después del bloqueo
    importacion = RegistroImportacionKobo.objects.filter(
        formulario_uid=formulario_uid,
        envio_id=envio_id
    ).first()

    if importacion:
        return {
            "envio_id": envio_id,
            "estado": importacion.estado,
            "asistencia_id": importacion.asistencia_id,
            "importacion_creada": False,
            "asistencia_creada": False,
        }

    # 5. Buscar si ya existe la asistencia
    asistencia = Asistencia.objects.filter(
        estudiante=estudiante,
        sesion=sesion
    ).first()

    asistencia_creada = False

    if asistencia:

        if asistencia.estado != estado_recibido:
            raise ValueError(
                "La asistencia existente tiene "
                "un estado diferente."
            )

        estado_importacion = (
            RegistroImportacionKobo.Estado.EXISTENTE
        )

    else:

        # Buscar la matrícula válida del estudiante
    # para el aula, CLEI y fecha de la sesión.
        matricula = (
            MatriculaCLEI.objects.filter(
                estudiante=estudiante,
                aula=sesion.horario.aula,
                clei=sesion.horario.clei,
                estado="EN_CURSO",
                fecha_inicio__lte=sesion.fecha
            )
            .filter(
                Q(fecha_fin__isnull=True)
                | Q(fecha_fin__gte=sesion.fecha)
            )
            .first()
        )

        if matricula is None:
            raise ValueError(
                "No se encontró una matrícula CLEI "
                "vigente para el estudiante, aula "
                "y fecha de la sesión."
            )

        # Crear asistencia asociada a la matrícula
        asistencia = Asistencia(
            estudiante=estudiante,
            sesion=sesion,
            matricula=matricula,
            estado=estado_recibido
        )

        asistencia.full_clean()
        asistencia.save()

        asistencia_creada = True

        estado_importacion = (
            RegistroImportacionKobo.Estado.CREADA
        )


    # 6. Registrar el envío de KoboToolbox
    importacion = RegistroImportacionKobo(
        formulario_uid=formulario_uid,
        envio_id=envio_id,
        envio_uuid=str(
            registro.get("_uuid") or ""
        ),
        asistencia=asistencia,
        estado=estado_importacion
    )

    importacion.full_clean()
    importacion.save()

    # 7. Actualizar el caso y programar la notificación
    # únicamente cuando se crea una nueva ausencia.
    if (
        asistencia_creada
        and estado_recibido == Asistencia.Estado.AUSENTE
    ):

        caso, caso_creado, caso_actualizado = (
            actualizar_caso_alerta(
                estudiante,
                crear_si_no_existe=True
            )
        )

        if caso is not None:

            # Ejecutar el envío de correo después
            # de confirmar la transacción en PostgreSQL.
            transaction.on_commit(
                lambda caso_id=caso.id,
                       asistencia_id=asistencia.id:
                    notificar_caso_alerta_segura(
                        caso_id,
                        asistencia_id
                    )
            )

    # 8. Devolver el resultado de la importación
    return {
        "envio_id": envio_id,
        "estado": importacion.estado,
        "asistencia_id": asistencia.id,
        "importacion_creada": True,
        "asistencia_creada": asistencia_creada,
    }


def sincronizar_asistencias_kobo(limite=100):
    """
    Sincroniza todas las respuestas de KoboToolbox.

    El parámetro limite controla el tamaño de cada página,
    no la cantidad total de respuestas procesadas.
    """

    cliente = KoboClient()

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
            resultado = procesar_respuesta_kobo(registro)

            if resultado["asistencia_creada"]:
                resumen["asistencias_creadas"] += 1

            elif not resultado["importacion_creada"]:
                resumen["envios_ya_procesados"] += 1

            else:
                resumen["asistencias_existentes"] += 1

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
    from .notificaciones import enviar_correo_caso_alerta

    logger = logging.getLogger(__name__)

    try:
        enviar_correo_caso_alerta(
            caso_id=caso_id,
            asistencia_id=asistencia_id
        )

    except Exception:
        logger.exception(
            "Error al enviar notificación del caso %s "
            "por la asistencia %s.",
            caso_id,
            asistencia_id
        )

