"""Procesamiento atómico de contratos individual y GRUPAL_V1."""
from django.core.exceptions import ValidationError
from django.db import transaction

from . import services
from .kobo_client import KoboClient
from .models import (
    AsignacionDocenteCLEI, Asistencia, DetalleImportacionKobo, Estudiante,
    FormatoRegistroKobo, FormularioKobo, RegistroImportacionKobo,
)


def normalizar_envio(registro, formulario):
    """No interpreta códigos a partir del nombre del campo: usa el mapeo autorizado."""
    campos_recibidos = {clave for clave in registro if clave.startswith("asistencia_")}
    if formulario is None or formulario.formato == FormatoRegistroKobo.INDIVIDUAL:
        if campos_recibidos or registro.get("formato_registro") == FormatoRegistroKobo.GRUPAL_V1:
            raise ValidationError("El formulario no está configurado para recepción grupal.")
        return [("", registro)]

    if registro.get("formato_registro") != FormatoRegistroKobo.GRUPAL_V1:
        raise ValidationError("El envío debe declarar formato_registro=GRUPAL_V1.")
    if "codigo_estudiante" in registro or "estado_asistencia" in registro:
        raise ValidationError("No se pueden mezclar contratos individual y grupal.")
    mapas = list(formulario.campos_asistencia.select_for_update().order_by("estudiante_id"))
    if not mapas:
        raise ValidationError("El formulario grupal no tiene estudiantes configurados.")
    if campos_recibidos != {mapa.campo for mapa in mapas}:
        raise ValidationError("La lista de campos de asistencia no coincide con la autorizada.")
    return [(mapa.campo, {
        **registro, "codigo_estudiante": mapa.estudiante.codigo,
        "estado_asistencia": registro[mapa.campo],
    }) for mapa in mapas]


def resultado_existente(importacion):
    return {
        "envio_id": importacion.envio_id, "estado": importacion.estado,
        "asistencia_id": importacion.asistencia_id,
        "asistencia_ids": list(importacion.asistencias.values_list("pk", flat=True)),
        "importacion_creada": False, "asistencia_creada": False,
        "asistencias_creadas": 0, "asistencias_existentes": 0,
    }


def guardar_asistencia(estudiante, sesion, estado):
    asistencia = Asistencia.objects.filter(estudiante=estudiante, sesion=sesion).first()
    if asistencia is not None:
        if asistencia.estado != estado:
            raise ValidationError("La asistencia existente tiene un estado diferente.")
        return asistencia, False
    matricula = services.obtener_matricula_kobo(
        estudiante, sesion.aula, sesion.clei, sesion.fecha, bloquear=True,
    )
    asistencia = Asistencia(estudiante=estudiante, sesion=sesion, matricula=matricula, estado=estado)
    asistencia.full_clean()
    asistencia.save()
    return asistencia, True


def notificar_nueva_ausencia(asistencia, estadisticas):
    caso, _, _ = services.actualizar_caso_alerta(asistencia.estudiante, crear_si_no_existe=True)
    if caso is not None:
        from .correo_persistente import preparar_notificaciones
        registros = preparar_notificaciones(caso.pk, asistencia.pk)
        estadisticas["programadas"] += sum(registro.estado in ("PENDIENTE", "FALLIDA") for registro in registros)
        estadisticas["bloqueadas"] += sum(registro.estado == "BLOQUEADA" for registro in registros)

        def entregar(caso_id=caso.pk, asistencia_id=asistencia.pk):
            resultados = services.notificar_caso_alerta_segura(caso_id, asistencia_id)
            if isinstance(resultados, dict):
                for origen, destino in (("ENVIADA", "aceptadas"), ("FALLIDA", "fallidas"),
                                        ("INCIERTA", "inciertas"), ("ERROR_INTERNO", "fallidas")):
                    estadisticas[destino] += resultados.get(origen, 0)

        transaction.on_commit(entregar)


