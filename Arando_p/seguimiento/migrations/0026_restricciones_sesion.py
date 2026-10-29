import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("seguimiento", "0025_completar_contexto_sesion")]

    operations = [
        *[
            migrations.AlterField(
                model_name="sesionclase", name=campo,
                field=models.ForeignKey(
                    to=f"seguimiento.{destino}",
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="sesiones",
                ),
            )
            for campo, destino in (("aula", "aula"), ("clei", "clei"), ("docente", "docente"))
        ],
        migrations.AddConstraint(
            model_name="sesionclase",
            constraint=models.UniqueConstraint(
                fields=["aula", "clei", "docente", "fecha", "hora_inicio"],
                name="sesion_grupo_docente_fecha_inicio_unica",
            ),
        ),
        migrations.AddConstraint(
            model_name="sesionclase",
            constraint=models.CheckConstraint(
                condition=models.Q(hora_fin__gt=models.F("hora_inicio")),
                name="sesion_fin_posterior_inicio",
            ),
        ),
    ]
