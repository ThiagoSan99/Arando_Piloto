from datetime import date, time
from io import StringIO

from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class MigracionContextoSesionTests(TransactionTestCase):
    anterior = [("seguimiento", "0023_formulario_kobo")]
    actual = [("seguimiento", "0029_notificaciones_persistentes")]

    def migrar(self, destino):
        ejecutor = MigrationExecutor(connection)
        ejecutor.migrate(destino)
        return ejecutor.loader.project_state(destino).apps

    def setUp(self):
        self.apps = self.migrar(self.anterior)
        modelo = lambda nombre: self.apps.get_model("seguimiento", nombre)
        proyecto = modelo("Proyecto").objects.create(nombre="Proyecto ficticio")
        departamento = modelo("Departamento").objects.create(nombre="Departamento ficticio")
        zona = modelo("Zona").objects.create(
            proyecto=proyecto, departamento=departamento, nombre="Zona ficticia",
        )
        institucion = modelo("Institucion").objects.create(zona=zona, nombre="Institución ficticia")
        aula = modelo("Aula").objects.create(institucion=institucion, nombre="Aula ficticia")
        clei = modelo("CLEI").objects.create(codigo="III", nombre="CLEI III")
        docente = modelo("Docente").objects.create(
            institucion=institucion, codigo="DOC-FICTICIO", nombres="Docente", apellidos="Ficticio",
        )
        self.horario = modelo("Horario").objects.create(
            aula=aula, clei=clei, docente=docente, dia_semana=1,
            hora_inicio=time(8), hora_fin=time(10),
        )
        self.sesion = modelo("SesionClase").objects.create(
            horario=self.horario, fecha=date(2026, 10, 20),
            hora_inicio=time(8), hora_fin=time(10), estado="REALIZADA",
        )
        estudiante = modelo("Estudiante").objects.create(codigo="EST-FICTICIO", aula=aula, clei=clei)
        self.asistencia = modelo("Asistencia").objects.create(
            estudiante=estudiante, sesion=self.sesion, estado="PRESENTE",
        )

    def tearDown(self):
        try:
            self.migrar(self.actual)
        finally:
            super().tearDown()

    def test_completa_contexto_y_conserva_ids_horario_y_asistencias(self):
        registro = self.apps.get_model("seguimiento", "RegistroImportacionKobo").objects.create(
            formulario_uid="formulario-historico-ficticio", envio_id=123,
            asistencia=self.asistencia, estado="CREADA",
        )
        apps = self.migrar(self.actual)
        sesion = apps.get_model("seguimiento", "SesionClase").objects.get(pk=self.sesion.pk)
        self.assertEqual(sesion.horario_id, self.horario.pk)
        self.assertEqual(sesion.aula_id, self.horario.aula_id)
        self.assertEqual(sesion.clei_id, self.horario.clei_id)
        self.assertEqual(sesion.docente_id, self.horario.docente_id)
        self.assertIsNone(sesion.asignacion_id)
        asistencia = apps.get_model("seguimiento", "Asistencia").objects.get(pk=self.asistencia.pk)
        self.assertEqual(asistencia.sesion_id, self.sesion.pk)
        importacion = apps.get_model("seguimiento", "RegistroImportacionKobo").objects.get(pk=registro.pk)
        self.assertEqual(importacion.asistencia_id, self.asistencia.pk)
        self.assertEqual(importacion.formato, "INDIVIDUAL")
        self.assertEqual(list(importacion.asistencias.values_list("pk", flat=True)), [self.asistencia.pk])

    def test_duplicados_detienen_migracion_sin_fusionar(self):
        Sesion = self.apps.get_model("seguimiento", "SesionClase")
        duplicada = Sesion.objects.create(
            horario=self.horario, fecha=self.sesion.fecha,
            hora_inicio=time(8), hora_fin=time(10), estado="REALIZADA",
        )
        try:
            with self.assertRaisesRegex(RuntimeError, "duplicadas"):
                self.migrar(self.actual)
            self.assertEqual(Sesion.objects.count(), 2)
        finally:
            # Solo datos ficticios de esta prueba, para restaurar el esquema.
            Sesion.objects.filter(pk=duplicada.pk).delete()

    def test_horas_invalidas_detienen_migracion_sin_corregirlas(self):
        Sesion = self.apps.get_model("seguimiento", "SesionClase")
        Sesion.objects.filter(pk=self.sesion.pk).update(hora_fin=time(7))
        try:
            with self.assertRaisesRegex(RuntimeError, "horas inválidas"):
                self.migrar(self.actual)
            self.assertEqual(Sesion.objects.get(pk=self.sesion.pk).hora_fin, time(7))
        finally:
            Sesion.objects.filter(pk=self.sesion.pk).update(hora_fin=time(10))

    def test_limpieza_funciona_antes_de_migrar_contexto(self):
        Aula = self.apps.get_model("seguimiento", "Aula")
        Aula.objects.filter(pk=self.horario.aula_id).update(codigo_kobo="AULA-FICTICIA")
        opciones = dict(docente="DOC-FICTICIO", aula="AULA-FICTICIA", clei="III", incluir_horarios=True)
        salida = StringIO()
        call_command("limpiar_pruebas_kobo", **opciones, stdout=salida)
        huella = next(linea.split(": ", 1)[1] for linea in salida.getvalue().splitlines()
                      if linea.startswith("Huella del plan:"))
        call_command(
            "limpiar_pruebas_kobo", **opciones, ejecutar=True, confirmar_plan=huella,
            confirmar_base=str(connection.settings_dict["NAME"]), stdout=StringIO(),
        )
        self.assertEqual(self.apps.get_model("seguimiento", "SesionClase").objects.count(), 0)
