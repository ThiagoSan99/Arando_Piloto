from django.contrib import admin

from .models import CampoAsistenciaKobo, FormularioKobo, NotificacionAusencia, IntentoNotificacionAusencia


class CampoAsistenciaKoboInline(admin.TabularInline):
    model = CampoAsistenciaKobo
    raw_id_fields = ("estudiante",)
    extra = 0


@admin.register(FormularioKobo)
class FormularioKoboAdmin(admin.ModelAdmin):
    list_display = ("formulario_uid", "docente", "aula", "clei", "formato", "activo")
    inlines = (CampoAsistenciaKoboInline,)
    list_filter = ("activo",)
    search_fields = ("formulario_uid", "docente__codigo", "aula__codigo_kobo")
    raw_id_fields = ("docente", "aula", "clei")
    readonly_fields = ("fecha_creacion", "fecha_actualizacion")
    list_select_related = ("docente", "aula__institucion", "clei")


class IntentoNotificacionInline(admin.TabularInline):
    model = IntentoNotificacionAusencia
    extra = 0
    can_delete = False
    readonly_fields = ("numero", "estado", "fase", "tipo_error", "codigo_smtp", "fecha_inicio", "fecha_fin")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(NotificacionAusencia)
class NotificacionAusenciaAdmin(admin.ModelAdmin):
    list_display = ("id", "asistencia_referencia", "destinatario", "estado", "intentos", "fecha_envio")
    list_filter = ("estado", "origen")
    inlines = (IntentoNotificacionInline,)
    readonly_fields = tuple(campo.name for campo in NotificacionAusencia._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
