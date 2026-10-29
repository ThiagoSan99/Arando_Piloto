# Diagnóstico SMTP y regla vigente de notificación

La regla confirmada por el usuario es notificar desde la primera inasistencia.
Se conserva el comportamiento actual; no se cambió a un umbral de dos ausencias.

## Resultado de las comprobaciones

- Django carga la misma contraseña y usuario que figuran en el `.env` actual.
- La clave efectiva tiene 16 caracteres ASCII y no contiene espacios.
- El usuario SMTP y el remitente corresponden a la cuenta del proyecto.
- La conexión, EHLO y STARTTLS funcionan.
- El certificado observado está emitido por Google Trust Services (WE2).
- La autenticación habitual produce `SMTPServerDisconnected`.
- La autenticación de diagnóstico con AUTH LOGIN permite obtener el rechazo
  explícito de Gmail: `535 5.7.8 Username and Password not accepted`.

Esto confirma un rechazo de autenticación con la pareja usuario/clave efectiva.
No confirma por sí solo si la causa es contraseña incorrecta, revocada o generada
para otra cuenta. Cambiar al puerto 465 tampoco resolvió la desconexión en las
pruebas. No se cambió el backend ni se desactivó la verificación TLS.

## Acción en la cuenta de Google

Abrir https://myaccount.google.com/apppasswords y comprobar que la cuenta activa
sea exactamente `arandolaeducacion@gmail.com`. La clave debe ser de aplicación,
no la contraseña normal de acceso a Google. Requiere verificación en dos pasos.
Si se cambió la contraseña principal de Google después de generar la clave de
aplicación, esa clave puede haber sido revocada y debe reemplazarse.

Guardar la clave únicamente en `ARANDO_EMAIL_PASSWORD` del `.env` local. No
publicarla en capturas, registros o mensajes. Abrir un proceso Django nuevo para
verificar la configuración cargada. No hace falta limpiar datos ni importar
otra vez las asistencias para comprobar autenticación.

Referencia oficial: https://support.google.com/mail/answer/185833?hl=es

## Comando sin envío de correo

Desde `Arando_p`:

```powershell
.\.venv\Scripts\python.exe manage.py diagnosticar_correo
```

El comando compara los valores efectivos con `.env` sin mostrarlos, negocia TLS
o SSL según `MAILERS`, prueba AUTH LOGIN una sola vez y cierra la conexión.
No ejecuta envío de mensajes, no modifica asistencias ni reintenta notificaciones
anteriores. Un éxito confirma autenticación, no entrega real en la bandeja de
entrada. Un fallo muestra su fase o código SMTP sin imprimir respuestas que
puedan contener información sensible.

La sincronización ya confirmada conserva sus marcas de importación: repetirla
no reenvía correos fallidos. El reintento persistente de notificaciones sigue
siendo un incremento separado.
