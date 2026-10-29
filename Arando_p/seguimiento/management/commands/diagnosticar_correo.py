"""Comprueba TLS y AUTH LOGIN; nunca ejecuta MAIL FROM, RCPT TO ni DATA."""
import smtplib
import ssl

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from dotenv import dotenv_values


class Command(BaseCommand):
    help = "Comprueba la configuración y autenticación SMTP sin enviar correos ni mostrar credenciales."

    def handle(self, *args, **options):
        configuracion = settings.MAILERS.get("default", {})
        if configuracion.get("BACKEND") != "django.core.mail.backends.smtp.EmailBackend":
            raise CommandError("El mailer predeterminado no utiliza SMTP.")
        smtp_options = configuracion.get("OPTIONS", {})
        usuario = smtp_options.get("username", "")
        clave = smtp_options.get("password", "")
        if not usuario or not clave:
            raise CommandError("Falta usuario o contraseña SMTP en la configuración efectiva.")
        tls = smtp_options.get("use_tls", False)
        seguro = smtp_options.get("use_ssl", False)
        if tls == seguro:
            raise CommandError("Configura exactamente una opción segura: TLS o SSL.")

        archivo = dotenv_values(settings.BASE_DIR / ".env")
        for variable, valor in (("ARANDO_EMAIL_USER", usuario), ("ARANDO_EMAIL_PASSWORD", clave)):
            coincide = archivo.get(variable) == valor
            self.stdout.write(f"{variable} coincide con .env: {'sí' if coincide else 'no'}")
        if any(caracter.isspace() for caracter in clave):
            self.stdout.write("La clave efectiva contiene espacios o saltos de línea.")

        conexion = None
        fase = "conexión"
        try:
            host = smtp_options.get("host", "smtp.gmail.com")
            puerto = smtp_options.get("port", 465 if seguro else 587)
            timeout = smtp_options.get("timeout", 20)
            if seguro:
                conexion = smtplib.SMTP_SSL(host, puerto, timeout=timeout, context=ssl.create_default_context())
            else:
                conexion = smtplib.SMTP(host, puerto, timeout=timeout)
            conexion.ehlo()
            if tls:
                fase = "STARTTLS"
                conexion.starttls(context=ssl.create_default_context())
                conexion.ehlo()
            self.stdout.write("Conexión segura establecida.")
            fase = "autenticación"
            if "LOGIN" not in conexion.esmtp_features.get("auth", "").upper().split():
                raise CommandError("El servidor no anuncia AUTH LOGIN para este diagnóstico.")
            # LOGIN permite obtener el rechazo explícito que PLAIN está ocultando
            # con una desconexión en el entorno del piloto. No cambia el backend.
            conexion.user = usuario
            conexion.password = clave
            conexion.auth("LOGIN", conexion.auth_login, initial_response_ok=False)
        except smtplib.SMTPAuthenticationError as error:
            raise CommandError(
                f"SMTP {error.smtp_code}: autenticación rechazada. Verifica la cuenta y su contraseña de aplicación. "
                "No se envió ningún correo."
            ) from None
        except (OSError, smtplib.SMTPException) as error:
            raise CommandError(
                f"Fallo en {fase}: {type(error).__name__}. No se envió ningún correo."
            ) from None
        finally:
            if conexion is not None:
                conexion.close()
        self.stdout.write(self.style.SUCCESS("Autenticación SMTP correcta. No se envió ningún correo."))
