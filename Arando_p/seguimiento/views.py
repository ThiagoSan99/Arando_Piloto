
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.db import transaction

from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.exceptions import ValidationError


from .services import (
    calcular_horas_presenciales,
    calcular_riesgo_actual,
    actualizar_caso_alerta
)


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
    MatriculaCLEI,
    Asistencia, 
    SesionClase, 
    RevalidacionAsistencia
)

from .serializers import (
    ProyectoSerializer,
    DepartamentoSerializer,
    ZonaSerializer,
    InstitucionSerializer,
    AulaSerializer,
    CLEISerializer,
    DocenteSerializer,
    EstudianteSerializer,
    HorarioSerializer,
    SesionClaseSerializer,
    AsistenciaSerializer,
    AlertaSerializer,
    SeguimientoSerializer,
    RevalidacionAsistenciaSerializer
)


# Clase base para endpoints de solo lectura
class BaseListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]


class ProyectoListView(BaseListView):
    queryset = Proyecto.objects.all()
    serializer_class = ProyectoSerializer


class DepartamentoListView(BaseListView):
    queryset = Departamento.objects.all()
    serializer_class = DepartamentoSerializer


class ZonaListView(BaseListView):
    queryset = Zona.objects.select_related(
        "proyecto", "departamento"
    ).all()
    serializer_class = ZonaSerializer


class InstitucionListView(BaseListView):
    queryset = Institucion.objects.select_related(
        "zona"
    ).all()
    serializer_class = InstitucionSerializer


class AulaListView(BaseListView):
    queryset = Aula.objects.select_related(
        "institucion"
    ).all()
    serializer_class = AulaSerializer


class CLEIListView(BaseListView):
    queryset = CLEI.objects.all()
    serializer_class = CLEISerializer


class DocenteListView(BaseListView):
    queryset = Docente.objects.select_related(
        "institucion"
    ).all()
    serializer_class = DocenteSerializer


class EstudianteListView(BaseListView):
    queryset = Estudiante.objects.select_related(
        "aula", "clei"
    ).all().order_by("codigo")
    serializer_class = EstudianteSerializer


class HorarioListView(BaseListView):
    queryset = Horario.objects.select_related(
        "aula", "clei", "docente"
    ).all()
    serializer_class = HorarioSerializer


class SesionClaseListView(BaseListView):
    queryset = SesionClase.objects.select_related(
        "aula",
        "clei",
        "docente",
    ).all()
    serializer_class = SesionClaseSerializer


class AsistenciaListView(BaseListView):
    queryset = Asistencia.objects.select_related(
        "estudiante", "sesion"
    ).all()
    serializer_class = AsistenciaSerializer


class AlertaListView(BaseListView):
    queryset = Alerta.objects.select_related(
        "estudiante"
    ).all()
    serializer_class = AlertaSerializer


class SeguimientoListView(BaseListView):
    queryset = Seguimiento.objects.select_related(
        "alerta__estudiante"
    ).all()
    serializer_class = SeguimientoSerializer

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def horas_presenciales_matricula(request, matricula_id):

    matricula = get_object_or_404(
        MatriculaCLEI.objects.select_related(
            "estudiante",
            "clei"
        ),
        pk=matricula_id
    )

    resultado = calcular_horas_presenciales(matricula)

    return Response(resultado)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def registrar_revalidacion(request):

    serializer = RevalidacionAsistenciaSerializer(
        data=request.data
    )

    serializer.is_valid(raise_exception=True)

    with transaction.atomic():

        asistencia = Asistencia.objects.select_for_update().get(
            pk=serializer.validated_data["asistencia"].pk
        )

        if asistencia.estado != Asistencia.Estado.AUSENTE:
            raise ValidationError({
                "asistencia": "Solo se pueden revalidar ausencias."
            })

        if asistencia.matricula_id is None:
            raise ValidationError({
                "asistencia": "La asistencia no tiene matrícula CLEI."
            })

        if asistencia.sesion.estado != SesionClase.Estado.REALIZADA:
            raise ValidationError({
                "asistencia": "La sesión debe estar REALIZADA."
            })

        if RevalidacionAsistencia.objects.filter(
            asistencia=asistencia
        ).exists():
            raise ValidationError({
                "asistencia": (
                    "Esta asistencia ya tiene una decisión registrada."
                )
            })

        serializer.save(
            asistencia=asistencia,
            registrado_por=request.user
        )

        # Calcular el riesgo después de registrar la revalidación

    
    # Recalcular el riesgo académico
    estudiante = asistencia.estudiante

    riesgo_actualizado = calcular_riesgo_actual(
        estudiante
    )

    # Actualizar el caso administrativo existente.
    # Una revalidación no abre un caso nuevo.
    caso, caso_creado, caso_actualizado = actualizar_caso_alerta(
        estudiante,
        crear_si_no_existe=False
    )

    return Response(
        {
            "mensaje": "Revalidación registrada correctamente.",
            "revalidacion": serializer.data,
            "riesgo_actual": riesgo_actualizado,
            "caso_alerta": {
                "id": caso.id if caso else None,
                "nivel_actual": caso.nivel_actual if caso else None,
                "ausencias_efectivas": (
                    caso.ausencias_efectivas if caso else None
                ),
                "estado": caso.estado if caso else None,
                "actualizado": caso_actualizado,
            }
        },
        status=status.HTTP_201_CREATED
    )



@api_view(["GET"])
@permission_classes([IsAdminUser])
def consultar_riesgo_estudiante(request, codigo):

    estudiante = get_object_or_404(
        Estudiante,
        codigo=codigo
    )

    resultado = calcular_riesgo_actual(estudiante)

    return Response(resultado)
