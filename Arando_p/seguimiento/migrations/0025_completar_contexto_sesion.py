from django.db import migrations
from django.db.models import Count, F


def completar_contexto(apps, schema_editor):
    Sesion = apps.get_model("seguimiento", "SesionClase")
    sesiones = Sesion.objects.using(schema_editor.connection.alias)
    # No fusionar registros ni elegir autorizaciones históricas por inferencia.
    if sesiones.filter(horario__isnull=True).exists():
        raise RuntimeError("Hay sesiones sin horario; revisa su contexto antes de migrar.")
    if sesiones.filter(hora_fin__lte=F("hora_inicio")).exists():
        raise RuntimeError("Hay sesiones con horas inválidas; se requiere revisión antes de migrar.")
    if sesiones.exclude(
        horario__aula__institucion_id=F("horario__docente__institucion_id")
    ).exists():
        raise RuntimeError("Hay sesiones con instituciones incoherentes; se requiere revisión.")
    duplicados = sesiones.values(
        "horario__aula_id", "horario__clei_id", "horario__docente_id", "fecha", "hora_inicio"
    ).annotate(total=Count("id")).filter(total__gt=1)
    if duplicados.exists():
        raise RuntimeError("Hay sesiones duplicadas; no se fusionaron ni eliminaron registros.")

    for sesion in sesiones.select_related("horario").iterator():
        contexto = {f"{campo}_id": getattr(sesion.horario, f"{campo}_id")
                    for campo in ("aula", "clei", "docente")}
        if any(getattr(sesion, campo) not in (None, valor)
               for campo, valor in contexto.items()):
            raise RuntimeError("El contexto previo de una sesión contradice su horario.")
        sesiones.filter(pk=sesion.pk).update(**contexto)


class Migration(migrations.Migration):
    dependencies = [("seguimiento", "0024_contexto_sesion")]
    operations = [migrations.RunPython(completar_contexto, migrations.RunPython.noop)]
