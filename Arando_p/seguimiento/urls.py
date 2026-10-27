
from django.urls import path

from .views import (
    ProyectoListView,
    DepartamentoListView,
    ZonaListView,
    InstitucionListView,
    AulaListView,
    CLEIListView,
    DocenteListView,
    EstudianteListView,
    HorarioListView,
    SesionClaseListView,
    AsistenciaListView,
    AlertaListView,
    SeguimientoListView,
    
)

urlpatterns = [
    path("proyectos/", ProyectoListView.as_view()),
    path("departamentos/", DepartamentoListView.as_view()),
    path("zonas/", ZonaListView.as_view()),
    path("instituciones/", InstitucionListView.as_view()),
    path("aulas/", AulaListView.as_view()),
    path("clei/", CLEIListView.as_view()),
    path("docentes/", DocenteListView.as_view()),
    path("estudiantes/", EstudianteListView.as_view()),
    path("horarios/", HorarioListView.as_view()),
    path("sesiones/", SesionClaseListView.as_view()),
    path("asistencias/", AsistenciaListView.as_view()),
    path("alertas/", AlertaListView.as_view()),
    path("seguimientos/", SeguimientoListView.as_view()),

]
