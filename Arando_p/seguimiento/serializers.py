from django.core.exceptions import ValidationError as DjangoValidationError

from rest_framework import serializers

from .models import (
    Proyecto,
    Departamento,
    Zona,
    Institucion,
    Aula,
    CLEI,
    Docente,
    Estudiante,
    Horario,
    SesionClase,
    Asistencia,
    Alerta,
    Seguimiento,
    RevalidacionAsistencia,
)

from .services import (
    contar_ausencias,
    determinar_nivel_alerta,
)


# ==========================================
# 1. PROYECTOS
# ==========================================

class ProyectoSerializer(serializers.ModelSerializer):

    class Meta:
        model = Proyecto
        fields = [
            "id",
            "nombre",
            "descripcion",
            "fecha_inicio",
            "fecha_fin",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = fields


# ==========================================
# 2. DEPARTAMENTOS
# ==========================================

class DepartamentoSerializer(serializers.ModelSerializer):

    class Meta:
        model = Departamento
        fields = [
            "id",
            "nombre",
            "codigo_dane",
        ]
        read_only_fields = fields


# ==========================================
# 3. ZONAS
# ==========================================

class ZonaSerializer(serializers.ModelSerializer):

    proyecto_nombre = serializers.CharField(
        source="proyecto.nombre",
        read_only=True
    )

    departamento_nombre = serializers.CharField(
        source="departamento.nombre",
        read_only=True
    )

    class Meta:
        model = Zona
        fields = [
            "id",
            "proyecto",
            "proyecto_nombre",
            "departamento",
            "departamento_nombre",
            "nombre",
            "descripcion",
            "activa",
        ]
        read_only_fields = fields


# ==========================================
# 4. INSTITUCIONES
# ==========================================

class InstitucionSerializer(serializers.ModelSerializer):

    zona_nombre = serializers.CharField(
        source="zona.nombre",
        read_only=True
    )

    departamento_nombre = serializers.CharField(
        source="zona.departamento.nombre",
        read_only=True
    )

    proyecto_nombre = serializers.CharField(
        source="zona.proyecto.nombre",
        read_only=True
    )

    latitud = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        read_only=True,
        coerce_to_string=False
    )

    longitud = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        read_only=True,
        coerce_to_string=False
    )

    class Meta:
        model = Institucion
        fields = [
            "id",
            "nombre",
            "codigo_dane",
            "direccion",
            "municipio",
            "zona",
            "zona_nombre",
            "departamento_nombre",
            "proyecto_nombre",
            "latitud",
            "longitud",
            "activa",
            "fecha_creacion",
        ]
        read_only_fields = fields

# ==========================================
# 5. AULAS
# ==========================================

class AulaSerializer(serializers.ModelSerializer):

    institucion_nombre = serializers.CharField(
        source="institucion.nombre",
        read_only=True
    )

    class Meta:
        model = Aula
        fields = [
            "id",
            "institucion",
            "institucion_nombre",
            "nombre",
            "descripcion",
            "activa",
        ]
        read_only_fields = fields


# ==========================================
# 6. CLEI
# ==========================================

class CLEISerializer(serializers.ModelSerializer):

    class Meta:
        model = CLEI
        fields = [
            "id",
            "codigo",
            "nombre",
            "descripcion",
            "activo",
        ]
        read_only_fields = fields


# ==========================================
# 7. DOCENTES
# ==========================================

class DocenteSerializer(serializers.ModelSerializer):

    institucion_nombre = serializers.CharField(
        source="institucion.nombre",
        read_only=True
    )

    class Meta:
        model = Docente
        fields = [
            "id",
            "codigo",
            "institucion",
            "institucion_nombre",
            "nombres",
            "apellidos",
            "correo",
            "telefono",
            "activo",
            "fecha_creacion",
        ]
        read_only_fields = fields


# ==========================================
# 8. ESTUDIANTES
# ==========================================

class EstudianteSerializer(serializers.ModelSerializer):

    aula_nombre = serializers.CharField(
        source="aula.nombre",
        read_only=True
    )

    clei_codigo = serializers.CharField(
        source="clei.codigo",
        read_only=True
    )

    porcentaje_asistencia = serializers.SerializerMethodField()
    cantidad_ausencias = serializers.SerializerMethodField()
    nivel_alerta_actual = serializers.SerializerMethodField()

    class Meta:
        model = Estudiante
        fields = [
            "id",
            "codigo",
            "aula",
            "aula_nombre",
            "clei",
            "clei_codigo",
            "estado",
            "fecha_ingreso",
            "fecha_finalizacion",
            "porcentaje_asistencia",
            "cantidad_ausencias",
            "nivel_alerta_actual",
        ]
        read_only_fields = fields

    def get_porcentaje_asistencia(self, obj):
        return obj.porcentaje_asistencia()

    def get_cantidad_ausencias(self, obj):
        return contar_ausencias(obj)

    def get_nivel_alerta_actual(self, obj):
        ausencias = contar_ausencias(obj)
        nivel = determinar_nivel_alerta(ausencias)

        return str(nivel) if nivel is not None else None


