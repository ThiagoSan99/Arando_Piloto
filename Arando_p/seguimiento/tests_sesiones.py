from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timezone as dt_timezone
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase

from . import tests_kobo
from .models import (
    Asistencia, CasoAlerta, FormularioKobo, Horario, MatriculaCLEI,
    RegistroImportacionKobo, RevalidacionAsistencia, SesionClase,
)
from .serializers import SesionClaseSerializer
from .services import calcular_horas_presenciales, procesar_respuesta_kobo, validar_asistencia_kobo


class SesionesAutomaticasTests(TestCase):
    UID = "formulario-grupo-ficticio"
    registro = tests_kobo.ImportacionContextoKoboTests.registro
    procesar = tests_kobo.ImportacionContextoKoboTests.procesar

    @classmethod
    def setUpTestData(cls):
        tests_kobo.ImportacionContextoKoboTests.setUpTestData.__func__(cls)

    def test_creacion_no_genera_horarios_y_reimportacion_reutiliza_sesion(self):
        horarios = Horario.objects.count()
        primera = self.procesar(fecha_sesion="2026-10-21")
        self.procesar(fecha_sesion="2026-10-21")
        otra = self.procesar(_id=124, fecha_sesion="2026-10-21")
        self.assertTrue(primera["sesion_creada"])
        self.assertFalse(otra["sesion_creada"])
        self.assertEqual(Horario.objects.count(), horarios)
        self.assertEqual(SesionClase.objects.count(), 2)
        self.assertEqual(Asistencia.objects.count(), 1)

    def test_varios_estudiantes_comparten_sesion_y_reconocen_cinco_horas(self):
        matricula_otro = MatriculaCLEI.objects.create(
            estudiante=self.otro_estudiante, aula=self.aula, clei=self.clei,
            fecha_inicio=date(2026, 10, 1),
        )
        primera = self.procesar(fecha_sesion="2026-10-21")
        segunda = self.procesar(
            _id=124, fecha_sesion="2026-10-21", codigo_estudiante=self.otro_estudiante.codigo,
        )
        self.assertEqual(primera["sesion_id"], segunda["sesion_id"])
        self.assertEqual(calcular_horas_presenciales(self.matricula)["horas_cumplidas"], 5)
        self.assertEqual(calcular_horas_presenciales(matricula_otro)["horas_cumplidas"], 5)

    def test_programada_se_confirma_y_conserva_horario(self):
        SesionClase.objects.filter(pk=self.sesion.pk).update(estado="PROGRAMADA")
        self.procesar()
        self.sesion.refresh_from_db()
        self.assertEqual(self.sesion.estado, "REALIZADA")
        self.assertIsNotNone(self.sesion.horario_id)
        self.assertEqual(self.sesion.asignacion_id, self.asignacion.pk)

    def test_reprogramada_no_se_confirma_implicitamente(self):
        SesionClase.objects.filter(pk=self.sesion.pk).update(estado="REPROGRAMADA")
        with self.assertRaises(ValidationError):
            self.procesar()
        self.sesion.refresh_from_db()
        self.assertEqual(self.sesion.estado, "REPROGRAMADA")

    def test_rechaza_futuro_y_acepta_fecha_local_de_bogota(self):
        # En UTC ya es el día 22, pero en Colombia aún es el 21.
        instante = datetime(2026, 10, 22, 2, tzinfo=dt_timezone.utc)
        with patch("seguimiento.services.timezone.now", return_value=instante):
            with self.assertRaises(ValidationError):
                self.procesar(fecha_sesion="2026-10-22")
            self.assertTrue(self.procesar(fecha_sesion="2026-10-21")["sesion_creada"])

    def test_validacion_de_sesion_nueva_no_escribe(self):
        resultado = validar_asistencia_kobo(
            self.registro(fecha_sesion="2026-10-21"), formulario_uid=self.UID,
        )
        self.assertIsNone(resultado["sesion_id"])
        self.assertEqual(SesionClase.objects.count(), 1)

    def test_error_en_importacion_revierte_sesion_nueva_y_correo(self):
        with patch.object(RegistroImportacionKobo, "save", side_effect=RuntimeError):
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                with self.assertRaises(RuntimeError):
                    self.procesar(fecha_sesion="2026-10-21", estado_asistencia="AUSENTE")
        self.assertEqual(callbacks, [])
        self.assertEqual(SesionClase.objects.count(), 1)
        self.assertFalse(Asistencia.objects.exists())
        self.assertFalse(CasoAlerta.objects.exists())
        self.assertTrue(self.procesar(fecha_sesion="2026-10-21")["sesion_creada"])

    def test_sin_matricula_no_crea_sesion(self):
        self.matricula.delete()
        with self.assertRaises(ValidationError):
            self.procesar(fecha_sesion="2026-10-21")
        self.assertEqual(SesionClase.objects.count(), 1)

    def test_revalidacion_y_cancelacion_conservan_regla_de_horas(self):
        with patch("seguimiento.services.notificar_caso_alerta_segura"):
            resultado = self.procesar(fecha_sesion="2026-10-21", estado_asistencia="AUSENTE")
        self.assertEqual(calcular_horas_presenciales(self.matricula)["horas_cumplidas"], 0)
        usuario = get_user_model().objects.create_user(username="usuario-ficticio")
        RevalidacionAsistencia.objects.create(
            asistencia_id=resultado["asistencia_id"], decision="APROBADA",
            tipo_autorizador="COORDINADOR", autorizado_por="Responsable ficticio",
            registrado_por=usuario, motivo="Motivo ficticio", fecha_decision=date(2026, 10, 22),
        )
        self.assertEqual(calcular_horas_presenciales(self.matricula)["horas_cumplidas"], 5)
        SesionClase.objects.filter(pk=resultado["sesion_id"]).update(estado="CANCELADA")
        self.assertEqual(calcular_horas_presenciales(self.matricula)["horas_cumplidas"], 0)

    def test_bd_impide_duplicados_incluso_con_otro_horario(self):
        otro_horario = Horario.objects.create(
            docente=self.docente, aula=self.aula, clei=self.clei,
            dia_semana=1, hora_inicio=time(8), hora_fin=time(10),
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            SesionClase.objects.create(
                horario=otro_horario, fecha=self.sesion.fecha,
                hora_inicio=time(8), hora_fin=time(10), estado="REALIZADA",
            )

    def test_bd_impide_hora_final_invalida(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            SesionClase.objects.filter(pk=self.sesion.pk).update(hora_fin=time(7))

    def test_serializador_mantiene_contexto_sin_horario(self):
        resultado = self.procesar(fecha_sesion="2026-10-21")
        sesion = SesionClase.objects.get(pk=resultado["sesion_id"])
        datos = SesionClaseSerializer(sesion).data
        self.assertIsNone(datos["horario"])
        self.assertEqual(datos["docente_codigo"], self.docente.codigo)
        self.assertEqual(datos["aula_nombre"], self.aula.nombre)
        self.assertEqual(datos["clei_codigo"], self.clei.codigo)

    def test_cada_ausencia_notifica_aun_en_riesgo_rojo(self):
        with patch("seguimiento.services.notificar_caso_alerta_segura") as notificar:
            with self.captureOnCommitCallbacks(execute=True):
                for numero, dia in enumerate((20, 21, 22, 23)):
                    self.procesar(
                        _id=200 + numero, fecha_sesion=f"2026-10-{dia}",
                        estado_asistencia="AUSENTE",
                    )
        self.assertEqual(notificar.call_count, 4)
        self.assertEqual(CasoAlerta.objects.count(), 1)
        self.assertEqual(CasoAlerta.objects.get().nivel_actual, "ROJA")


@skipUnless(connection.vendor == "postgresql", "Requiere PostgreSQL y conexiones independientes.")
class ConcurrenciaSesionesTests(TransactionTestCase):
    UID = "formulario-grupo-ficticio"
    registro = tests_kobo.ImportacionContextoKoboTests.registro

    def setUp(self):
        tests_kobo.ImportacionContextoKoboTests.setUpTestData.__func__(type(self))

    def ejecutar_en_paralelo(self, trabajos):
        barrera = Barrier(2)

        def ejecutar(trabajo):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET statement_timeout = '15s'")
                    cursor.execute("SET lock_timeout = '10s'")
                barrera.wait(timeout=10)
                registro, uid = trabajo
                return procesar_respuesta_kobo(registro, formulario_uid=uid)
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futuros = [pool.submit(ejecutar, trabajo) for trabajo in trabajos]
            return [futuro.result(timeout=30) for futuro in futuros]

    def test_mismo_envio_concurrente(self):
        registro = self.registro(fecha_sesion="2026-10-21", estado_asistencia="AUSENTE")
        with patch("seguimiento.services.notificar_caso_alerta_segura") as notificar:
            resultados = self.ejecutar_en_paralelo([(registro, self.UID), (registro, self.UID)])
        self.assertEqual(sum(r["asistencia_creada"] for r in resultados), 1)
        self.assertEqual(SesionClase.objects.count(), 2)
        self.assertEqual(RegistroImportacionKobo.objects.count(), 1)
        self.assertEqual(CasoAlerta.objects.count(), 1)
        notificar.assert_called_once()

    def test_distintos_formularios_y_estudiantes_comparten_sesion(self):
        otro_uid = "otro-formulario-ficticio"
        FormularioKobo.objects.create(
            formulario_uid=otro_uid, docente=self.docente, aula=self.aula, clei=self.clei,
        )
        MatriculaCLEI.objects.create(
            estudiante=self.otro_estudiante, aula=self.aula, clei=self.clei,
            fecha_inicio=date(2026, 10, 1),
        )
        resultados = self.ejecutar_en_paralelo([
            (self.registro(fecha_sesion="2026-10-21"), self.UID),
            (self.registro(fecha_sesion="2026-10-21", codigo_estudiante=self.otro_estudiante.codigo), otro_uid),
        ])
        self.assertEqual(sum(r["sesion_creada"] for r in resultados), 1)
        self.assertEqual(Asistencia.objects.count(), 2)
        self.assertEqual(SesionClase.objects.count(), 2)
