from io import StringIO
from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.db import connection, DatabaseError
from django.db.models.query import QuerySet
from django.test import TestCase
from django.utils import timezone

from . import tests_kobo
from .models import (
    Alerta, Asistencia, Aula, CasoAlerta, Docente, Estudiante, FormularioKobo,
    Horario, MatriculaCLEI, RegistroImportacionKobo, RevalidacionAsistencia,
    Seguimiento, SesionClase,
)


class LimpiezaPruebasKoboTests(TestCase):
    UID = "formulario-grupo-ficticio"
    registro = tests_kobo.ImportacionContextoKoboTests.registro
    procesar = tests_kobo.ImportacionContextoKoboTests.procesar

    @classmethod
    def setUpTestData(cls):
        tests_kobo.ImportacionContextoKoboTests.setUpTestData.__func__(cls)

    def comando(self, **opciones):
        salida = StringIO()
        call_command(
            "limpiar_pruebas_kobo", docente="DOC-TEST", aula="AULA-TEST", clei="III",
            stdout=salida, **opciones,
        )
        texto = salida.getvalue()
        huella = next(linea.split(": ", 1)[1] for linea in texto.splitlines()
                      if linea.startswith("Huella del plan:"))
        return texto, huella

    def ejecutar(self, **opciones):
        _, huella = self.comando(**opciones)
        return self.comando(
            **opciones, ejecutar=True, confirmar_plan=huella,
            confirmar_base=str(connection.settings_dict["NAME"]),
        )

    def test_vista_previa_no_modifica_registros(self):
        self.procesar()
        texto, _ = self.comando(incluir_horarios=True)
        self.assertIn("VISTA PREVIA", texto)
        self.assertEqual(Asistencia.objects.count(), 1)
        self.assertEqual(SesionClase.objects.count(), 1)

    def test_limpia_y_conserva_datos_maestros_y_marcas_de_importacion(self):
        self.procesar()
        self.ejecutar(incluir_horarios=True)
        self.assertFalse(Asistencia.objects.exists())
        self.assertFalse(SesionClase.objects.exists())
        self.assertFalse(Horario.objects.exists())
        marca = RegistroImportacionKobo.objects.get()
        self.assertIsNone(marca.asistencia_id)
        self.assertEqual(marca.estado, "EXISTENTE")
        self.assertFalse(self.procesar()["importacion_creada"])
        self.assertEqual(Estudiante.objects.count(), 2)
        self.assertEqual(Docente.objects.count(), 1)
        self.assertEqual(MatriculaCLEI.objects.count(), 1)
        self.assertEqual(FormularioKobo.objects.count(), 1)

    def test_reimportacion_explicita_permite_recrear_sesion(self):
        self.procesar()
        self.ejecutar(incluir_horarios=True, permitir_reimportacion=True)
        self.assertFalse(RegistroImportacionKobo.objects.exists())
        resultado = self.procesar()
        self.assertTrue(resultado["sesion_creada"])
        self.assertTrue(resultado["asistencia_creada"])

    def test_rechaza_base_no_confirmada(self):
        _, huella = self.comando()
        with self.assertRaises(CommandError):
            self.comando(ejecutar=True, confirmar_plan=huella, confirmar_base="otra-base")
        self.assertEqual(SesionClase.objects.count(), 1)

    def test_rechaza_huella_desactualizada(self):
        _, huella = self.comando()
        SesionClase.objects.filter(pk=self.sesion.pk).update(observaciones="Cambio ficticio")
        with self.assertRaises(CommandError):
            self.comando(
                ejecutar=True, confirmar_plan=huella,
                confirmar_base=str(connection.settings_dict["NAME"]),
            )
        self.assertEqual(SesionClase.objects.count(), 1)

    def test_alertas_exigen_reinicio_explicito(self):
        self.procesar(estado_asistencia="AUSENTE")
        with self.assertRaises(CommandError):
            self.ejecutar()
        self.assertEqual(CasoAlerta.objects.count(), 1)
        self.ejecutar(reiniciar_alertas=True)
        self.assertFalse(CasoAlerta.objects.exists())
        self.assertFalse(Asistencia.objects.exists())

    def test_no_reinicia_historia_si_hay_asistencias_fuera_del_rango(self):
        self.procesar(estado_asistencia="AUSENTE")
        self.procesar(_id=124, fecha_sesion="2026-10-21")
        with self.assertRaises(CommandError):
            self.ejecutar(reiniciar_alertas=True, hasta="2026-10-20")
        self.assertEqual(Asistencia.objects.count(), 2)
        self.assertEqual(CasoAlerta.objects.count(), 1)

    def test_no_borra_horario_usado_fuera_del_rango(self):
        SesionClase.objects.create(
            horario=self.sesion.horario, fecha="2026-10-21",
            hora_inicio=self.sesion.hora_inicio, hora_fin=self.sesion.hora_fin,
        )
        self.ejecutar(incluir_horarios=True, hasta="2026-10-20")
        self.assertEqual(SesionClase.objects.count(), 1)
        self.assertEqual(Horario.objects.count(), 1)

    def test_no_borra_otro_grupo_del_docente(self):
        aula = Aula.objects.create(
            institucion=self.aula.institucion, nombre="Otro grupo ficticio", codigo_kobo="OTRA",
        )
        otra = SesionClase.objects.create(
            aula=aula, docente=self.docente, clei=self.clei, fecha="2026-10-20",
            hora_inicio=self.sesion.hora_inicio, hora_fin=self.sesion.hora_fin,
        )
        self.ejecutar()
        self.assertEqual(list(SesionClase.objects.values_list("pk", flat=True)), [otra.pk])

    def test_rango_invalido_se_rechaza(self):
        for opciones in (
            {"desde": "2026-02-30"}, {"desde": "2026-10-21", "hasta": "2026-10-20"},
        ):
            with self.subTest(opciones=opciones), self.assertRaises(CommandError):
                self.comando(**opciones)

    def test_elimina_dependencias_de_alertas_y_revalidaciones(self):
        resultado = self.procesar(estado_asistencia="AUSENTE")
        usuario = get_user_model().objects.create_user(username="responsable-ficticio")
        RevalidacionAsistencia.objects.create(
            asistencia_id=resultado["asistencia_id"], decision="APROBADA",
            tipo_autorizador="COORDINADOR", autorizado_por="Responsable ficticio",
            registrado_por=usuario, motivo="Prueba ficticia", fecha_decision=date(2026, 10, 21),
        )
        alerta = Alerta.objects.create(
            estudiante=self.estudiante, nivel="TEMPRANA", cantidad_ausencias=1,
        )
        Seguimiento.objects.create(
            alerta=alerta, responsable="Responsable ficticio",
            accion_realizada="Prueba", fecha_seguimiento=timezone.now(),
        )
        self.ejecutar(reiniciar_alertas=True)
        for modelo in (RevalidacionAsistencia, Seguimiento, Alerta, CasoAlerta, Asistencia):
            self.assertFalse(modelo.objects.exists())
        self.assertTrue(get_user_model().objects.filter(pk=usuario.pk).exists())

    def test_fallo_revierte_eliminaciones_y_desvinculacion_de_importaciones(self):
        resultado = self.procesar()
        borrar_original = QuerySet.delete

        def borrar(queryset):
            if queryset.model._meta.model_name == "sesionclase":
                raise DatabaseError("Fallo simulado")
            return borrar_original(queryset)

        with patch.object(QuerySet, "delete", autospec=True, side_effect=borrar):
            with self.assertRaises(CommandError):
                self.ejecutar()
        self.assertEqual(SesionClase.objects.count(), 1)
        self.assertEqual(Asistencia.objects.count(), 1)
        self.assertEqual(RegistroImportacionKobo.objects.get().asistencia_id, resultado["asistencia_id"])
