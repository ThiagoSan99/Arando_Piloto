from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError

class Proyecto(models.Model):
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    fecha_inicio = models.DateField(null=True, blank=True)
    fecha_fin = models.DateField(null=True, blank=True)
    activo = models.BooleanField(default=True)

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Proyecto"
        verbose_name_plural = "Proyectos"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

class Departamento(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    codigo_dane = models.CharField(
        max_length=2,
        unique=True,
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = "Departamento"
        verbose_name_plural = "Departamentos"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

class Zona(models.Model):
    proyecto = models.ForeignKey(
        Proyecto,
        on_delete=models.PROTECT,
        related_name="zonas"
    )

    departamento = models.ForeignKey(
        Departamento,
        on_delete=models.PROTECT,
        related_name="zonas"
    )

    nombre = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True)
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Zona"
        verbose_name_plural = "Zonas"
        ordering = ["nombre"]

        constraints = [
            models.UniqueConstraint(
                fields=["proyecto", "departamento", "nombre"],
                name="zona_unica_por_proyecto_departamento"
            )
        ]

    def __str__(self):
        return f"{self.nombre} - {self.departamento.nombre}"

class Institucion(models.Model):
    zona = models.ForeignKey(
        Zona,
        on_delete=models.PROTECT,
        related_name="instituciones"
    )

    nombre = models.CharField(max_length=200)

    codigo_dane = models.CharField(
        max_length=30,
        blank=True
    )

    direccion = models.CharField(
        max_length=250,
        blank=True
    )

    municipio = models.CharField(
        max_length=150,
        blank=True
    )

    activa = models.BooleanField(default=True)

    fecha_creacion = models.DateTimeField(auto_now_add=True)

    latitud = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True
    )

    longitud = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True
    )

    codigo_kobo = models.CharField(
        max_length=40,
        unique=True,
        null=True,
        blank=True
    )
    class Meta:
        verbose_name = "Institución"
        verbose_name_plural = "Instituciones"
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.nombre} - {self.zona.nombre}"

class Aula(models.Model):
    institucion = models.ForeignKey(
        Institucion,
        on_delete=models.PROTECT,
        related_name="aulas"
    )

    nombre = models.CharField(max_length=100)

    descripcion = models.TextField(
        blank=True
    )

    activa = models.BooleanField(default=True)
    codigo_kobo = models.CharField(
        max_length=40,
        unique=True,
        null=True,
        blank=True
    )
    class Meta:
        verbose_name = "Aula"
        verbose_name_plural = "Aulas"
        ordering = ["institucion", "nombre"]

        constraints = [
            models.UniqueConstraint(
                fields=["institucion", "nombre"],
                name="aula_unica_por_institucion"
            )
        ]

    def __str__(self):
        return f"{self.nombre} - {self.institucion.nombre}"

class CLEI(models.Model):
    codigo = models.CharField(
        max_length=10,
        unique=True
    )

    nombre = models.CharField(
        max_length=100
    )

    descripcion = models.TextField(
        blank=True
    )

    activo = models.BooleanField(
        default=True
    )
    horas_presenciales_requeridas = models.PositiveIntegerField(
    default=0
    )

    horas_autonomas_requeridas = models.PositiveIntegerField(
        default=0
    )

    class Meta:
        verbose_name = "CLEI"
        verbose_name_plural = "CLEI"
        ordering = ["codigo"]

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"

class Docente(models.Model):
    institucion = models.ForeignKey(
        Institucion,
        on_delete=models.PROTECT,
        related_name="docentes"
    )

    codigo = models.CharField(
        max_length=30,
        unique=True
    )

    nombres = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=100)

    correo = models.EmailField(blank=True)
    telefono = models.CharField(max_length=20, blank=True)

    activo = models.BooleanField(default=True)

    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Docente"
        verbose_name_plural = "Docentes"
        ordering = ["apellidos", "nombres"]

    def __str__(self):
        return f"{self.codigo} - {self.nombres} {self.apellidos}"

