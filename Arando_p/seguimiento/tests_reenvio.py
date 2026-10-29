from concurrent.futures import ThreadPoolExecutor
from datetime import date
from io import StringIO
import os
import smtplib
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase

from . import tests_kobo
from .correo_persistente import enviar_notificacion, preparar_notificaciones
from .models import (
    Asistencia, CasoAlerta, IntentoNotificacionAusencia, NotificacionAusencia,
    RevalidacionAsistencia, SesionClase,
)
from .services import actualizar_caso_alerta, procesar_respuesta_kobo


DESTINOS = {"ARANDO_ALERT_EMAIL": "primero@example.com,segundo@example.com"}


def preparar(cls):
    tests_kobo.ImportacionContextoKoboTests.setUpTestData.__func__(cls)
    registro = tests_kobo.ImportacionContextoKoboTests.registro(cls, estado_asistencia="AUSENTE")
    with patch.dict(os.environ, DESTINOS), patch("seguimiento.services.notificar_caso_alerta_segura"):
        resultado = procesar_respuesta_kobo(registro, formulario_uid=cls.UID)
    cls.ausencia_id = resultado["asistencia_id"]
    cls.caso = CasoAlerta.objects.get(estudiante=cls.estudiante)


class ReenvioControladoTests(TestCase):
    UID = "formulario-correo-ficticio"

    @classmethod
    def setUpTestData(cls):
        preparar(cls)

    def setUp(self):
        parche = patch.dict(os.environ, DESTINOS)
        parche.start()
        self.addCleanup(parche.stop)
        self.notificacion = NotificacionAusencia.objects.order_by("pk").first()

    def transporte(self):
        return patch("seguimiento.correo_persistente.mail.mailers.create_connection")

    def historica(self):
        sesion = SesionClase.objects.create(
            horario=self.sesion.horario, fecha=date(2026, 10, 21), hora_inicio="08:00", hora_fin="10:00", estado="REALIZADA",
        )
        asistencia = Asistencia.objects.create(
            sesion=sesion, estudiante=self.estudiante, matricula=self.matricula, estado="AUSENTE",
        )
        actualizar_caso_alerta(self.estudiante)
        return asistencia

    def comando(self, asistencia_id, **opciones):
        salida = StringIO()
        call_command("reenviar_notificaciones", "--asistencia-id", str(asistencia_id), stdout=salida, **opciones)
        huella = next(linea.split(": ", 1)[1] for linea in salida.getvalue().splitlines()
                      if linea.startswith("Huella del plan:"))
        return huella

    def test_se_registra_desde_primera_ausencia_y_por_destinatario(self):
        self.assertEqual(self.caso.nivel_actual, "TEMPRANA")
        self.assertEqual(NotificacionAusencia.objects.count(), 2)
        self.assertEqual(set(NotificacionAusencia.objects.values_list("estado", flat=True)), {"PENDIENTE"})
        preparar_notificaciones(self.caso.pk, self.ausencia_id)
        self.assertEqual(NotificacionAusencia.objects.count(), 2)

    def test_envio_exitoso_y_repeticion_no_duplican(self):
        with self.transporte() as fabrica:
            fabrica.return_value.send_messages.return_value = 1
            self.assertEqual(enviar_notificacion(self.notificacion.pk), "ENVIADA")
            self.assertEqual(enviar_notificacion(self.notificacion.pk), "ENVIADA")
        self.assertEqual(fabrica.return_value.send_messages.call_count, 1)
        self.notificacion.refresh_from_db()
        self.assertEqual(self.notificacion.intentos, 1)
        self.assertIsNotNone(self.notificacion.fecha_envio)
        self.assertEqual(self.notificacion.historial_intentos.get().estado, "ENVIADA")

    def test_535_falla_antes_del_envio_y_permite_reintento(self):
        with self.transporte() as fabrica:
            fabrica.return_value.open.side_effect = smtplib.SMTPAuthenticationError(535, b"dato privado")
            self.assertEqual(enviar_notificacion(self.notificacion.pk), "FALLIDA")
            fabrica.return_value.send_messages.assert_not_called()
            fabrica.return_value.open.side_effect = None
            fabrica.return_value.send_messages.return_value = 1
            self.assertEqual(enviar_notificacion(self.notificacion.pk), "ENVIADA")
        self.notificacion.refresh_from_db()
        self.assertEqual(self.notificacion.intentos, 2)
        self.assertEqual(self.notificacion.historial_intentos.order_by("numero").first().codigo_smtp, 535)
        self.assertNotIn("dato privado", self.notificacion.historial_intentos.first().tipo_error)

    def test_desconexion_durante_data_es_incierta_y_no_se_reintenta(self):
        with self.transporte() as fabrica:
            fabrica.return_value.send_messages.side_effect = smtplib.SMTPServerDisconnected("detalle privado")
            self.assertEqual(enviar_notificacion(self.notificacion.pk), "INCIERTA")
            self.assertEqual(enviar_notificacion(self.notificacion.pk), "INCIERTA")
        self.assertEqual(fabrica.return_value.send_messages.call_count, 1)
        self.assertEqual(IntentoNotificacionAusencia.objects.count(), 1)

    def test_rechazo_explicito_data_es_fallido(self):
        with self.transporte() as fabrica:
            fabrica.return_value.send_messages.side_effect = smtplib.SMTPDataError(550, b"rechazo")
            self.assertEqual(enviar_notificacion(self.notificacion.pk), "FALLIDA")

    def test_fallo_de_quit_no_borra_aceptacion_smtp(self):
        with self.transporte() as fabrica:
            fabrica.return_value.send_messages.return_value = 1
            fabrica.return_value.close.side_effect = OSError("cierre")
            self.assertEqual(enviar_notificacion(self.notificacion.pk), "ENVIADA")

    def test_caso_cerrado_no_se_notifica(self):
        CasoAlerta.objects.filter(pk=self.caso.pk).update(estado="CERRADA")
        with self.transporte() as fabrica:
            self.assertEqual(enviar_notificacion(self.notificacion.pk), "OMITIDA")
        fabrica.assert_not_called()

    def test_ausencia_revalidada_no_se_notifica(self):
        usuario = get_user_model().objects.create_user(username="responsable-correo-ficticio")
        RevalidacionAsistencia.objects.create(
            asistencia_id=self.ausencia_id, registrado_por=usuario, decision="APROBADA",
            tipo_autorizador="COORDINADOR", autorizado_por="Responsable ficticio",
            motivo="Prueba", fecha_decision=date(2026, 10, 21),
        )
        with self.transporte() as fabrica:
            self.assertEqual(enviar_notificacion(self.notificacion.pk), "OMITIDA")
        fabrica.assert_not_called()

    def test_asistencia_retirada_no_se_notifica(self):
        NotificacionAusencia.objects.filter(pk=self.notificacion.pk).update(asistencia=None)
        with self.transporte() as fabrica:
            self.assertEqual(enviar_notificacion(self.notificacion.pk), "OMITIDA")
        fabrica.assert_not_called()

    def test_operacion_enviando_nunca_se_reclama_automaticamente(self):
        NotificacionAusencia.objects.filter(pk=self.notificacion.pk).update(estado="ENVIANDO")
        with self.transporte() as fabrica:
            self.assertEqual(enviar_notificacion(self.notificacion.pk), "ENVIANDO")
        fabrica.assert_not_called()

    def test_vista_previa_historica_no_crea_registros_ni_envia(self):
        asistencia = self.historica()
        with self.transporte() as fabrica:
            self.comando(asistencia.pk)
        self.assertEqual(NotificacionAusencia.objects.count(), 2)
        fabrica.assert_not_called()

    def test_historico_requiere_confirmacion_y_huella(self):
        asistencia = self.historica()
        huella = self.comando(asistencia.pk)
        with self.assertRaises(CommandError):
            self.comando(asistencia.pk, ejecutar=True, confirmar_plan="incorrecta", confirmar_fallos_historicos=True)
        with self.assertRaises(CommandError):
            self.comando(asistencia.pk, ejecutar=True, confirmar_plan=huella)

    def test_recuperacion_historica_y_segunda_ejecucion_son_idempotentes(self):
        asistencia = self.historica()
        with self.transporte() as fabrica:
            fabrica.return_value.send_messages.return_value = 1
            for _ in range(2):
                huella = self.comando(asistencia.pk)
                self.comando(asistencia.pk, ejecutar=True, confirmar_plan=huella, confirmar_fallos_historicos=True)
        self.assertEqual(fabrica.return_value.send_messages.call_count, 2)
        recuperados = NotificacionAusencia.objects.filter(asistencia_referencia=asistencia.pk)
        self.assertEqual(recuperados.count(), 2)
        self.assertEqual(set(recuperados.values_list("estado", flat=True)), {"ENVIADA"})
        self.assertEqual(Asistencia.objects.count(), 2)

    def test_destinatario_enviado_no_se_repite_si_otro_fallo(self):
        registros = list(NotificacionAusencia.objects.order_by("pk"))
        with self.transporte() as fabrica:
            fabrica.return_value.send_messages.return_value = 1
            enviar_notificacion(registros[0].pk)
            fabrica.return_value.open.side_effect = smtplib.SMTPAuthenticationError(535, b"rechazo")
            enviar_notificacion(registros[1].pk)
            fabrica.return_value.open.side_effect = None
            huella = self.comando(self.ausencia_id)
            self.comando(self.ausencia_id, ejecutar=True, confirmar_plan=huella)
        self.assertEqual(fabrica.return_value.send_messages.call_count, 2)
        self.assertEqual(NotificacionAusencia.objects.filter(estado="ENVIADA").count(), 2)

    def test_sin_destinatarios_se_registra_bloqueo_sin_revertir_asistencia(self):
        registro = tests_kobo.ImportacionContextoKoboTests.registro(self, _id=124, fecha_sesion="2026-10-21", estado_asistencia="AUSENTE")
        with patch.dict(os.environ, {"ARANDO_ALERT_EMAIL": ""}):
            resultado = procesar_respuesta_kobo(registro, formulario_uid=self.UID)
        self.assertTrue(resultado["asistencia_creada"])
        self.assertEqual(NotificacionAusencia.objects.filter(estado="BLOQUEADA").count(), 1)


@skipUnless(connection.vendor == "postgresql", "Requiere PostgreSQL.")
class ConcurrenciaCorreoTests(TransactionTestCase):
    UID = "formulario-correo-concurrente"

    def setUp(self):
        preparar(type(self))

    def test_dos_operadores_no_envian_dos_veces(self):
        pk = NotificacionAusencia.objects.order_by("pk").first().pk
        barrera = Barrier(2)

        def ejecutar():
            close_old_connections()
            try:
                barrera.wait(timeout=10)
                return enviar_notificacion(pk)
            finally:
                connection.close()

        with patch("seguimiento.correo_persistente.mail.mailers.create_connection") as fabrica:
            fabrica.return_value.send_messages.return_value = 1
            with ThreadPoolExecutor(max_workers=2) as pool:
                futuros = [pool.submit(ejecutar) for _ in range(2)]
                [futuro.result(timeout=30) for futuro in futuros]
        self.assertEqual(fabrica.return_value.send_messages.call_count, 1)
        self.assertEqual(IntentoNotificacionAusencia.objects.count(), 1)
