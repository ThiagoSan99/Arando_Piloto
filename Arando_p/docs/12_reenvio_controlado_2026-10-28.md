# Reenvío controlado y registro persistente — 28 de octubre de 2026

## Resultado operativo

Se recuperaron los cuatro avisos con fallo SMTP conocido en el log suministrado.
El plan se limitó a las asistencias 13, 16, 17 y 18. Se comprobaron ausencia en
sesión REALIZADA, caso activo del estudiante y ausencia de revalidación aprobada.
Cada aviso tenía un destinatario configurado.

| Notificación | Asistencia | Caso | Estado | Intentos | Recepción |
|---:|---:|---:|---|---:|---|
| 1 | 13 | 2 | ENVIADA | 1 | Confirmada por el usuario |
| 2 | 16 | 3 | ENVIADA | 1 | Confirmada por el usuario |
| 3 | 17 | 4 | ENVIADA | 1 | Confirmada por el usuario |
| 4 | 18 | 4 | ENVIADA | 1 | Confirmada por el usuario |

Una segunda ejecución conservó los cuatro estados e intentos. Se bloqueó el
transporte durante esa comprobación y se verificó que no se intentara abrir otra
conexión SMTP. Las asistencias, sesiones e importaciones permanecieron iguales.
No se reimportaron respuestas de Kobo ni se reenviaron otras ausencias sin
evidencia de fallo previo.

La regla vigente sigue siendo notificar desde la primera inasistencia. El riesgo
continúa TEMPRANA con una, AMARILLA con dos y ROJA desde tres ausencias efectivas.

## Cambios implementados

- Migración `0029_notificaciones_persistentes`: registro de notificación por
  asistencia y destinatario e historial de intentos. No se rellenan ni reenvían
  automáticamente todos los correos históricos, cuya entrega anterior se desconoce.
- `correo_persistente.py`: preparación transaccional, snapshot de contenido y
  destinatario, reclamación con bloqueo e intentos SMTP fuera de la transacción
  académica. Una limpieza conserva la referencia y auditoría del correo.
- `kobo_importador.py` y `services.py`: la intención se guarda junto a la ausencia;
  el primer intento se ejecuta después del commit. SMTP no revierte asistencias.
- `reenviar_notificaciones`: vista previa, IDs explícitos, huella y confirmación
  de fallos históricos. También permite reintentar pendientes ya registrados.
- `sincronizar_kobo`: separa errores de importación de los resultados del correo.
  Un fallo SMTP deja un estado consultable y hace visible el resultado en consola.
- Administrador Django: consulta de notificaciones e intentos, sin edición de
  estados ni eliminación desde esa pantalla.

## Estados y garantías

| Estado | Significado y acción |
|---|---|
| PENDIENTE | Intención guardada; se puede intentar enviar. |
| ENVIANDO | Un proceso reclamó el aviso. No se reclama automáticamente otra vez. |
| ENVIADA | El backend SMTP confirmó aceptación; se conserva fecha y Message-ID estable. No se reenvía. |
| FALLIDA | Fallo antes de transmitir o rechazo explícito. Permite reintento controlado. |
| INCIERTA | Fallo durante transmisión sin aceptación/rechazo confirmado. Requiere revisión manual. |
| OMITIDA | Ausencia retirada/revalidada, sesión no realizada o caso cerrado. No se envía. |
| BLOQUEADA | Faltan destinatarios válidos. Corregir configuración antes de preparar el envío. |

Cada destinatario tiene un registro independiente: si uno fue aceptado y otro
falló, solo se reintenta el segundo. La restricción única por asistencia y
destinatario evita duplicar la intención. Los operadores concurrentes reclaman
el registro con bloqueo antes de la red.

SMTP no permite garantizar entrega exactamente una vez frente a una caída
después de aceptar DATA y antes de confirmar el resultado al proceso. Por eso
INCIERTA y ENVIANDO no se reenvían automáticamente: se revisan antes de resolver
si el mensaje fue recibido. ENVIADA acredita aceptación SMTP; para este control
también se obtuvo confirmación del usuario de que llegaron los cuatro mensajes.

## Uso para futuros fallos

Vista previa de los registros persistentes pendientes o fallidos:

```powershell
python manage.py reenviar_notificaciones --pendientes
```

Después de revisar el alcance, copiar la huella y ejecutar:

```powershell
python manage.py reenviar_notificaciones --pendientes --ejecutar --confirmar-plan HUELLA_MOSTRADA
```

Sincronizar Kobo de nuevo sigue omitiendo los envíos ya procesados. El comando
anterior reintenta sus correos sin tocar las asistencias. No se creó una tarea
programada; el primer intento es automático después de importar una ausencia y
los reintentos se solicitan mediante el comando.

Para un histórico anterior al registro persistente, indicar solo IDs con fallo
conocido. Ejemplo de la vista previa utilizada:

```powershell
python manage.py reenviar_notificaciones --asistencia-id 13 --asistencia-id 16 --asistencia-id 17 --asistencia-id 18
```

La ejecución histórica exige además `--confirmar-fallos-historicos`; no usarlo
para ausencias cuya entrega previa sea desconocida. Ahora esas cuatro ya constan
ENVIADA y repetir la operación no produce nuevos mensajes.

## Validación y control del día

La suite final de PostgreSQL encontró 125 pruebas: 120 aprobadas, 5 omitidas por
el archivo SQL ausente y ninguna fallida. Incluye concurrencia de correo, rechazo
535, desconexión durante envío, reintento por destinatario, vista previa sin
escrituras, histórico con confirmación, idempotencia, ausencia revalidada y caso
cerrado, además de las regresiones del importador individual y grupal.

```powershell
python manage.py test seguimiento --settings=config.settings_test_postgres --verbosity 1
```

El Excel del día contiene 18 historias de usuario, 32 casos de aceptación y la
evidencia de las cuatro notificaciones. Distingue el resultado de la suite completa
del subconjunto de casos de aceptación documentados y mantiene las direcciones
de correo anonimizadas. La recepción en bandeja se confirmó por el usuario.
