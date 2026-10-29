from pathlib import Path
from unittest import skipUnless

from django.db import connection, DatabaseError
from django.test import TransactionTestCase

from . import tests_kobo
from .models import Asistencia, Estudiante, Horario, RegistroImportacionKobo, SesionClase


@skipUnless(connection.vendor == "postgresql", "El script manual utiliza PostgreSQL.")
@skipUnless((Path(__file__).resolve().parent.parent / "scripts" / "limpiar_piloto.sql").exists(),
            "El script SQL manual fue retirado de este checkout; se prueba el comando Django de limpieza.")
class SqlLimpiezaTests(TransactionTestCase):
    UID = "formulario-grupo-ficticio"
    registro = tests_kobo.ImportacionContextoKoboTests.registro
    procesar = tests_kobo.ImportacionContextoKoboTests.procesar

    def setUp(self):
        tests_kobo.ImportacionContextoKoboTests.setUpTestData.__func__(type(self))
        self.procesar()

    def ejecutar_sql(self, ejecutar=False, confirmar=False, reimportar=False, reiniciar=False, hasta=None):
        sql = (Path(__file__).resolve().parent.parent / "scripts" / "limpiar_piloto.sql").read_text(encoding="utf-8")
        sql = sql.replace("'arando_db'", "'" + connection.settings_dict["NAME"] + "'")
        for marcador, valor in (
            ("REEMPLAZAR_DOCENTE", "DOC-TEST"), ("REEMPLAZAR_AULA", "AULA-TEST"),
            ("REEMPLAZAR_CLEI", "III"),
        ):
            sql = sql.replace(marcador, valor)
        if ejecutar:
            sql = sql.replace("FALSE  -- EJECUTAR", "TRUE  -- EJECUTAR")
        if confirmar:
            sql = sql.replace("ROLLBACK; -- FIN:", "COMMIT; -- FIN:")
        if reimportar:
            sql = sql.replace("FALSE, -- permitir reimportar", "TRUE, -- permitir reimportar")
        if reiniciar:
            sql = sql.replace("FALSE, -- reiniciar alertas", "TRUE, -- reiniciar alertas")
        if hasta:
            sql = sql.replace("NULL, -- hasta", f"DATE '{hasta}', -- hasta")
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql)
                while cursor.nextset():
                    pass
        finally:
            connection.rollback()

    def test_vista_previa_preserva_datos(self):
        self.ejecutar_sql()
        self.assertEqual(SesionClase.objects.count(), 1)
        self.assertEqual(Asistencia.objects.count(), 1)

    def test_rollback_preserva_datos_aunque_ejecutar_sea_true(self):
        self.ejecutar_sql(ejecutar=True)
        self.assertEqual(SesionClase.objects.count(), 1)
        self.assertIsNotNone(RegistroImportacionKobo.objects.get().asistencia_id)

    def test_commit_limpia_contexto_y_preserva_marcas_y_personas(self):
        self.ejecutar_sql(ejecutar=True, confirmar=True)
        self.assertFalse(SesionClase.objects.exists())
        self.assertFalse(Asistencia.objects.exists())
        self.assertFalse(Horario.objects.exists())
        self.assertEqual(Estudiante.objects.count(), 2)
        self.assertIsNone(RegistroImportacionKobo.objects.get().asistencia_id)

    def test_reimportacion_opcional_elimina_marcas_vinculadas(self):
        self.ejecutar_sql(ejecutar=True, confirmar=True, reimportar=True)
        self.assertFalse(RegistroImportacionKobo.objects.exists())

    def test_historial_externo_bloquea_reinicio_y_revierte(self):
        self.procesar(_id=124, fecha_sesion="2026-10-21", estado_asistencia="AUSENTE")
        with self.assertRaises(DatabaseError):
            self.ejecutar_sql(ejecutar=True, confirmar=True, reiniciar=True, hasta="2026-10-20")
        self.assertEqual(SesionClase.objects.count(), 2)
        self.assertEqual(Asistencia.objects.count(), 2)
