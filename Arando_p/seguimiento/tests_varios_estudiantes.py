from datetime import date
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command, CommandError
from django.test import TestCase

from . import tests_kobo
from .kobo_client import KoboClient
from .models import (
    AsignacionDocenteCLEI, Asistencia, Aula, CasoAlerta, Estudiante,
    FormularioKobo, MatriculaCLEI, RegistroImportacionKobo, SesionClase,
)


class VariosEstudiantesPorFormularioTests(TestCase):
    UID = "primer-formulario-ficticio"
    UID2 = "segundo-formulario-ficticio"
    registro = tests_kobo.ImportacionContextoKoboTests.registro

    @classmethod
    def setUpTestData(cls):
        tests_kobo.ImportacionContextoKoboTests.setUpTestData.__func__(cls)
        MatriculaCLEI.objects.create(
            estudiante=cls.otro_estudiante, aula=cls.aula, clei=cls.clei,
            fecha_inicio=date(2026, 10, 1),
        )
        cls.aula2 = Aula.objects.create(
            institucion=cls.aula.institucion, nombre="Segundo grupo ficticio", codigo_kobo="AULA-TEST-2",
        )
        AsignacionDocenteCLEI.objects.create(
            docente=cls.docente, aula=cls.aula2, clei=cls.clei, fecha_inicio=date(2026, 10, 1),
        )
        FormularioKobo.objects.create(
            formulario_uid=cls.UID2, docente=cls.docente, aula=cls.aula2, clei=cls.clei,
        )
        cls.estudiantes2 = []
        for numero in (1, 2):
            estudiante = Estudiante.objects.create(
                codigo=f"EST-GRUPO2-{numero}", aula=cls.aula2, clei=cls.clei,
            )
            MatriculaCLEI.objects.create(
                estudiante=estudiante, aula=cls.aula2, clei=cls.clei, fecha_inicio=date(2026, 10, 1),
            )
            cls.estudiantes2.append(estudiante)

    def respuestas(self):
        return {
            self.UID: [
                self.registro(_id=1, fecha_sesion="2026-10-21"),
                self.registro(_id=2, fecha_sesion="2026-10-21",
                              codigo_estudiante=self.otro_estudiante.codigo, estado_asistencia="AUSENTE"),
            ],
            self.UID2: [
                self.registro(_id=1, fecha_sesion="2026-10-21", codigo_aula=self.aula2.codigo_kobo,
                              codigo_estudiante=self.estudiantes2[0].codigo),
                self.registro(_id=2, fecha_sesion="2026-10-21", codigo_aula=self.aula2.codigo_kobo,
                              codigo_estudiante=self.estudiantes2[1].codigo, estado_asistencia="AUSENTE"),
            ],
        }

    def sincronizar(self, respuestas, uids):
        def iterar(cliente, tamano_pagina):
            return iter(respuestas[cliente.FORM_UID])

        with patch.dict("os.environ", {"KOBO_API_TOKEN": "token-ficticio-no-real"}):
            with patch.object(KoboClient, "iterar_respuestas", autospec=True, side_effect=iterar):
                call_command("sincronizar_kobo", formularios=uids, stdout=StringIO(), stderr=StringIO())

    def test_dos_formularios_reciben_varios_estudiantes_y_reimportan_sin_duplicar(self):
        with patch("seguimiento.services.notificar_caso_alerta_segura") as notificar:
            with self.captureOnCommitCallbacks(execute=True):
                self.sincronizar(self.respuestas(), [self.UID, self.UID2])
                self.sincronizar(self.respuestas(), [self.UID, self.UID2])
        # Se conserva la sesión de la fixture del día 20 y se crean dos del día 21.
        self.assertEqual(SesionClase.objects.filter(fecha="2026-10-21").count(), 2)
        self.assertEqual(Asistencia.objects.count(), 4)
        self.assertEqual(RegistroImportacionKobo.objects.count(), 4)
        self.assertEqual(CasoAlerta.objects.count(), 2)
        self.assertEqual(notificar.call_count, 2)
        for uid in (self.UID, self.UID2):
            importaciones = RegistroImportacionKobo.objects.filter(formulario_uid=uid)
            self.assertEqual(importaciones.count(), 2)
            self.assertEqual(importaciones.values("asistencia__sesion_id").distinct().count(), 1)

    def test_un_estudiante_sin_matricula_no_impide_otro_envio_valido(self):
        MatriculaCLEI.objects.filter(estudiante=self.otro_estudiante).delete()
        with self.assertRaises(CommandError):
            self.sincronizar(self.respuestas(), [self.UID])
        self.assertEqual(Asistencia.objects.count(), 1)
        self.assertEqual(Asistencia.objects.get().estudiante_id, self.estudiante.pk)
        self.assertEqual(RegistroImportacionKobo.objects.count(), 1)

    def test_estudiante_de_otro_formulario_no_se_atribuye_al_grupo(self):
        respuestas = self.respuestas()
        respuestas[self.UID][0]["codigo_estudiante"] = self.estudiantes2[0].codigo
        respuestas[self.UID] = respuestas[self.UID][:1]
        with self.assertRaises(CommandError):
            self.sincronizar(respuestas, [self.UID])
        self.assertFalse(Asistencia.objects.exists())
        self.assertFalse(SesionClase.objects.filter(fecha="2026-10-21").exists())

    def test_estados_contrarios_para_mismo_estudiante_son_conflicto(self):
        respuestas = self.respuestas()
        registro = respuestas[self.UID][0]
        respuestas[self.UID] = [registro, {**registro, "_id": 99, "estado_asistencia": "AUSENTE"}]
        with self.assertRaises(CommandError):
            self.sincronizar(respuestas, [self.UID])
        self.assertEqual(Asistencia.objects.count(), 1)
        self.assertEqual(Asistencia.objects.get().estado, "PRESENTE")