# ==========================================
# 9. HORARIOS
# ==========================================

class HorarioSerializer(serializers.ModelSerializer):

    aula_nombre = serializers.CharField(
        source="aula.nombre",
        read_only=True
    )

    clei_codigo = serializers.CharField(
        source="clei.codigo",
        read_only=True
    )

    docente_codigo = serializers.CharField(
        source="docente.codigo",
        read_only=True
    )

    dia_nombre = serializers.CharField(
        source="get_dia_semana_display",
        read_only=True
    )

    class Meta:
        model = Horario
        fields = [
            "id",
            "aula",
            "aula_nombre",
            "clei",
            "clei_codigo",
            "docente",
            "docente_codigo",
            "dia_semana",
            "dia_nombre",
            "hora_inicio",
            "hora_fin",
            "activo",
            "fecha_creacion",
        ]
        read_only_fields = fields


# ==========================================
# 10. SESIONES DE CLASE
# ==========================================

class SesionClaseSerializer(serializers.ModelSerializer):

    aula_nombre = serializers.CharField(
        source="horario.aula.nombre",
        read_only=True
    )

    clei_codigo = serializers.CharField(
        source="horario.clei.codigo",
        read_only=True
    )

    docente_codigo = serializers.CharField(
        source="horario.docente.codigo",
        read_only=True
    )

    class Meta:
        model = SesionClase
        fields = [
            "id",
            "horario",
            "aula_nombre",
            "clei_codigo",
            "docente_codigo",
            "fecha",
            "hora_inicio",
            "hora_fin",
            "estado",
            "observaciones",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = fields


# ==========================================
# 11. ASISTENCIAS
# ==========================================

class AsistenciaSerializer(serializers.ModelSerializer):

    estudiante_codigo = serializers.CharField(
        source="estudiante.codigo",
        read_only=True
    )

    sesion_fecha = serializers.DateField(
        source="sesion.fecha",
        read_only=True
    )

    class Meta:
        model = Asistencia
        fields = [
            "id",
            "estudiante",
            "estudiante_codigo",
            "sesion",
            "sesion_fecha",
            "estado",
            "fecha_registro",
        ]
        read_only_fields = fields


# ==========================================
# 12. ALERTAS
# ==========================================

class AlertaSerializer(serializers.ModelSerializer):

    estudiante_codigo = serializers.CharField(
        source="estudiante.codigo",
        read_only=True
    )

    total_seguimientos = serializers.SerializerMethodField()

    class Meta:
        model = Alerta
        fields = [
            "id",
            "estudiante",
            "estudiante_codigo",
            "nivel",
            "estado",
            "cantidad_ausencias",
            "descripcion",
            "fecha_generacion",
            "fecha_cierre",
            "total_seguimientos",
        ]
        read_only_fields = fields

    def get_total_seguimientos(self, obj):
        return obj.seguimientos.count()


# ==========================================
# 13. SEGUIMIENTOS
# ==========================================

class SeguimientoSerializer(serializers.ModelSerializer):

    estudiante_codigo = serializers.CharField(
        source="alerta.estudiante.codigo",
        read_only=True
    )

    nivel_alerta = serializers.CharField(
        source="alerta.nivel",
        read_only=True
    )

    class Meta:
        model = Seguimiento
        fields = [
            "id",
            "alerta",
            "estudiante_codigo",
            "nivel_alerta",
            "responsable",
            "accion_realizada",
            "observaciones",
            "fecha_seguimiento",
            "fecha_registro",
        ]
        read_only_fields = fields


class RevalidacionAsistenciaSerializer(serializers.ModelSerializer):

    class Meta:
        model = RevalidacionAsistencia
        fields = [
            "id",
            "asistencia",
            "decision",
            "tipo_autorizador",
            "autorizado_por",
            "registrado_por",
            "motivo",
            "fecha_decision",
            "fecha_registro",
        ]

        read_only_fields = [
            "id",
            "registrado_por",
            "fecha_registro",
        ]

    def create(self, validated_data):
        revalidacion = RevalidacionAsistencia(**validated_data)

        try:
            revalidacion.full_clean()
        except DjangoValidationError as error:
            raise serializers.ValidationError(
                getattr(error, "message_dict", error.messages)
            )

        revalidacion.save()
        return revalidacion
