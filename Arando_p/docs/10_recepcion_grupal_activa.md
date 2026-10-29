# Recepción grupal activa — 2026-10-28

## Estado del piloto

Se implementó el formato `GRUPAL_V1`, se aplicaron las migraciones 0027 y 0028
y se activaron los dos formularios después de comprobar sus metadatos en Kobo,
asignación docente y matrículas locales:

| UID | Docente / aula / CLEI | Estudiantes por envío |
|---|---|---:|
| a7Sco3Aw7XWTnCNHhF8pcf | DOC-DEMO-001 / DEMO-NAR-Z1-I1-A1 / III | 3 |
| aiDQR8Dr7BERTRX6fgCvFL | DOC-DEMO-003 / DEMO-CAU-Z1-I1-A1 / III | 2 |

Esta entrega no importó respuestas de Kobo ni envió correos reales. Conservó las
cantidades de sesiones, asistencias e importaciones existentes. No modificó
personas, asignaciones ni matrículas. El estado inactivo de la entrega 09 queda
reemplazado por esta activación.

## Flujo y contrato

Cada envío contiene una cabecera de docente, institución, aula, CLEI, fecha,
inicio y fin, el marcador `formato_registro=GRUPAL_V1` y todos los campos de
asistencia configurados para ese formulario. No incluye los campos individuales
`codigo_estudiante` y `estado_asistencia`.

El mapeo es explícito y se almacena en `CampoAsistenciaKobo`; no se deducen
códigos de estudiantes a partir de nombres de preguntas ni de su posición:

| Formulario | Campo | Código de estudiante |
|---|---|---|
| Primero | asistencia_est_demo_001 | EST-DEMO-001 |
| Primero | asistencia_est_demo_002 | EST-DEMO-002 |
| Primero | asistencia_est_demo_003 | EST-DEMO-003 |
| Segundo | asistencia_est_demo_012 | EST-DEMO-012 |
| Segundo | asistencia_est_demo_013 | EST-DEMO-013 |

Las opciones admitidas son PRESENTE y AUSENTE. Se rechazan campos de asistencia
faltantes o desconocidos, valores vacíos, estados inválidos y mezcla de contratos.
Se comprueba la matrícula de cada estudiante para la fecha y grupo. Estudiantes
que estén en la base pero no en el mapeo no reciben ausencias implícitas.

El procesamiento bloquea formulario, mapeos, asignación y estudiantes en orden
estable; valida de nuevo las vigencias y crea o reutiliza una única sesión.
Guarda todas las asistencias y una importación con sus detalles en la misma
transacción. Un fallo de cualquier estudiante o detalle revierte todo el envío,
incluida una sesión nueva. Los correos se programan después del commit, solo por
ausencias realmente nuevas, incluso si el estudiante ya está en ROJA.

El envío sigue siendo la confirmación de clase impartida. Las fechas futuras se
rechazan según Colombia; el fin debe ser posterior al inicio. Los estados
CANCELADA y REPROGRAMADA no se convierten automáticamente. Cinco horas académicas
por sesión válida siguen siendo independientes de su duración cronológica.

## Trazabilidad y compatibilidad

`RegistroImportacionKobo` mantiene su FK `asistencia` para registros individuales.
La nueva relación `asistencias`, a través de `DetalleImportacionKobo`, permite
relacionar una importación con varias asistencias. Cada detalle conserva el campo
del formulario de origen. En las importaciones grupales la FK individual es null.

La migración 0028 completa los detalles de importaciones históricas con FK sin
cambiar sus IDs ni eliminar los vínculos anteriores. El piloto individual sigue
funcionando. Las consultas nuevas que necesiten todas las asistencias de una
importación deben usar la relación múltiple, no solo la FK histórica.

Repetir un mismo UID + ID de envío no crea registros ni correos. Otro ID con
idénticas asistencias reutiliza las existentes y agrega únicamente su trazabilidad.
Un nuevo ID que contradiga un estado ya registrado genera conflicto y no lo
sobrescribe.

## Prueba desde Kobo

1. Enviar el primer formulario completo con tres estados y el segundo con dos.
2. Usar una fecha de clase válida y horas coherentes. Para una clase nueva de
   cada grupo, esos dos envíos producirán dos sesiones y cinco asistencias.
3. Ejecutar desde `Arando_p`:

   ```powershell
   .\.venv\Scripts\python.exe manage.py sincronizar_kobo
   ```

4. Revisar los resúmenes por formulario: respuestas consultadas cuenta envíos;
   asistencias creadas/existentes cuenta estudiantes. El comando consulta todos
   los formularios registrados activos, incluidos otros pilotos que sigan activos.
5. Repetir el comando. No debe agregar asistencias ni correos por los mismos envíos.

Si la clase ya existe, se reutiliza y los incrementos pueden ser menores. La
sincronización recorre también respuestas anteriores del mismo UID. El envío a
Kobo no dispara por sí solo la consulta del backend: se ejecuta el comando.

Para comprobar configuración y metadatos sin importar respuestas:

```powershell
.\.venv\Scripts\python.exe manage.py inspeccionar_formularios_kobo --formulario-uid a7Sco3Aw7XWTnCNHhF8pcf --formulario-uid aiDQR8Dr7BERTRX6fgCvFL
```

## Registrar otro formulario grupal

Primero definir un grupo y estudiantes existentes, con matrículas y asignación
autorizadas. Registrar su UID y cada relación de campo de manera explícita:

```powershell
.\.venv\Scripts\python.exe manage.py configurar_formulario_kobo --formulario-uid UID_NUEVO --docente CODIGO_DOCENTE --aula CODIGO_KOBO_AULA --clei CODIGO_CLEI --formato GRUPAL_V1 --campo-asistencia asistencia_campo_uno=CODIGO_ESTUDIANTE_UNO --campo-asistencia asistencia_campo_dos=CODIGO_ESTUDIANTE_DOS
```

Un registro grupal nuevo queda inactivo por defecto. Revisar metadatos con
`inspeccionar_formularios_kobo` y las vigencias de cada estudiante. Repetir la
configuración con `--activar` para habilitarlo, y ejecutar el diagnóstico local
`verificar_formulario_kobo`. También se pueden gestionar los mapeos en el admin.
El comando no reasigna silenciosamente un campo a otro estudiante.

Para cambiar la lista sin invalidar envíos históricos pendientes, es preferible
crear un UID nuevo con su propio contrato. Actualizar únicamente el formulario
o únicamente el mapeo deja respuestas incompatibles con la lista autorizada.

## Limpieza y pruebas

`limpiar_pruebas_kobo` contempla los detalles múltiples. Conserva marcas de
importación por defecto y elimina sus detalles antes de borrar asistencias. Si
una importación incluye asistencias fuera del alcance, bloquea la limpieza
parcial. Las opciones de reinicio de alertas y reimportación siguen siendo
explícitas. Las consultas SQL manuales antiguas deben contemplar la nueva tabla
de detalles; el archivo SQL anterior no está presente en este checkout.

La suite PostgreSQL encontró 104 pruebas: 99 aprobadas y 5 omitidas porque falta
ese archivo SQL. Incluye concurrencia de un mismo envío grupal, dos formularios
que comparten clase, compatibilidad individual, migración histórica, conteos,
rollback, reintentos, limpieza y un escenario de tres más dos estudiantes.
Las pruebas usan datos ficticios y correo simulado; la entrega real de Gmail
sigue comprobándose con las pruebas operativas autorizadas del piloto.

```powershell
.\.venv\Scripts\python.exe manage.py test seguimiento --settings=config.settings_test_postgres --verbosity 1
```