class Estudiante(models.Model):
    class Estado(models.TextChoices):
        ACTIVO = "ACTIVO", "Activo"
        APROBADO = "APROBADO", "Aprobado"
        RETIRADO = "RETIRADO", "Retirado"

    codigo = models.CharField(
        max_length=30,
        unique=True
    )

    aula = models.ForeignKey(
        Aula,
        on_delete=models.PROTECT,
        related_name="estudiantes"
    )

    clei = models.ForeignKey(
        CLEI,
        on_delete=models.PROTECT,
        related_name="estudiantes"
    )

    estado = models.CharField(
        max_length=10,
        choices=Estado.choices,
        default=Estado.ACTIVO
    )

    fecha_ingreso = models.DateField(
        null=True,
        blank=True
    )

    fecha_finalizacion = models.DateField(
        null=True,
        blank=True
    )

    fecha_creacion = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        verbose_name = "Estudiante"
        verbose_name_plural = "Estudiantes"
        ordering = ["codigo"]

    def __str__(self):
        return f"{self.codigo} - {self.clei.codigo}"

    def porcentaje_asistencia(self):

    # Si el estudiante aún no existe en la base de datos
        if self.pk is None:
            return 0

        # Consultar asistencias de sesiones realizadas
        asistencias = self.asistencias.filter(
            sesion__estado="REALIZADA"
        )

        total = asistencias.count()

        if total == 0:
            return 0

        presentes = asistencias.filter(
            estado="PRESENTE"
        ).count()

        return round((presentes / total) * 100, 2)

class Horario(models.Model):
    class DiaSemana(models.IntegerChoices):
        LUNES = 0, "Lunes"
        MARTES = 1, "Martes"
        MIERCOLES = 2, "Miércoles"
        JUEVES = 3, "Jueves"
        VIERNES = 4, "Viernes"
        SABADO = 5, "Sábado"
        DOMINGO = 6, "Domingo"

    aula = models.ForeignKey(
        Aula,
        on_delete=models.PROTECT,
        related_name="horarios"
    )

    clei = models.ForeignKey(
        CLEI,
        on_delete=models.PROTECT,
        related_name="horarios"
    )

    docente = models.ForeignKey(
        Docente,
        on_delete=models.PROTECT,
        related_name="horarios"
    )

    dia_semana = models.IntegerField(
        choices=DiaSemana.choices
    )

    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()

    activo = models.BooleanField(default=True)

    fecha_creacion = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        verbose_name = "Horario"
        verbose_name_plural = "Horarios"
        ordering = ["dia_semana", "hora_inicio"]

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.hora_inicio and self.hora_fin:
            if self.hora_inicio >= self.hora_fin:
                raise ValidationError({
                    "hora_fin": "La hora de finalización debe ser posterior a la hora de inicio."
                })

        if self.aula_id and self.docente_id:
            if self.aula.institucion_id != self.docente.institucion_id:
                raise ValidationError(
                    "El docente debe pertenecer a la misma institución del aula."
                )

    def __str__(self):
        return (
            f"{self.get_dia_semana_display()} - "
            f"{self.aula.nombre} - {self.clei.codigo} "
            f"({self.hora_inicio} - {self.hora_fin})"
        )

class SesionClase(models.Model):
    class Estado(models.TextChoices):
        PROGRAMADA = "PROGRAMADA", "Programada"
        REALIZADA = "REALIZADA", "Realizada"
        CANCELADA = "CANCELADA", "Cancelada"
        REPROGRAMADA = "REPROGRAMADA", "Reprogramada"

    @property
    def horas_academicas(self):
        if self.estado == self.Estado.REALIZADA:
            return 5
        return 0

    horario = models.ForeignKey(
        Horario,
        on_delete=models.PROTECT,
        related_name="sesiones"
    )

    fecha = models.DateField()

    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()

    estado = models.CharField(
        max_length=15,
        choices=Estado.choices,
        default=Estado.PROGRAMADA
    )

    observaciones = models.TextField(blank=True)

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Sesión de clase"
        verbose_name_plural = "Sesiones de clase"
        ordering = ["-fecha", "hora_inicio"]

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.hora_inicio and self.hora_fin:
            if self.hora_inicio >= self.hora_fin:
                raise ValidationError({
                    "hora_fin": (
                        "La hora de finalización debe ser "
                        "posterior a la hora de inicio."
                    )
                })

    def __str__(self):
        return (
            f"{self.fecha} - "
            f"{self.horario.clei.codigo} - "
            f"{self.horario.aula.nombre}"
        )

