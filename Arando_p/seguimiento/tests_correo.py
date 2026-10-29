from io import StringIO
from unittest.mock import patch
import smtplib

from django.core.management import call_command, CommandError
from django.test import SimpleTestCase, override_settings


@override_settings(MAILERS={"default": {
    "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
    "OPTIONS": {"host": "smtp.gmail.com", "port": 587, "use_tls": True,
                "username": "prueba@example.com", "password": "clave-ficticia", "timeout": 20},
}})
class DiagnosticoCorreoTests(SimpleTestCase):
    def smtp(self):
        return patch("seguimiento.management.commands.diagnosticar_correo.smtplib.SMTP")

    def test_autentica_sin_enviar_correo_y_sin_mostrar_secretos(self):
        with self.smtp() as smtp:
            smtp.return_value.esmtp_features = {"auth": "LOGIN PLAIN"}
            salida = StringIO()
            call_command("diagnosticar_correo", stdout=salida)
        smtp.return_value.starttls.assert_called_once()
        smtp.return_value.auth.assert_called_once()
        smtp.return_value.sendmail.assert_not_called()
        smtp.return_value.send_message.assert_not_called()
        smtp.return_value.close.assert_called_once()
        self.assertNotIn("clave-ficticia", salida.getvalue())
        self.assertNotIn("prueba@example.com", salida.getvalue())

    def test_muestra_codigo_535_sin_publicar_respuesta_arbitraria(self):
        with self.smtp() as smtp:
            smtp.return_value.esmtp_features = {"auth": "LOGIN PLAIN"}
            smtp.return_value.auth.side_effect = smtplib.SMTPAuthenticationError(535, b"clave-ficticia")
            with self.assertRaises(CommandError) as error:
                call_command("diagnosticar_correo", stdout=StringIO())
        self.assertIn("535", str(error.exception))
        self.assertNotIn("clave-ficticia", str(error.exception))
        smtp.return_value.close.assert_called_once()

    def test_desconexion_se_informa_sin_reintentos(self):
        with self.smtp() as smtp:
            smtp.return_value.esmtp_features = {"auth": "LOGIN"}
            smtp.return_value.auth.side_effect = smtplib.SMTPServerDisconnected("detalle privado")
            with self.assertRaises(CommandError) as error:
                call_command("diagnosticar_correo", stdout=StringIO())
        self.assertIn("autenticación", str(error.exception))
        self.assertNotIn("detalle privado", str(error.exception))
        self.assertEqual(smtp.return_value.auth.call_count, 1)

    @override_settings(MAILERS={"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}})
    def test_no_intenta_conexion_si_el_mailer_no_es_smtp(self):
        with self.smtp() as smtp:
            with self.assertRaises(CommandError):
                call_command("diagnosticar_correo", stdout=StringIO())
        smtp.assert_not_called()
