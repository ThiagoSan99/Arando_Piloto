from datetime import date
from io import StringIO
from unittest import skipUnless
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.management import call_command, CommandError
from django.db import connection
from django.test import TestCase, TransactionTestCase

from . import tests_kobo, tests_limpieza, tests_sesiones
from .models import (
    AsignacionDocenteCLEI, Asistencia, Aula, CampoAsistenciaKobo, DetalleImportacionKobo, Estudiante,
    FormatoRegistroKobo, FormularioKobo, MatriculaCLEI, RegistroImportacionKobo, SesionClase,
)
from .services import calcular_horas_presenciales, procesar_respuesta_kobo, sincronizar_asistencias_kobo


def preparar_grupo(cls):
    tests_kobo.ImportacionContextoKoboTests.setUpTestData.__func__(cls)
    cls.formulario.formato = FormatoRegistroKobo.GRUPAL_V1
    cls.formulario.save()
    MatriculaCLEI.objects.create(
        estudiante=cls.otro_estudiante, aula=cls.aula, clei=cls.clei, fecha_inicio=date(2026, 10, 1),
    )
    CampoAsistenciaKobo.objects.create(formulario=cls.formulario, campo="asistencia_uno", estudiante=cls.estudiante)
    CampoAsistenciaKobo.objects.create(formulario=cls.formulario, campo="asistencia_dos", estudiante=cls.otro_estudiante)


def registro_grupal(self, **cambios):
    registro = tests_kobo.ImportacionContextoKoboTests.registro(self, fecha_sesion="2026-10-21")
    registro.pop("codigo_estudiante")
    registro.pop("estado_asistencia")
    registro.update(formato_registro="GRUPAL_V1", asistencia_uno="PRESENTE", asistencia_dos="AUSENTE")
    registro.update(cambios)
    return registro


