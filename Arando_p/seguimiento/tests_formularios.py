from io import StringIO
from unittest.mock import patch

from django.core.management import call_command, CommandError
from django.test import TestCase

from . import tests_kobo
from .models import FormularioKobo


class RecepcionFormulariosTests(TestCase):
    UID = "formulario-grupo-ficticio"

    @classmethod
    def setUpTestData(cls):
        tests_kobo.ImportacionContextoKoboTests.setUpTestData.__func__(cls)
        cls.segundo_uid = "segundo-formulario-ficticio"
        FormularioKobo.objects.create(
            formulario_uid=cls.segundo_uid, docente=cls.docente, aula=cls.aula, clei=cls.clei,
        )

    def resumen(self):
        return dict(respuestas_consultadas=0, asistencias_creadas=0, envios_ya_procesados=0,
                    asistencias_existentes=0, errores=[])

    def test_dos_uid_se_consultan_sin_cambiar_env_y_sin_repetir(self):
        with patch("seguimiento.management.commands.sincronizar_kobo.sincronizar_asistencias_kobo",
                   return_value=self.resumen()) as sincronizar:
            call_command("sincronizar_kobo", formularios=[self.UID, self.segundo_uid, self.UID], stdout=StringIO())
        self.assertEqual(sincronizar.call_count, 2)
        self.assertEqual(sincronizar.call_args_list[0].kwargs["formulario_uid"], self.UID)
        self.assertEqual(sincronizar.call_args_list[1].kwargs["formulario_uid"], self.segundo_uid)

    def test_todos_omite_desactivados(self):
        FormularioKobo.objects.filter(formulario_uid=self.segundo_uid).update(activo=False)
        with patch("seguimiento.management.commands.sincronizar_kobo.sincronizar_asistencias_kobo",
                   return_value=self.resumen()) as sincronizar:
            call_command("sincronizar_kobo", todos=True, stdout=StringIO())
        sincronizar.assert_called_once_with(limite=100, formulario_uid=self.UID)

    def test_sin_argumentos_consulta_todos_los_activos_e_ignora_uid_de_env(self):
        with patch("seguimiento.management.commands.sincronizar_kobo.KoboClient.FORM_UID", "otro-uid-del-env"):
            with patch("seguimiento.management.commands.sincronizar_kobo.sincronizar_asistencias_kobo",
                       return_value=self.resumen()) as sincronizar:
                call_command("sincronizar_kobo", stdout=StringIO())
        self.assertEqual(sincronizar.call_count, 2)
        self.assertEqual({llamada.kwargs["formulario_uid"] for llamada in sincronizar.call_args_list},
                         {self.UID, self.segundo_uid})

    def test_sin_argumentos_omite_desactivados(self):
        FormularioKobo.objects.filter(formulario_uid=self.segundo_uid).update(activo=False)
        with patch("seguimiento.management.commands.sincronizar_kobo.sincronizar_asistencias_kobo",
                   return_value=self.resumen()) as sincronizar:
            call_command("sincronizar_kobo", stdout=StringIO())
        sincronizar.assert_called_once_with(limite=100, formulario_uid=self.UID)

    def test_sin_activos_no_consulta_el_uid_de_env(self):
        FormularioKobo.objects.update(activo=False)
        with patch("seguimiento.management.commands.sincronizar_kobo.sincronizar_asistencias_kobo") as sincronizar:
            with self.assertRaisesRegex(CommandError, "No hay formularios activos"):
                call_command("sincronizar_kobo", stdout=StringIO())
        sincronizar.assert_not_called()

    def test_seleccion_explicita_sigue_limitando_la_consulta(self):
        with patch("seguimiento.management.commands.sincronizar_kobo.sincronizar_asistencias_kobo",
                   return_value=self.resumen()) as sincronizar:
            call_command("sincronizar_kobo", formularios=[self.segundo_uid], stdout=StringIO())
        sincronizar.assert_called_once_with(limite=100, formulario_uid=self.segundo_uid)

    def test_uid_desconocido_bloquea_todo_lote_antes_de_consultar_kobo(self):
        with patch("seguimiento.management.commands.sincronizar_kobo.sincronizar_asistencias_kobo") as sincronizar:
            with self.assertRaises(CommandError):
                call_command("sincronizar_kobo", formularios=[self.UID, "desconocido"], stdout=StringIO())
        sincronizar.assert_not_called()

    def test_fallo_de_un_formulario_no_impide_consultar_otro(self):
        with patch("seguimiento.management.commands.sincronizar_kobo.sincronizar_asistencias_kobo",
                   side_effect=[RuntimeError("detalle privado"), self.resumen()]) as sincronizar:
            salida = StringIO()
            with self.assertRaises(CommandError):
                call_command("sincronizar_kobo", formularios=[self.UID, self.segundo_uid],
                             stdout=StringIO(), stderr=salida)
        self.assertEqual(sincronizar.call_count, 2)
        self.assertNotIn("detalle privado", salida.getvalue())

    def test_fallo_de_correo_se_distingue_de_errores_de_importacion(self):
        resumen = self.resumen()
        resumen.update(asistencias_creadas=1, correos_fallidas=1)
        with patch("seguimiento.management.commands.sincronizar_kobo.sincronizar_asistencias_kobo",
                   return_value=resumen):
            salida = StringIO()
            with self.assertRaises(CommandError):
                call_command("sincronizar_kobo", formularios=[self.UID], stdout=salida)
        self.assertIn("Errores de importación: 0", salida.getvalue())
        self.assertIn("Correos fallidos: 1", salida.getvalue())
        self.assertIn("Asistencias creadas: 1", salida.getvalue())

    def test_diagnostico_local_indica_grupo_y_matriculas(self):
        salida = StringIO()
        call_command("verificar_formulario_kobo", formulario_uid=self.UID,
                     fecha="2026-10-20", stdout=salida)
        self.assertIn("matrículas compatibles vigentes: 1", salida.getvalue())
        self.assertIn("Configuración local válida", salida.getvalue())

    def test_diagnostico_uid_no_registrado_explica_comando(self):
        with self.assertRaisesRegex(CommandError, "configurar_formulario_kobo"):
            call_command("verificar_formulario_kobo", formulario_uid="desconocido", stdout=StringIO())

    def test_diagnostico_rechaza_fecha_fuera_de_asignacion(self):
        with self.assertRaises(CommandError):
            call_command("verificar_formulario_kobo", formulario_uid=self.UID,
                         fecha="2026-09-01", stdout=StringIO(), stderr=StringIO())

    def test_servicio_pasa_uid_explicitamente_al_cliente(self):
        from .services import sincronizar_asistencias_kobo

        with patch("seguimiento.services.KoboClient") as cliente:
            cliente.return_value.iterar_respuestas.return_value = []
            sincronizar_asistencias_kobo(formulario_uid=self.segundo_uid)
        cliente.assert_called_once_with(formulario_uid=self.segundo_uid)

    def metadatos(self):
        contexto = dict(codigo_docente="DOC-TEST", codigo_institucion="INST-TEST",
                        codigo_aula="AULA-TEST", clei="III")
        survey = [{"name": campo, "type": "calculate", "calculation": repr(valor)}
                  for campo, valor in contexto.items()]
        survey += [{"name": campo, "type": tipo} for campo, tipo in (
            ("fecha_sesion", "date"), ("hora_inicio", "time"), ("hora_fin", "time"),
            ("estado_asistencia", "select_one"),
        )]
        survey.append({"name": "codigo_estudiante", "type": "select_one", "select_from_list_name": "estudiantes"})
        return {"content": {"survey": survey, "choices": [
            {"list_name": "estudiantes", "name": "EST-TEST"},
            {"list_name": "estudiantes", "name": "EST-TEST-OTRO"},
        ]}}

    def test_inspeccion_solo_metadatos_cuenta_opciones_y_matriculas(self):
        with patch("seguimiento.management.commands.inspeccionar_formularios_kobo.KoboClient") as cliente:
            cliente.return_value.obtener_formulario.return_value = self.metadatos()
            salida = StringIO()
            call_command("inspeccionar_formularios_kobo", formularios=[self.UID],
                         fecha="2026-10-20", stdout=salida)
        self.assertIn("Opciones de estudiante: 2; con matrícula compatible: 1", salida.getvalue())
        self.assertIn("Opciones sin matrícula compatible: 1", salida.getvalue())
        cliente.return_value.iterar_respuestas.assert_not_called()

    def test_inspeccion_no_ejecuta_expresiones_de_calculo(self):
        datos = self.metadatos()
        datos["content"]["survey"][0]["calculation"] = "1 + 2"
        with patch("seguimiento.management.commands.inspeccionar_formularios_kobo.KoboClient") as cliente:
            cliente.return_value.obtener_formulario.return_value = datos
            with self.assertRaises(CommandError):
                call_command("inspeccionar_formularios_kobo", formularios=[self.UID], stdout=StringIO())

    def test_inspeccion_rechaza_codigos_repetidos_en_selector(self):
        datos = self.metadatos()
        datos["content"]["choices"].append(datos["content"]["choices"][0])
        with patch("seguimiento.management.commands.inspeccionar_formularios_kobo.KoboClient") as cliente:
            cliente.return_value.obtener_formulario.return_value = datos
            with self.assertRaisesRegex(CommandError, "repetidos"):
                call_command("inspeccionar_formularios_kobo", formularios=[self.UID], stdout=StringIO())
