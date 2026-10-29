# Sustitución de formularios y estado de recepción grupal — 2026-10-28

Estado posterior: la recepción grupal fue implementada y ambos UID quedaron
activos. Consultar `10_recepcion_grupal_activa.md` para el contrato y las pruebas.

| UID retirado de la configuración local | UID nuevo registrado | Docente | Aula | Estado nuevo |
|---|---|---|---|---|
| ahY7XJ8XWxktEDcMJ3PmXx | a7Sco3Aw7XWTnCNHhF8pcf | DOC-DEMO-001 | DEMO-NAR-Z1-I1-A1 | Inactivo, pendiente de importador grupal |
| aPE9NpdweqBP6FeJafbiRV | aiDQR8Dr7BERTRX6fgCvFL | DOC-DEMO-003 | DEMO-CAU-Z1-I1-A1 | Inactivo, pendiente de importador grupal |

Ambos grupos corresponden a CLEI III. Se verificaron los códigos precargados de
sus metadatos en Kobo antes de registrar las vinculaciones. La sustitución fue
transaccional y se comprobó que las cantidades de sesiones, asistencias e
importaciones permanecieran iguales. No se eliminaron proyectos en Kobo ni
se procesaron respuestas o enviaron correos.

## Diferencia respecto a los formularios anteriores

Los anteriores usaban `codigo_estudiante` y `estado_asistencia`: un estudiante
por envío, varios envíos podían compartir sesión.

Los nuevos tienen `formato_registro` y campos individuales de asistencia para
todo el listado, sin esos dos campos del contrato individual:

- Primer formulario: `asistencia_est_demo_001`, `asistencia_est_demo_002`,
  `asistencia_est_demo_003`.
- Segundo formulario: `asistencia_est_demo_012`, `asistencia_est_demo_013`.

El backend actual aún no interpreta ese formato grupal. Los nuevos UID se
mantienen inactivos para que la sincronización predeterminada no los procese con
el contrato individual. Registrarlos no equivale a implementar su recepción.

## Siguiente incremento pendiente de confirmación

Adaptar la validación de cabecera y de cada asistencia; establecer un mapeo
explícito y autorizado entre campos del formulario y estudiantes; relacionar una
importación con varias asistencias sin perder trazabilidad del piloto; mantener
una sesión por grupo/clase; confirmar todas las asistencias del envío de forma
atómica; notificar cada ausencia nueva después del commit; probar reintentos,
concurrencia y compatibilidad individual. Después se podrán activar ambos UID.

Las utilidades de limpieza también deberán reconocer esas relaciones múltiples
para conservar la prevención de reimportación y la integridad del histórico.
