from datetime import date, time
from io import StringIO
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.management import call_command, CommandError
from django.test import TestCase

from .kobo_client import KoboClient
from .models import (
    AsignacionDocenteCLEI, Asistencia, Aula, CLEI, CasoAlerta, Departamento,
    Docente, Estudiante, FormularioKobo, Horario, Institucion, MatriculaCLEI,
    Proyecto, RegistroImportacionKobo, SesionClase, Zona,
)
from .services import procesar_respuesta_kobo, validar_asistencia_kobo


class ImportacionContextoKoboTests(TestCase):
    UID = "formulario-grupo-ficticio"

    @classmethod
    def setUpTestData(cls):
        proyecto = Proyecto.objects.create(nombre="Proyecto ficticio")
        departamento = Departamento.objects.create(nombre="Departamento ficticio")
        zona = Zona.objects.create(
            proyecto=proyecto, departamento=departamento, nombre="Zona ficticia",
        )
        institucion = Institucion.objects.create(
            zona=zona, nombre="Institución ficticia", codigo_kobo="INST-TEST",
        )
        cls.aula = Aula.objects.create(
            institucion=institucion, nombre="Aula ficticia", codigo_kobo="AULA-TEST",
        )
        cls.clei = CLEI.objects.create(
            codigo="III", nombre="CLEI III", horas_presenciales_requeridas=400,
        )
        cls.docente = Docente.objects.create(
            institucion=institucion, codigo="DOC-TEST",
            nombres="Docente", apellidos="Ficticio",
        )
        cls.formulario = FormularioKobo.objects.create(
            formulario_uid=cls.UID, docente=cls.docente, aula=cls.aula, clei=cls.clei,
        )
        cls.asignacion = AsignacionDocenteCLEI.objects.create(
            docente=cls.docente, aula=cls.aula, clei=cls.clei,
            fecha_inicio=date(2026, 10, 1), fecha_fin=date(2026, 10, 31),
        )
        cls.estudiante = Estudiante.objects.create(
            codigo="EST-TEST", aula=cls.aula, clei=cls.clei,
        )
        cls.otro_estudiante = Estudiante.objects.create(
            codigo="EST-TEST-OTRO", aula=cls.aula, clei=cls.clei,
        )
        cls.matricula = MatriculaCLEI.objects.create(
            estudiante=cls.estudiante, aula=cls.aula, clei=cls.clei,
            fecha_inicio=date(2026, 10, 1), fecha_fin=date(2026, 10, 31),
        )
        horario = Horario.objects.create(
            docente=cls.docente, aula=cls.aula, clei=cls.clei,
            dia_semana=1, hora_inicio=time(8), hora_fin=time(10),
        )
        cls.sesion = SesionClase.objects.create(
            horario=horario, fecha=date(2026, 10, 20),
            hora_inicio=time(8), hora_fin=time(10), estado="REALIZADA",
        )

    def registro(self, **cambios):
        datos = {
            "_id": 123, "codigo_docente": "DOC-TEST",
            "codigo_institucion": "INST-TEST", "codigo_aula": "AULA-TEST",
            "clei": "III", "codigo_estudiante": "EST-TEST",
            "fecha_sesion": "2026-10-20", "hora_inicio": "08:00:00.000-05:00",
            "hora_fin": "10:00:00.000-05:00", "estado_asistencia": "PRESENTE",
        }
        datos.update(cambios)
        return datos

    def procesar(self, **cambios):
        return procesar_respuesta_kobo(self.registro(**cambios), formulario_uid=self.UID)

    def test_crea_asistencia_solo_para_estudiante_del_envio(self):
        resultado = self.procesar()
        asistencia = Asistencia.objects.get(pk=resultado["asistencia_id"])
        self.assertEqual(asistencia.matricula_id, self.matricula.pk)
        self.assertEqual(asistencia.estudiante_id, self.estudiante.pk)
        self.assertFalse(self.otro_estudiante.asistencias.exists())
        self.assertEqual(asistencia.sesion_id, self.sesion.pk)
        self.assertEqual(RegistroImportacionKobo.objects.get().formulario_uid, self.UID)

    def test_ausencia_notifica_una_vez_y_actualiza_caso(self):
        with patch("seguimiento.services.notificar_caso_alerta_segura") as notificar:
            with self.captureOnCommitCallbacks(execute=True):
                primera = self.procesar(estado_asistencia="AUSENTE")
                repetida = self.procesar(estado_asistencia="AUSENTE")
                otro_envio = self.procesar(_id=124, estado_asistencia="AUSENTE")
        notificar.assert_called_once()
        self.assertTrue(primera["asistencia_creada"])
        self.assertFalse(repetida["importacion_creada"])
        self.assertFalse(otro_envio["asistencia_creada"])
        self.assertEqual(CasoAlerta.objects.get().ausencias_efectivas, 1)
        self.assertEqual(Asistencia.objects.count(), 1)

    def test_rechaza_contexto_manipulado_incluso_con_codigos_existentes(self):
        otro_docente = Docente.objects.create(
            institucion=self.docente.institucion, codigo="DOC-TEST-OTRO",
            nombres="Otro", apellidos="Ficticio",
        )
        otros = {
            "codigo_docente": otro_docente.codigo, "codigo_aula": "OTRA-AULA",
            "codigo_institucion": "OTRA-INST", "clei": "IV",
        }
        for campo, valor in otros.items():
            with self.subTest(campo=campo), self.assertRaises(ValidationError):
                self.procesar(**{campo: valor})
        self.assertFalse(Asistencia.objects.exists())
        self.assertFalse(RegistroImportacionKobo.objects.exists())

    def test_uid_declarado_en_envio_no_sustituye_origen(self):
        with self.assertRaises(ValidationError):
            procesar_respuesta_kobo(
                self.registro(formulario_uid=self.UID), formulario_uid="no-configurado",
            )

    def test_rechaza_formulario_desconocido(self):
        with self.assertRaises(ValidationError):
            procesar_respuesta_kobo(self.registro(), formulario_uid="no-configurado")

    def test_rechaza_formulario_desactivado(self):
        FormularioKobo.objects.filter(pk=self.formulario.pk).update(activo=False)
        with self.assertRaises(ValidationError):
            self.procesar()

    def test_rechaza_contexto_institucional_inactivo(self):
        for objeto, campo in (
            (self.docente, "activo"), (self.aula, "activa"),
            (self.aula.institucion, "activa"), (self.clei, "activo"),
        ):
            type(objeto).objects.filter(pk=objeto.pk).update(**{campo: False})
            with self.subTest(modelo=objeto._meta.label), self.assertRaises(ValidationError):
                self.procesar()
            type(objeto).objects.filter(pk=objeto.pk).update(**{campo: True})

    def test_reimportacion_procesada_se_conserva_aunque_formulario_se_desactive(self):
        self.procesar()
        FormularioKobo.objects.filter(pk=self.formulario.pk).update(activo=False)
        self.assertFalse(self.procesar()["importacion_creada"])

    def test_rechaza_asignacion_ausente_inactiva_o_fuera_de_vigencia(self):
        casos = (
            {"activa": False},
            {"activa": True, "fecha_inicio": date(2026, 10, 21)},
            {"fecha_inicio": date(2026, 10, 1), "fecha_fin": date(2026, 10, 19)},
        )
        for cambios in casos:
            AsignacionDocenteCLEI.objects.filter(pk=self.asignacion.pk).update(**cambios)
            with self.subTest(cambios=cambios), self.assertRaises(ValidationError):
                self.procesar()
        self.asignacion.delete()
        with self.assertRaises(ValidationError):
            self.procesar()

    def test_rechaza_matricula_ausente_o_fuera_de_vigencia(self):
        for cambios in (
            {"fecha_inicio": date(2026, 10, 21)},
            {"fecha_inicio": date(2026, 10, 1), "fecha_fin": date(2026, 10, 19)},
            {"fecha_fin": None, "estado": "RETIRADA"},
        ):
            MatriculaCLEI.objects.filter(pk=self.matricula.pk).update(**cambios)
            with self.subTest(cambios=cambios), self.assertRaises(ValidationError):
                self.procesar()
        self.matricula.delete()
        with self.assertRaises(ValidationError):
            self.procesar()

    def test_fechas_limite_de_vigencia_son_inclusivas(self):
        AsignacionDocenteCLEI.objects.filter(pk=self.asignacion.pk).update(
            fecha_inicio=self.sesion.fecha, fecha_fin=self.sesion.fecha,
        )
        MatriculaCLEI.objects.filter(pk=self.matricula.pk).update(
            fecha_inicio=self.sesion.fecha, fecha_fin=self.sesion.fecha,
        )
        self.assertTrue(self.procesar()["asistencia_creada"])

    def test_rechaza_fecha_y_horas_invalidas_sin_escrituras(self):
        for cambios in (
            {"fecha_sesion": "2026-02-30"}, {"hora_inicio": "25:00"},
            {"hora_inicio": "08:00:00-basura"}, {"hora_fin": "09:99"},
            {"hora_fin": "07:00"}, {"hora_fin": "08:00"},
            {"hora_fin": None},
        ):
            with self.subTest(cambios=cambios), self.assertRaises(ValidationError):
                self.procesar(**cambios)
        self.assertFalse(Asistencia.objects.exists())
        self.assertFalse(RegistroImportacionKobo.objects.exists())

    def test_hora_final_contradictoria_no_modifica_sesion(self):
        with self.assertRaises(ValidationError):
            self.procesar(hora_fin="11:00")
        self.sesion.refresh_from_db()
        self.assertEqual(self.sesion.hora_fin, time(10))

    def test_conserva_formulario_original_sin_vinculacion_ni_hora_fin(self):
        self.asignacion.delete()
        registro = self.registro()
        registro.pop("hora_fin")
        resultado = procesar_respuesta_kobo(
            registro, formulario_uid=KoboClient.LEGACY_FORM_UID,
        )
        self.assertTrue(resultado["asistencia_creada"])

    def test_validar_no_crea_asistencias_ni_importaciones(self):
        validar_asistencia_kobo(self.registro(), formulario_uid=self.UID)
        self.assertFalse(Asistencia.objects.exists())
        self.assertFalse(RegistroImportacionKobo.objects.exists())

    def test_sesion_inexistente_se_crea_automaticamente(self):
        resultado = self.procesar(fecha_sesion="2026-10-21")
        self.assertTrue(resultado["sesion_creada"])
        sesion = SesionClase.objects.get(pk=resultado["sesion_id"])
        self.assertEqual(sesion.estado, "REALIZADA")
        self.assertIsNone(sesion.horario_id)
        self.assertEqual(sesion.asignacion_id, self.asignacion.pk)
        self.assertEqual(Asistencia.objects.count(), 1)

    def test_sesion_cancelada_no_admite_asistencia(self):
        SesionClase.objects.filter(pk=self.sesion.pk).update(estado="CANCELADA")
        with self.assertRaises(ValidationError):
            self.procesar()
        self.assertFalse(Asistencia.objects.exists())

    def test_error_al_registrar_importacion_revierte_asistencia(self):
        with patch.object(RegistroImportacionKobo, "save", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.procesar()
        self.assertFalse(Asistencia.objects.exists())
        self.assertFalse(CasoAlerta.objects.exists())
        self.assertTrue(self.procesar()["asistencia_creada"])

    def test_mismo_id_en_dos_formularios_conserva_ambas_importaciones(self):
        FormularioKobo.objects.create(
            formulario_uid="otro-formulario-ficticio",
            docente=self.docente, aula=self.aula, clei=self.clei,
        )
        self.procesar()
        resultado = procesar_respuesta_kobo(
            self.registro(), formulario_uid="otro-formulario-ficticio",
        )
        self.assertTrue(resultado["importacion_creada"])
        self.assertFalse(resultado["asistencia_creada"])
        self.assertEqual(RegistroImportacionKobo.objects.count(), 2)

    def test_comando_configura_uid_actual_sin_crear_datos_institucionales(self):
        with patch.object(KoboClient, "FORM_UID", "formulario-nuevo-ficticio"):
            for _ in range(2):
                call_command(
                    "configurar_formulario_kobo", docente="DOC-TEST",
                    aula="AULA-TEST", clei="III", stdout=StringIO(),
                )
        self.assertEqual(FormularioKobo.objects.count(), 2)
        self.assertEqual(Estudiante.objects.count(), 2)
        self.assertEqual(Docente.objects.count(), 1)

    def test_comando_no_reasigna_uid_existente(self):
        otra_aula = Aula.objects.create(
            institucion=self.aula.institucion, nombre="Otra aula ficticia",
            codigo_kobo="OTRA-AULA",
        )
        with self.assertRaises(CommandError):
            call_command(
                "configurar_formulario_kobo", formulario_uid=self.UID,
                docente="DOC-TEST", aula=otra_aula.codigo_kobo, clei="III",
                stdout=StringIO(),
            )
        self.formulario.refresh_from_db()
        self.assertEqual(self.formulario.aula_id, self.aula.pk)

    def test_comando_rechaza_referencias_inexistentes_sin_crearlas(self):
        with self.assertRaises(CommandError):
            call_command(
                "configurar_formulario_kobo", formulario_uid="nuevo-ficticio",
                docente="DOC-INEXISTENTE", aula="AULA-TEST", clei="III",
                stdout=StringIO(),
            )
        self.assertEqual(FormularioKobo.objects.count(), 1)
        self.assertEqual(Docente.objects.count(), 1)

    def test_sincronizacion_transmite_uid_real_del_cliente(self):
        from .services import sincronizar_asistencias_kobo

        with patch("seguimiento.services.KoboClient") as cliente:
            cliente.return_value.FORM_UID = self.UID
            cliente.return_value.iterar_respuestas.return_value = [self.registro()]
            resumen = sincronizar_asistencias_kobo()
        self.assertEqual(resumen["asistencias_creadas"], 1)
        self.assertEqual(RegistroImportacionKobo.objects.get().formulario_uid, self.UID)
