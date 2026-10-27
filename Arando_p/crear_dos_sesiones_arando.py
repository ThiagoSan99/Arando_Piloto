"""Arando: crea dos sesiones PILOTO para el 20/10/2026.

Uso (desde E:\\Arando_p, en PowerShell con .venv activado):
    python manage.py shell -c "exec(open('crear_dos_sesiones_arando_2026_10_20.py', encoding='utf-8').read())"

La ejecución es idempotente: si existen los mismos horarios/sesiones,
los reutiliza. NO marca clases futuras como REALIZADA.
"""

from datetime import date, time

from django.db import transaction
from seguimiento.models import Horario, SesionClase

FECHA = date(2026, 10, 20)
SESION_REFERENCIA = 8
FRANJAS = [
    ("Sesión 1", time(11, 0), time(13, 0)),
    ("Sesión 2", time(14, 0), time(16, 0)),
]

base = SesionClase.objects.select_related(
    "horario__aula", "horario__clei", "horario__docente"
).get(pk=SESION_REFERENCIA)
horario_base = base.horario

campo_dia = Horario._meta.get_field("dia_semana")
opciones_dia = list(campo_dia.flatchoices)
valor_martes = next(
    (
        valor
        for valor, etiqueta in opciones_dia
        if "martes" in str(etiqueta).casefold()
        or "tuesday" in str(etiqueta).casefold()
    ),
    None,
)

if valor_martes is None:
    raise ValueError(
        "No se puede determinar automáticamente el valor de MARTES para "
        f"Horario.dia_semana. Opciones disponibles: {opciones_dia}. "
        "Indícame esta salida para ajustar el script a tu modelo."
    )

print("Fecha de prueba:", FECHA)
print("Día configurado:", valor_martes)
print("Institución:", horario_base.aula.institucion.nombre)
print("Aula:", horario_base.aula.nombre)
print("CLEI:", horario_base.clei.codigo)
print("Docente:", horario_base.docente.codigo)

with transaction.atomic():
    for nombre, inicio, fin in FRANJAS:
        horario, horario_creado = Horario.objects.get_or_create(
            aula=horario_base.aula,
            clei=horario_base.clei,
            docente=horario_base.docente,
            dia_semana=valor_martes,
            hora_inicio=inicio,
            hora_fin=fin,
        )
        horario.full_clean()

        sesion, sesion_creada = SesionClase.objects.get_or_create(
            horario=horario,
            fecha=FECHA,
            defaults={
                "hora_inicio": inicio,
                "hora_fin": fin,
                "estado": SesionClase.Estado.PROGRAMADA,
            },
        )
        if sesion.hora_inicio != inicio or sesion.hora_fin != fin:
            raise ValueError(
                f"La sesión {sesion.pk} ya existe pero tiene otra hora. "
                "Detuve la operación para no modificarla accidentalmente."
            )
        sesion.full_clean()
        print(
            f"{nombre} | sesión_id={sesion.pk} | horario_id={horario.pk} "
            f"| {inicio:%H:%M}-{fin:%H:%M} | estado={sesion.estado} "
            f"| nueva={sesion_creada}"
        )

print("LISTO. Una vez realizada cada clase, cambia su estado a REALIZADA")
print("antes de enviar y sincronizar la asistencia desde KoboToolbox.")
