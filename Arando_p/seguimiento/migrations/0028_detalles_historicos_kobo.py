from django.db import migrations


def completar_detalles(apps, schema_editor):
    Registro = apps.get_model("seguimiento", "RegistroImportacionKobo")
    Detalle = apps.get_model("seguimiento", "DetalleImportacionKobo")
    alias = schema_editor.connection.alias
    for registro in Registro.objects.using(alias).exclude(asistencia_id=None).iterator():
        Detalle.objects.using(alias).get_or_create(
            importacion_id=registro.pk, asistencia_id=registro.asistencia_id,
        )


class Migration(migrations.Migration):
    dependencies = [("seguimiento", "0027_recepcion_grupal")]
    operations = [migrations.RunPython(completar_detalles, migrations.RunPython.noop)]
