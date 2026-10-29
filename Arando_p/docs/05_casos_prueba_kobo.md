# Casos de prueba del piloto individual

## Preparación y evidencia

Usar datos ficticios del grupo vinculado al UID de `.env`, matrícula EN_CURSO y
asignación activa con vigencia para todas las fechas elegidas. Elegir fechas
distintas y pasadas o actuales de Colombia. Los ejemplos no requieren que los
demás estudiantes de la base respondan ni se marquen ausentes.

Para rondas desde cero, usar el procedimiento de limpieza de la entrega 04.
Registrar por caso: ID del envío Kobo, ID de sesión, ID de asistencia, resumen de
sincronización, horas de la matrícula, caso de alerta y cantidad de correos.
Los IDs son generados: no se exige que comiencen en 1 ni que sean consecutivos.
Evitar capturas o exportaciones con información personal real.

Los casos positivos se pueden ejecutar desde el formulario. Los negativos con
campos precargados manipulados, concurrencia, errores simulados y estados
administrativos se verifican mediante la suite automatizada o una base de ensayo;
no se necesita editar el formulario real para ejecutarlos.

## Matriz funcional

| ID | Escenario y acción | Resultado esperado |
|---|---|---|
| CP-01 | Sin sesión previa, enviar PRESENTE con fecha y horas válidas. | Una sesión REALIZADA sin horario nuevo; una asistencia y una importación. Cinco horas reconocidas; sin correo de ausencia. |
| CP-02 | Repetir la sincronización del mismo envío. | Cero sesiones/asistencias nuevas y cero correos adicionales. |
| CP-03 | Enviar otro registro con distinto ID pero misma clase, estudiante y estado. | Reutiliza sesión y asistencia; crea solo otra marca de importación. |
| CP-04 | Otra clase del mismo grupo, con fecha o inicio distintos. | Otra sesión; no cambia la anterior. |
| CP-05 | Primera AUSENTE, en una clase distinta. | Cero horas por esa clase; un caso activo TEMPRANA y un correo por esa ausencia. |
| CP-06 | Segunda AUSENTE en otra clase. | Mismo caso activo, nivel AMARILLA y un correo adicional. |
| CP-07 | Tercera y cuarta AUSENTE en clases distintas. | Mismo caso ROJA; un correo por cada ausencia, también por la cuarta. |
| CP-08 | Aprobar una revalidación de una ausencia. | Esa clase reconoce cinco horas, baja el conteo efectivo y se actualiza el caso; conserva el conteo histórico. |
| CP-09 | Cerrar administrativamente el caso y registrar otra ausencia. | Nuevo caso activo; conserva el cerrado y cuenta todo el historial efectivo. |
| CP-10 | Fecha posterior al día local de Colombia. | Rechazo sin crear sesión, asistencia, importación ni correo. |
| CP-11 | Fin igual o anterior al inicio; fecha imposible u hora inválida. | Rechazo sin escrituras. |
| CP-12 | Cambiar un código precargado por otro docente, institución, aula o CLEI. | Rechazo por contradicción con el grupo autorizado, aunque el código exista. |
| CP-13 | Docente sin asignación activa, o fecha fuera de su vigencia. | Rechazo sin sesión nueva. |
| CP-14 | Estudiante sin matrícula EN_CURSO del aula/CLEI y fecha. | Rechazo sin sesión ni asistencia; no marca a otros estudiantes. |
| CP-15 | Formulario no vinculado o desactivado. | Rechazo de envíos nuevos. Los ya procesados siguen siendo idempotentes. |
| CP-16 | La sesión existente tiene otra hora final. | Conflicto; no crea otra sesión ni cambia silenciosamente las horas. |
| CP-17 | La sesión ya está PROGRAMADA y coincide con el envío autorizado. | Confirma REALIZADA; conserva ID y horario institucional. |
| CP-18 | La sesión está CANCELADA o REPROGRAMADA. | Rechazo; conserva el estado. |
| CP-19 | Mismo estudiante y sesión, nuevo envío con estado contrario. | Conflicto; no sobrescribe la asistencia previa. |
| CP-20 | Procesar el mismo envío simultáneamente en dos conexiones PostgreSQL. | Una sesión, una asistencia, una marca por formulario/envío y un solo correo si AUSENTE. |
| CP-21 | Dos estudiantes válidos de un grupo registran la misma clase. | Una sesión y dos asistencias. Escenario automatizado/preparatorio: el piloto visible solo contiene un estudiante. |
| CP-22 | Falla al guardar la importación después de crear la sesión. | Rollback de sesión, asistencia y caso; no se ejecuta el correo. Reintentar luego funciona. |
| CP-23 | Falla SMTP después del commit. | La asistencia y el caso permanecen. Se registra el fallo; hoy no hay cola persistente de reintentos. |
| CP-24 | Formulario original sin vinculación ni hora final, con sesión REALIZADA previa. | Conserva la compatibilidad; no inventa sesiones si faltan datos autorizados. |

La política de fechas no impone todavía un corte por hora de envío para clases
del día actual. Las pruebas de hora verifican coherencia cronológica, no cinco
horas de reloj; una clase de dos horas cronológicas reconoce cinco académicas
cuando corresponde por presencia/revalidación y estado REALIZADA.

## Matriz de limpieza

| ID | Acción | Resultado esperado |
|---|---|---|
| CL-01 | Ejecutar limpieza sin `--ejecutar`. | Solo cantidades, bloqueos y huella; ninguna escritura. |
| CL-02 | Confirmar otra base o una huella incorrecta/desactualizada. | Rechazo sin cambios. |
| CL-03 | Limpiar grupo confirmado, conservando importaciones. | Elimina registros seleccionados; volver a sincronizar sus IDs antiguos no los recrea. |
| CL-04 | Repetir con `--permitir-reimportacion` en vista previa y ejecución. | Los envíos antiguos ligados a lo eliminado quedan disponibles para reprocesar; pueden volver a notificar. |
| CL-05 | Solicitar reinicio de alertas de estudiante con asistencias fuera del alcance. | Bloqueo y rollback completo. |
| CL-06 | Limpiar un rango mientras otro usa el mismo horario. | Conserva ese horario y todas las sesiones fuera del rango. |
| CL-07 | Existen otros grupos del mismo docente. | Los conserva. |
| CL-08 | Limpiar datos ficticios antes de la migración de contexto. | Funciona con esquema desde 0022; luego permite aplicar las migraciones si ya no hay conflictos históricos. |

## Ejecución automatizada

```powershell
.\.venv\Scripts\python.exe manage.py test seguimiento --settings=config.settings_test_postgres --verbosity 1
```

La suite implementa escenarios de los incrementos entregados; la matriz además
incluye verificaciones de aceptación manuales. No representa una certificación
de entrega real de Gmail ni de captura completa desde un dispositivo docente.
La prueba PostgreSQL trabaja sobre una base temporal y correo en memoria.