class RecepcionGrupalTests(TestCase):
    UID = "formulario-grupal-ficticio"
    registro = registro_grupal
    comando = tests_limpieza.LimpiezaPruebasKoboTests.comando
    ejecutar = tests_limpieza.LimpiezaPruebasKoboTests.ejecutar

    @classmethod
    def setUpTestData(cls):
        preparar_grupo(cls)

    def procesar(self, **cambios):
        return procesar_respuesta_kobo(self.registro(**cambios), formulario_uid=self.UID)

    def test_un_envio_crea_una_sesion_y_dos_asistencias_trazables(self):
        with patch("seguimiento.services.notificar_caso_alerta_segura") as notificar:
            with self.captureOnCommitCallbacks(execute=True):
                resultado = self.procesar()
        self.assertEqual(resultado["asistencias_creadas"], 2)
        self.assertEqual(len(resultado["asistencia_ids"]), 2)
        self.assertIsNone(resultado["asistencia_id"])
        importacion = RegistroImportacionKobo.objects.get()
        self.assertEqual(importacion.formato, "GRUPAL_V1")
        self.assertEqual(importacion.asistencias.count(), 2)
        self.assertEqual(importacion.asistencias.values("sesion_id").distinct().count(), 1)
        self.assertEqual(set(importacion.detalles.values_list("campo_formulario", flat=True)),
                         {"asistencia_uno", "asistencia_dos"})
        self.assertEqual(SesionClase.objects.filter(fecha="2026-10-21").count(), 1)
        self.assertEqual(calcular_horas_presenciales(self.matricula)["horas_cumplidas"], 5)
        notificar.assert_called_once()

    def test_reimportacion_y_otro_envio_equivalente_no_notifican_otra_vez(self):
        with patch("seguimiento.services.notificar_caso_alerta_segura") as notificar:
            with self.captureOnCommitCallbacks(execute=True):
                self.procesar()
                repetida = self.procesar()
                equivalente = self.procesar(_id=124)
        self.assertFalse(repetida["importacion_creada"])
        self.assertEqual(len(repetida["asistencia_ids"]), 2)
        self.assertEqual(equivalente["asistencias_creadas"], 0)
        self.assertEqual(equivalente["asistencias_existentes"], 2)
        self.assertEqual(RegistroImportacionKobo.objects.count(), 2)
        self.assertEqual(Asistencia.objects.count(), 2)
        notificar.assert_called_once()

    def test_un_estudiante_sin_matricula_revierte_el_envio_completo(self):
        MatriculaCLEI.objects.filter(estudiante=self.otro_estudiante).delete()
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            with self.assertRaises(ValidationError):
                self.procesar()
        self.assertEqual(callbacks, [])
        self.assertFalse(Asistencia.objects.exists())
        self.assertFalse(RegistroImportacionKobo.objects.exists())
        self.assertFalse(SesionClase.objects.filter(fecha="2026-10-21").exists())

    def test_rechaza_campos_faltantes_extra_vacios_y_estados_invalidos(self):
        for cambios in ({"asistencia_dos": None}, {"asistencia_dos": ""},
                        {"asistencia_dos": "DESCONOCIDO"}, {"asistencia_extra": "PRESENTE"},
                        {"formato_registro": "INDIVIDUAL"}, {"codigo_estudiante": "EST-TEST"}):
            with self.subTest(cambios=cambios), self.assertRaises(ValidationError):
                self.procesar(**cambios)
        registro = self.registro()
        registro.pop("asistencia_dos")
        with self.assertRaises(ValidationError):
            procesar_respuesta_kobo(registro, formulario_uid=self.UID)
        self.assertFalse(Asistencia.objects.exists())

    def test_no_acepta_lista_grupal_en_un_uid_individual(self):
        FormularioKobo.objects.filter(pk=self.formulario.pk).update(formato="INDIVIDUAL")
        with self.assertRaises(ValidationError):
            self.procesar()

    def test_grupal_no_acepta_payload_individual(self):
        registro = tests_kobo.ImportacionContextoKoboTests.registro(self)
        with self.assertRaises(ValidationError):
            procesar_respuesta_kobo(registro, formulario_uid=self.UID)

    def test_conflicto_en_un_estudiante_no_modifica_a_los_demas(self):
        self.procesar()
        with self.assertRaises(ValidationError):
            self.procesar(_id=124, asistencia_dos="PRESENTE")
        self.assertEqual(RegistroImportacionKobo.objects.count(), 1)
        self.assertEqual(Asistencia.objects.filter(estado="AUSENTE").count(), 1)

    def test_error_en_ultimo_detalle_revierte_todo_y_sus_callbacks(self):
        guardar = DetalleImportacionKobo.save
        contador = []

        def fallar(detalle, *args, **kwargs):
            contador.append(1)
            if len(contador) == 2:
                raise RuntimeError("Fallo simulado")
            return guardar(detalle, *args, **kwargs)

        with patch.object(DetalleImportacionKobo, "save", new=fallar):
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                with self.assertRaises(RuntimeError):
                    self.procesar(asistencia_uno="AUSENTE")
        self.assertEqual(callbacks, [])
        self.assertFalse(Asistencia.objects.exists())
        self.assertFalse(RegistroImportacionKobo.objects.exists())
        self.assertFalse(DetalleImportacionKobo.objects.exists())
        self.assertTrue(self.procesar()["importacion_creada"])

    def test_no_inventa_ausencias_de_estudiantes_fuera_de_la_lista(self):
        tercero = Estudiante.objects.create(codigo="EST-TERCERO", aula=self.aula, clei=self.clei)
        MatriculaCLEI.objects.create(estudiante=tercero, aula=self.aula, clei=self.clei,
                                     fecha_inicio=date(2026, 10, 1))
        self.procesar()
        self.assertFalse(tercero.asistencias.exists())

    def test_resumen_cuenta_asistencias_y_no_solo_envios(self):
        with patch("seguimiento.services.KoboClient") as cliente:
            cliente.return_value.FORM_UID = self.UID
            cliente.return_value.iterar_respuestas.return_value = [self.registro(), self.registro()]
            resumen = sincronizar_asistencias_kobo()
        self.assertEqual(resumen["asistencias_creadas"], 2)
        self.assertEqual(resumen["envios_ya_procesados"], 1)

    def test_dos_formularios_con_tres_y_dos_estudiantes_crean_cinco_asistencias(self):
        tercero = Estudiante.objects.create(codigo="TERCERO-FICTICIO", aula=self.aula, clei=self.clei)
        MatriculaCLEI.objects.create(estudiante=tercero, aula=self.aula, clei=self.clei,
                                     fecha_inicio=date(2026, 10, 1))
        CampoAsistenciaKobo.objects.create(formulario=self.formulario, campo="asistencia_tres", estudiante=tercero)
        aula2 = Aula.objects.create(institucion=self.aula.institucion, codigo_kobo="AULA-G2", nombre="Grupo ficticio 2")
        AsignacionDocenteCLEI.objects.create(docente=self.docente, aula=aula2, clei=self.clei,
                                            fecha_inicio=date(2026, 10, 1))
        segundo = FormularioKobo.objects.create(formulario_uid="segundo-grupal-ficticio",
                                                docente=self.docente, aula=aula2, clei=self.clei, formato="GRUPAL_V1")
        for numero in (1, 2):
            estudiante = Estudiante.objects.create(codigo=f"G2-FICTICIO-{numero}", aula=aula2, clei=self.clei)
            MatriculaCLEI.objects.create(estudiante=estudiante, aula=aula2, clei=self.clei,
                                         fecha_inicio=date(2026, 10, 1))
            CampoAsistenciaKobo.objects.create(formulario=segundo, campo=f"asistencia_g2_{numero}", estudiante=estudiante)
        registro2 = {clave: valor for clave, valor in self.registro().items() if not clave.startswith("asistencia_")}
        registro2.update(codigo_aula="AULA-G2", asistencia_g2_1="PRESENTE", asistencia_g2_2="AUSENTE")
        with patch("seguimiento.services.notificar_caso_alerta_segura") as notificar:
            with self.captureOnCommitCallbacks(execute=True):
                self.procesar(asistencia_tres="PRESENTE")
                procesar_respuesta_kobo(registro2, formulario_uid=segundo.formulario_uid)
        self.assertEqual(Asistencia.objects.count(), 5)
        self.assertEqual(RegistroImportacionKobo.objects.count(), 2)
        self.assertEqual(SesionClase.objects.filter(fecha="2026-10-21").count(), 2)
        self.assertEqual(notificar.call_count, 2)

    def test_limpieza_conserva_marca_del_envio_grupal(self):
        self.procesar()
        self.ejecutar(reiniciar_alertas=True)
        self.assertFalse(Asistencia.objects.exists())
        self.assertFalse(DetalleImportacionKobo.objects.exists())
        self.assertEqual(RegistroImportacionKobo.objects.count(), 1)
        self.assertFalse(self.procesar()["importacion_creada"])

    def test_limpieza_con_reimportacion_borra_marca_y_permite_repetir(self):
        self.procesar()
        self.ejecutar(reiniciar_alertas=True, permitir_reimportacion=True)
        self.assertFalse(RegistroImportacionKobo.objects.exists())
        self.assertEqual(self.procesar()["asistencias_creadas"], 2)

    def test_mapeo_no_permite_reasignar_campo_o_estudiante_de_otro_grupo(self):
        with self.assertRaises(CommandError):
            call_command(
                "configurar_formulario_kobo", formulario_uid=self.UID, docente="DOC-TEST",
                aula="AULA-TEST", clei="III", formato="GRUPAL_V1",
                campo_asistencia=["asistencia_uno=EST-TEST-OTRO"], stdout=StringIO(),
            )
        self.assertEqual(self.formulario.campos_asistencia.get(campo="asistencia_uno").estudiante_id,
                         self.estudiante.pk)

    def test_comando_configura_mapeo_idempotente_y_activa(self):
        FormularioKobo.objects.filter(pk=self.formulario.pk).update(activo=False)
        for _ in range(2):
            call_command(
                "configurar_formulario_kobo", formulario_uid=self.UID, docente="DOC-TEST",
                aula="AULA-TEST", clei="III", formato="GRUPAL_V1", activar=True,
                campo_asistencia=["asistencia_uno=EST-TEST", "asistencia_dos=EST-TEST-OTRO"], stdout=StringIO(),
            )
        self.formulario.refresh_from_db()
        self.assertTrue(self.formulario.activo)
        self.assertEqual(self.formulario.campos_asistencia.count(), 2)


