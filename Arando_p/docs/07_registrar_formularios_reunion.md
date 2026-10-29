# Registrar formularios y preparar la demostración

## Por qué falló el formulario nuevo

`KOBO_FORM_UID` en `.env` selecciona el formulario consultado. No crea ni autoriza
su contexto en la base. Cada UID nuevo necesita una fila `FormularioKobo` con
docente, aula y CLEI; además necesita una `AsignacionDocenteCLEI` activa y una
`MatriculaCLEI` EN_CURSO por estudiante, con fechas compatibles con la clase.

La revisión local del piloto encontró registrado y activo el UID
`aqb3gi22VAatKuPPZqSBnK`, vinculado a `DOC-PRUEBA-001`, aula `AULA-101`, CLEI `III`.
También encontró una asignación activa desde 2026-09-01 y una sola matrícula
EN_CURSO en ese grupo. Esta es una observación del estado revisado, no una
garantía de vigencia futura o de que otros estudiantes estén ya matriculados.

## Flujo de registro por cada formulario

1. Identificar el UID del proyecto de Kobo. Es el identificador de su URL de
   administración, no el ID numérico de una respuesta ni el enlace público Enketo.
2. Definir el docente, aula y CLEI autorizados, usando códigos existentes. El aula
   y el docente deben pertenecer a la misma institución.
3. Verificar/registrar la asignación docente para ese grupo y la matrícula de
   cada estudiante. Crear un formulario no crea estos registros académicos.
4. Registrar el UID en Django. Desde `Arando_p`, para el formulario ya verificado:

   ```powershell
   .\.venv\Scripts\python.exe manage.py configurar_formulario_kobo --formulario-uid aqb3gi22VAatKuPPZqSBnK --docente DOC-PRUEBA-001 --aula AULA-101 --clei III
   ```

   Para el segundo, sustituir los marcadores por su distribución autorizada:

   ```powershell
   .\.venv\Scripts\python.exe manage.py configurar_formulario_kobo --formulario-uid UID_SEGUNDO --docente CODIGO_DOCENTE --aula CODIGO_KOBO_AULA --clei CODIGO_CLEI
   ```

   Repetir el mismo registro es idempotente. El comando no reasigna un UID ya
   vinculado a otro grupo ni reactiva uno desactivado. Tampoco crea matrículas.
5. Verificar la recepción local para la FECHA REAL de la clase:

   ```powershell
   .\.venv\Scripts\python.exe manage.py verificar_formulario_kobo --formulario-uid aqb3gi22VAatKuPPZqSBnK --fecha 2026-10-28
   ```

   Repetir para el segundo UID. El diagnóstico muestra códigos de contexto y
   cantidades de asignaciones/matrículas compatibles; no expone nombres ni
   consulta respuestas de Kobo. No garantiza que cada envío tenga campos válidos.
6. Comprobar el contrato del formulario, desplegar su versión correcta en Kobo
   y enviar una respuesta de prueba con un estudiante matriculado.
7. Sincronizar únicamente los formularios elegidos:

   ```powershell
   .\.venv\Scripts\python.exe manage.py sincronizar_kobo --formulario-uid aqb3gi22VAatKuPPZqSBnK --formulario-uid UID_SEGUNDO
   ```

   No hace falta cambiar `.env` entre ellos. Para consultar todos los UID
   registrados activos:

   ```powershell
   .\.venv\Scripts\python.exe manage.py sincronizar_kobo --todos
   ```

   Sin opciones consulta todos los formularios registrados activos; `--todos`
   conserva el mismo significado como opción explícita. `KOBO_FORM_UID` sigue
   siendo un valor predeterminado para otras utilidades de un solo formulario,
   pero no limita el comando general de sincronización. UID repetidos explícitos se consultan
   una sola vez. El comando comprueba los registros del lote antes de descargar
   respuestas. Si falla una consulta, informa el tipo de error y continúa con los
   demás; los envíos ya confirmados mantienen su idempotencia al reintentar.

## Contrato individual vigente

El envío contiene `codigo_docente`, `codigo_institucion`, `codigo_aula`, `clei`,
`fecha_sesion`, `hora_inicio`, `hora_fin`, `codigo_estudiante` y
`estado_asistencia` (PRESENTE/AUSENTE), además del `_id` de Kobo. Los códigos
precargados deben ser campos enviados, no solo texto de una nota.

El servidor identifica el formulario por el UID que consulta, no por un valor
editable del envío. Valida fecha, horas, grupo, asignación y matrícula. Después
crea/reutiliza una sesión REALIZADA y su asistencia, y notifica solo ausencias
nuevas. No acredita la identidad personal de quien posee el enlace del formulario.

## Qué falta para dos formularios con varios estudiantes

La consulta de formularios encontró varios proyectos ya desplegados. Falta
seleccionar el segundo UID y confirmar los códigos de estudiantes de cada grupo.
No se asume que estudiantes existentes estén matriculados en un grupo, ni se
crean relaciones para completar una demostración sin esa distribución.

Sincronizar varios formularios ya está disponible con este incremento. Recibir
un solo envío con una lista de asistencias todavía requiere implementar el
contrato grupal y relacionar la importación con varias asistencias, preservando
el contrato individual anterior. No basta con agregar preguntas al formulario.

Para la reunión, el objetivo grupal será: una cabecera institucional y de clase,
una fila PRESENTE/AUSENTE por estudiante precargado y un envío que crea una sola
sesión con varias asistencias. Se necesita verificar la estructura de los dos
formularios seleccionados antes de modificar sus versiones desplegadas.

No se modificaron datos del piloto ni proyectos de Kobo en este incremento.