class Asistencia(models.Model):
    class Estado(models.TextChoices):
        PRESENTE = "PRESENTE", "Presente"
        AUSENTE = "AUSENTE", "Ausente"

    estudiante = models.ForeignKey(
        Estudiante,
        on_delete=models.PROTECT,
        related_name="asistencias"
    )

    sesion = models.ForeignKey(
        SesionClase,
        on_delete=models.PROTECT,
        related_name="asistencias"
    )

    estado = models.CharField(
        max_length=10,
        choices=Estado.choices
    )

    fecha_registro = models.DateTimeField(
        auto_now_add=True
    )
    matricula = models.ForeignKey(
        "MatriculaCLEI",
        on_delete=models.PROTECT,
        related_name="asistencias",
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = "Asistencia"
        verbose_name_plural = "Asistencias"
        ordering = ["-sesion__fecha"]

        constraints = [
            models.UniqueConstraint(
                fields=["estudiante", "sesion"],
                name="asistencia_unica_por_estudiante_sesion"
            )
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.estudiante_id and self.sesion_id:
            if self.estudiante.aula_id != self.sesion.horario.aula_id:
                raise ValidationError(
                    "El estudiante no pertenece al aula de esta sesión."
                )

            if self.estudiante.clei_id != self.sesion.horario.clei_id:
                raise ValidationError(
                    "El CLEI del estudiante no corresponde al de la sesión."
                )

            if self.sesion.estado == SesionClase.Estado.CANCELADA:
                raise ValidationError(
                    "No se puede registrar asistencia en una sesión cancelada."
                )

            if self.sesion.estado != SesionClase.Estado.REALIZADA:
                raise ValidationError(
                    "Solo se puede registrar asistencia en sesiones realizadas."
                )

    def __str__(self):
        return (
            f"{self.estudiante.codigo} - "
            f"{self.sesion.fecha} - "
            f"{self.estado}"
        )

class Alerta(models.Model):

    class Nivel(models.TextChoices):
        TEMPRANA = "TEMPRANA", "Temprana"
        AMARILLA = "AMARILLA", "Amarilla"
        ROJA = "ROJA", "Roja"

    class Estado(models.TextChoices):
        ABIERTA = "ABIERTA", "Abierta"
        EN_SEGUIMIENTO = "EN_SEGUIMIENTO", "En seguimiento"
        CERRADA = "CERRADA", "Cerrada"

    estudiante = models.ForeignKey(
        Estudiante,
        on_delete=models.PROTECT,
        related_name="alertas"
    )

    nivel = models.CharField(
        max_length=10,
        choices=Nivel.choices
    )

    estado = models.CharField(
        max_length=15,
        choices=Estado.choices,
        default=Estado.ABIERTA
    )

    cantidad_ausencias = models.PositiveIntegerField()

    descripcion = models.TextField(blank=True)

    fecha_generacion = models.DateTimeField(
        auto_now_add=True
    )

    fecha_cierre = models.DateTimeField(
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = "Alerta"
        verbose_name_plural = "Alertas"
        ordering = ["-fecha_generacion"]

    def __str__(self):
        return (
            f"{self.estudiante.codigo} - "
            f"{self.nivel} - {self.estado}"
        )

class Seguimiento(models.Model):

    alerta = models.ForeignKey(
        Alerta,
        on_delete=models.PROTECT,
        related_name="seguimientos"
    )

    responsable = models.CharField(
        max_length=150
    )

    accion_realizada = models.TextField()

    observaciones = models.TextField(
        blank=True
    )

    fecha_seguimiento = models.DateTimeField()

    fecha_registro = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        verbose_name = "Seguimiento"
        verbose_name_plural = "Seguimientos"
        ordering = ["-fecha_seguimiento"]

    def __str__(self):
        return (
            f"Seguimiento {self.id} - "
            f"Alerta {self.alerta.id}"
        )

class RegistroImportacionKobo(models.Model):

    class Estado(models.TextChoices):
        CREADA = "CREADA", "Asistencia creada"
        EXISTENTE = "EXISTENTE", "Asistencia ya existente"
        ERROR = "ERROR", "Error de importación"

    formulario_uid = models.CharField(
        max_length=100
    )

    envio_id = models.BigIntegerField()

    envio_uuid = models.CharField(
        max_length=100,
        blank=True
    )

    asistencia = models.ForeignKey(
        Asistencia,
        on_delete=models.PROTECT,
        related_name="importaciones_kobo",
        null=True,
        blank=True
    )

    estado = models.CharField(
        max_length=10,
        choices=Estado.choices
    )

    detalle_error = models.TextField(
        blank=True
    )

    fecha_procesamiento = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        verbose_name = "Registro de importación Kobo"
        verbose_name_plural = "Registros de importación Kobo"

        ordering = ["-fecha_procesamiento"]

        constraints = [
            models.UniqueConstraint(
                fields=["formulario_uid", "envio_id"],
                name="importacion_kobo_envio_unico"
            )
        ]

    def __str__(self):
        return (
            f"Kobo {self.envio_id} - {self.estado}"
        )


class MatriculaCLEI(models.Model):

    class Estado(models.TextChoices):
        EN_CURSO = "EN_CURSO", "En curso"
        APROBADA = "APROBADA", "Aprobada"
        RETIRADA = "RETIRADA", "Retirada"

    estudiante = models.ForeignKey(
        Estudiante,
        on_delete=models.PROTECT,
        related_name="matriculas"
    )

    clei = models.ForeignKey(
        CLEI,
        on_delete=models.PROTECT,
        related_name="matriculas"
    )

    aula = models.ForeignKey(
        Aula,
        on_delete=models.PROTECT,
        related_name="matriculas"
    )

    fecha_inicio = models.DateField()

    fecha_fin = models.DateField(
        null=True,
        blank=True
    )

    estado = models.CharField(
        max_length=15,
        choices=Estado.choices,
        default=Estado.EN_CURSO
    )

    observaciones = models.TextField(
        blank=True
    )

    fecha_creacion = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        verbose_name = "Matrícula CLEI"
        verbose_name_plural = "Matrículas CLEI"

        ordering = ["-fecha_inicio"]

        constraints = [
            models.UniqueConstraint(
                fields=["estudiante"],
                condition=models.Q(estado="EN_CURSO"),
                name="una_matricula_activa_por_estudiante"
            )
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        if (
            self.fecha_inicio
            and self.fecha_fin
            and self.fecha_fin < self.fecha_inicio
        ):
            raise ValidationError({
                "fecha_fin": (
                    "La fecha de finalización no puede "
                    "ser anterior a la fecha de inicio."
                )
            })

    def __str__(self):
        return (
            f"{self.estudiante.codigo} - "
            f"{self.clei.codigo} - {self.estado}"
        )


class AsignacionDocenteCLEI(models.Model):

    docente = models.ForeignKey(
        Docente,
        on_delete=models.PROTECT,
        related_name="asignaciones_clei"
    )

    aula = models.ForeignKey(
        Aula,
        on_delete=models.PROTECT,
        related_name="asignaciones_docentes"
    )

    clei = models.ForeignKey(
        CLEI,
        on_delete=models.PROTECT,
        related_name="asignaciones_docentes"
    )

    fecha_inicio = models.DateField()

    fecha_fin = models.DateField(
        null=True,
        blank=True
    )

    activa = models.BooleanField(
        default=True
    )

    fecha_creacion = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        verbose_name = "Asignación docente CLEI"
        verbose_name_plural = "Asignaciones docentes CLEI"

        constraints = [
            models.UniqueConstraint(
                fields=["docente", "aula", "clei"],
                condition=models.Q(activa=True),
                name="asignacion_docente_aula_clei_activa_unica"
            )
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        errores = {}

        if self.fecha_fin and self.fecha_inicio:
            if self.fecha_fin < self.fecha_inicio:
                errores["fecha_fin"] = (
                    "La fecha de finalización no puede "
                    "ser anterior a la fecha de inicio."
                )

        if self.docente_id and self.aula_id:
            if (
                self.docente.institucion_id
                != self.aula.institucion_id
            ):
                errores["docente"] = (
                    "El docente debe pertenecer a la "
                    "misma institución del aula."
                )

        if errores:
            raise ValidationError(errores)

    def __str__(self):
        return (
            f"{self.docente.codigo} - "
            f"{self.aula.nombre} - "
            f"CLEI {self.clei.codigo}"
        )

class RevalidacionAsistencia(models.Model):

    class Decision(models.TextChoices):
        APROBADA = "APROBADA", "Aprobada"
        RECHAZADA = "RECHAZADA", "Rechazada"

    class TipoAutorizador(models.TextChoices):
        DOCENTE = "DOCENTE", "Docente"
        COORDINADOR = "COORDINADOR", "Coordinador zonal"

    asistencia = models.ForeignKey(
        Asistencia,
        on_delete=models.PROTECT,
        related_name="revalidaciones"
    )

    decision = models.CharField(
        max_length=10,
        choices=Decision.choices
    )

    tipo_autorizador = models.CharField(
        max_length=15,
        choices=TipoAutorizador.choices
    )

    autorizado_por = models.CharField(
        max_length=150
    )

    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="revalidaciones_registradas"
    )

    motivo = models.TextField()

    fecha_decision = models.DateField()

    fecha_registro = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["-fecha_registro", "-id"]
        verbose_name = "Revalidación de asistencia"
        verbose_name_plural = "Revalidaciones de asistencia"

    def clean(self):
        super().clean()

        if self.asistencia_id:
            if self.asistencia.estado != Asistencia.Estado.AUSENTE:
                raise ValidationError({
                    "asistencia": (
                        "Solo se pueden revalidar "
                        "registros de inasistencia."
                    )
                })

    def __str__(self):
        return (
            f"Revalidación {self.id} - "
            f"{self.decision}"
        )


class CasoAlerta(models.Model):

    class Estado(models.TextChoices):
        ABIERTA = "ABIERTA", "Abierta"
        EN_SEGUIMIENTO = "EN_SEGUIMIENTO", "En seguimiento"
        CERRADA = "CERRADA", "Cerrada"

    estudiante = models.ForeignKey(
        Estudiante,
        on_delete=models.PROTECT,
        related_name="casos_alerta"
    )

    nivel_actual = models.CharField(
        max_length=10,
        choices=Alerta.Nivel.choices,
        null=True,
        blank=True
    )

    ausencias_efectivas = models.PositiveIntegerField(
        default=0
    )

    estado = models.CharField(
        max_length=15,
        choices=Estado.choices,
        default=Estado.ABIERTA
    )

    fecha_apertura = models.DateTimeField(
        auto_now_add=True
    )

    fecha_actualizacion = models.DateTimeField(
        auto_now=True
    )

    fecha_cierre = models.DateTimeField(
        null=True,
        blank=True
    )

    observaciones = models.TextField(
        blank=True
    )

    class Meta:
        verbose_name = "Caso de alerta"
        verbose_name_plural = "Casos de alerta"

        ordering = ["-fecha_apertura"]

        constraints = [
            models.UniqueConstraint(
                fields=["estudiante"],
                condition=models.Q(
                    estado__in=[
                        "ABIERTA",
                        "EN_SEGUIMIENTO"
                    ]
                ),
                name="un_caso_alerta_activo_por_estudiante"
            )
        ]

    def __str__(self):
        return (
            f"{self.estudiante.codigo} - "
            f"{self.nivel_actual or 'SIN RIESGO'} - "
            f"{self.estado}"
        )
