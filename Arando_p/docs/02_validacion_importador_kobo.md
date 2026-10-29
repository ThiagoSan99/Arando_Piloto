# Parte 2: origen autorizado y validación del envío individual

Este incremento conecta el importador con `FormularioKobo`. No crea todavía
sesiones automáticamente ni procesa listas grupales. No cambia la regla de
cinco horas ni las reglas de riesgo. No aplica migraciones a PostgreSQL.

## Contrato comprobado

Se consultó únicamente la estructura del formulario configurado en `KOBO_FORM_UID`
mediante la API de Kobo, sin descargar respuestas. El formulario contiene los
campos calculados `codigo_docente`, `codigo_institucion`, `codigo_aula`, `clei` y
`codigo_estudiante`; los campos `fecha_sesion` (date), `hora_inicio` y `hora_fin`
(time); y `estado_asistencia` con opciones `PRESENTE` y `AUSENTE`.

Esto verifica los nombres del formulario, no los datos realmente enviados ni la
identidad de quien utiliza su enlace. Los elementos de presentación y las notas
del formulario no se consideran instrucciones para el importador.

## Comportamiento

- El sincronizador pasa el UID del cliente al procesador. Un campo UID dentro
  del contenido del envío no reemplaza este origen.
- Los formularios nuevos requieren una vinculación activa con docente, aula y
  CLEI. Los códigos recibidos deben coincidir exactamente con ese contexto.
- Se rechazan contextos institucionales inactivos o incoherentes.
- Se exige una asignación activa cuya vigencia incluya la fecha de la sesión,
  y una matrícula EN_CURSO del estudiante para ese grupo y fecha.
- Se analizan fecha y horas completas. Los valores time con segundos, fracciones
  y desplazamiento horario conservan su hora local para los TimeField existentes.
  Se exige fin posterior a inicio; el fin debe coincidir con la sesión existente.
- `hora_fin` es obligatoria para los formularios vinculados.
- Se registra únicamente al estudiante del envío. Los demás estudiantes de la
  base no reciben una ausencia implícita.
- Una importación ya registrada retorna su resultado sin crear asistencias ni
  programar correos, incluso si posteriormente se desactiva el formulario.
- La clave de idempotencia continúa siendo `(formulario_uid, envio_id)`.

Solo el UID original del piloto, definido en `KoboClient.LEGACY_FORM_UID`, admite
seguir sin vinculación y sin `hora_fin`, reutilizando sesiones existentes.
Si se registra una vinculación para ese UID, se aplican las nuevas validaciones.
Cambiar `KOBO_FORM_UID` a un formulario desconocido no activa una excepción.

La interpretación de asignaciones activas y matrículas EN_CURSO es conservadora.
El tratamiento de inscripciones o asignaciones cerradas para cargas históricas,
fechas futuras y retrasos máximos queda pendiente de definición. Este incremento
no introduce nuevos plazos ni modifica fechas históricas.

## Activación del nuevo formulario en el piloto

La configuración y migración de la parte 1 deben aplicarse antes de utilizar el
importador actualizado. No se debe sincronizar el nuevo formulario hasta vincular
su grupo y verificar su asignación y matrícula existentes.

Desde `E:\Arando\Arando_Piloto\Arando_p`, aplicar la migración aditiva pendiente:

```powershell
.\.venv\Scripts\python.exe manage.py migrate seguimiento 0023
```

Registrar la vinculación con códigos verificados en la base. El comando utiliza
el UID cargado desde `.env`; estos marcadores se deben sustituir:

```powershell
.\.venv\Scripts\python.exe manage.py configurar_formulario_kobo --docente CODIGO_DOCENTE --aula CODIGO_KOBO_AULA --clei CODIGO_CLEI
```

El comando solo crea la vinculación, valida la institución y exige registros
existentes. Repetirlo con el mismo contexto no produce cambios. Si el UID ya está
vinculado a otro contexto, rechaza la operación; tampoco reactiva configuraciones
desactivadas. No crea asignaciones ni matrículas: se comprueban al procesar cada
respuesta.

Abrir un nuevo proceso de Django después de cambiar `.env`, porque el valor de
clase `KoboClient.FORM_UID` se carga al importar el módulo.

La sincronización sigue necesitando una sesión REALIZADA preexistente. La
creación automática de sesiones será el siguiente incremento, después de la
confirmación del usuario y la definición de las políticas pendientes.

## Verificación aislada

```powershell
.\.venv\Scripts\python.exe manage.py test seguimiento --settings=config.settings_test --verbosity 2
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run --settings=config.settings_test
```

Se prueban el contexto autorizado, vigencias inclusivas, matrícula, fechas y
horas, aislamiento por formulario, rollback y reintento, correo después del commit,
idempotencia, compatibilidad del piloto original y el comando de vinculación.
Las pruebas usan SQLite en memoria y correo simulado; no certifican concurrencia
de PostgreSQL ni entrega real de Gmail. No se descarga información de estudiantes.
