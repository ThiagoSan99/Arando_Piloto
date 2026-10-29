import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("seguimiento", "0023_formulario_kobo")]

    operations = [
        migrations.AlterField(
            model_name="sesionclase", name="horario",
            field=models.ForeignKey(
                to="seguimiento.horario", on_delete=django.db.models.deletion.PROTECT,
                related_name="sesiones", null=True, blank=True,
            ),
        ),
        *[
            migrations.AddField(
                model_name="sesionclase", name=campo,
                field=models.ForeignKey(
                    to=f"seguimiento.{destino}",
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="sesiones", null=True,
                ),
            )
            for campo, destino in (("aula", "aula"), ("clei", "clei"), ("docente", "docente"))
        ],
        migrations.AddField(
            model_name="sesionclase", name="asignacion",
            field=models.ForeignKey(
                to="seguimiento.asignaciondocenteclei",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="sesiones", null=True, blank=True,
            ),
        ),
    ]