@transaction.atomic
def procesar(registro, formulario_uid=None):
    if not isinstance(registro, dict):
        raise ValidationError("La respuesta Kobo debe ser un objeto.")
    uid = formulario_uid if formulario_uid is not None else KoboClient.FORM_UID
    if registro.get("_id") is None:
        raise ValueError("La respuesta no contiene el identificador _id.")
    envio_id = int(registro["_id"])
    importaciones = RegistroImportacionKobo.objects.filter(formulario_uid=uid, envio_id=envio_id)
    existente = importaciones.first()
    if existente is not None:
        return resultado_existente(existente)

    # Orden estable para grupos, formularios y estudiantes compartidos.
    formulario = FormularioKobo.objects.select_for_update().filter(formulario_uid=uid).first()
    existente = importaciones.first()
    if existente is not None:
        return resultado_existente(existente)
    filas = normalizar_envio(registro, formulario)
    resultados = [services.validar_asistencia_kobo(fila, formulario_uid=uid) for _, fila in filas]
    asignacion_id = resultados[0]["asignacion_id"]
    if asignacion_id is not None:
        AsignacionDocenteCLEI.objects.select_for_update().get(pk=asignacion_id)
    ids = sorted(resultado["estudiante_id"] for resultado in resultados)
    estudiantes = {estudiante.pk: estudiante for estudiante in
                   Estudiante.objects.select_for_update().filter(pk__in=ids).order_by("pk")}
    existente = importaciones.first()
    if existente is not None:
        return resultado_existente(existente)

    # Se vuelve a comprobar cada matrícula/estado tras adquirir los bloqueos.
    actuales = [services.validar_asistencia_kobo(fila, formulario_uid=uid) for _, fila in filas]
    if any(nuevo["asignacion_id"] != asignacion_id or nuevo["estudiante_id"] != anterior["estudiante_id"]
           for nuevo, anterior in zip(actuales, resultados)):
        raise ValidationError("El contexto cambió durante el procesamiento; reintenta el envío.")
    sesion, sesion_creada = services.obtener_o_crear_sesion_validada(actuales[0])
    guardadas = []
    for (campo, _), resultado in zip(filas, actuales):
        asistencia, creada = guardar_asistencia(
            estudiantes[resultado["estudiante_id"]], sesion, resultado["estado"],
        )
        guardadas.append((campo, asistencia, creada))

    cantidad = sum(creada for _, _, creada in guardadas)
    formato = formulario.formato if formulario is not None else FormatoRegistroKobo.INDIVIDUAL
    importacion = RegistroImportacionKobo(
        formulario_uid=uid, envio_id=envio_id, envio_uuid=str(registro.get("_uuid") or ""),
        formato=formato,
        asistencia=guardadas[0][1] if formato == FormatoRegistroKobo.INDIVIDUAL else None,
        estado=RegistroImportacionKobo.Estado.CREADA if cantidad else RegistroImportacionKobo.Estado.EXISTENTE,
    )
    importacion.full_clean()
    importacion.save()
    estadisticas = dict(programadas=0, aceptadas=0, fallidas=0, inciertas=0, bloqueadas=0)
    for campo, asistencia, creada in guardadas:
        DetalleImportacionKobo.objects.create(
            importacion=importacion, asistencia=asistencia, campo_formulario=campo,
        )
        if creada and asistencia.estado == Asistencia.Estado.AUSENTE:
            notificar_nueva_ausencia(asistencia, estadisticas)

    return {
        "envio_id": envio_id, "estado": importacion.estado,
        "asistencia_id": importacion.asistencia_id,
        "asistencia_ids": [asistencia.pk for _, asistencia, _ in guardadas],
        "importacion_creada": True, "asistencia_creada": bool(cantidad),
        "asistencias_creadas": cantidad, "asistencias_existentes": len(guardadas) - cantidad,
        "sesion_id": sesion.pk, "sesion_creada": sesion_creada,
        "notificaciones": estadisticas,
    }