@skipUnless(connection.vendor == "postgresql", "Requiere PostgreSQL y conexiones independientes.")
class ConcurrenciaGrupalTests(TransactionTestCase):
    UID = "formulario-grupal-ficticio"
    registro = registro_grupal
    ejecutar_en_paralelo = tests_sesiones.ConcurrenciaSesionesTests.ejecutar_en_paralelo

    def setUp(self):
        preparar_grupo(type(self))

    def test_envio_grupal_simultaneo_se_confirma_una_vez(self):
        registro = self.registro()
        with patch("seguimiento.services.notificar_caso_alerta_segura") as notificar:
            resultados = self.ejecutar_en_paralelo([(registro, self.UID), (registro, self.UID)])
        self.assertEqual(sum(resultado["asistencias_creadas"] for resultado in resultados), 2)
        self.assertEqual(Asistencia.objects.count(), 2)
        self.assertEqual(DetalleImportacionKobo.objects.count(), 2)
        self.assertEqual(RegistroImportacionKobo.objects.count(), 1)
        notificar.assert_called_once()

    def test_dos_formularios_grupales_comparten_sesion_y_asistencias(self):
        otro = FormularioKobo.objects.create(
            formulario_uid="otro-grupal", docente=self.docente, aula=self.aula, clei=self.clei, formato="GRUPAL_V1",
        )
        for mapa in self.formulario.campos_asistencia.all():
            CampoAsistenciaKobo.objects.create(formulario=otro, campo=mapa.campo, estudiante=mapa.estudiante)
        with patch("seguimiento.services.notificar_caso_alerta_segura") as notificar:
            self.ejecutar_en_paralelo([(self.registro(), self.UID), (self.registro(), otro.formulario_uid)])
        self.assertEqual(Asistencia.objects.count(), 2)
        self.assertEqual(SesionClase.objects.filter(fecha="2026-10-21").count(), 1)
        self.assertEqual(DetalleImportacionKobo.objects.count(), 4)
        self.assertEqual(RegistroImportacionKobo.objects.count(), 2)
        notificar.assert_called_once()
