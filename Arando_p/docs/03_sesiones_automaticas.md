# Parte 3: sesiones automáticas desde el formulario individual

## Comportamiento aprobado

El envío válido confirma que la clase se impartió. No se agrega otra pregunta de
confirmación al formulario. Se rechazan fechas posteriores a la fecha local de
America/Bogota. Se aceptan fechas pasadas sin límite de retraso, siempre que
existan la asignación activa y la matrícula EN_CURSO válidas para esa fecha,
conforme a las validaciones del incremento anterior.

La política aprobada se refiere a fechas: este incremento no impone un corte por
hora de envío para clases del día actual. La duración cronológica se conserva;
no modifica el reconocimiento de cinco horas académicas.

## Creación y reutilización

- La identidad única es aula + CLEI + docente + fecha + hora de inicio.
- Cada sesión tiene contexto institucional propio. `horario` es opcional y
  conserva su función de planificación. No se crean horarios desde Kobo.
- Una sesión nueva del formulario autorizado se crea REALIZADA y referencia la
  asignación que autorizó el registro.
- Una sesión existente REALIZADA se reutiliza; una PROGRAMADA se confirma como
  REALIZADA. Se conservan su ID y horario. El fin debe coincidir con el existente.
- CANCELADAS y REPROGRAMADAS se rechazan sin cambiar su estado administrativo.
- El UID original sin vinculación mantiene el flujo de reutilización de sesiones
  REALIZADAS existentes, sin exigir hora final. No puede crear sesiones nuevas.
- Los demás estudiantes de la base no reciben ausencias implícitas.

Las propiedades del serializador de sesiones conservan sus nombres. Ahora se
obtienen del contexto propio de la sesión y se agregan los IDs de aula, CLEI,
docente y asignación. `horario` puede ser null. Las notificaciones obtienen el
contexto institucional de la sesión e incluyen sus horas.

Los creadores anteriores que usan `SesionClase(horario=...)` con `save()` o
`full_clean()` completan el contexto automáticamente desde el horario. Las
operaciones masivas deben proporcionar los nuevos campos explícitamente.

## Transacciones y concurrencia

El procesamiento bloquea formulario, asignación, estudiante y sesión, en ese
orden. La matrícula se vuelve a comprobar y bloquear antes de crear la asistencia.
El bloqueo de la asignación serializa formularios distintos del mismo grupo.
La clave única de PostgreSQL también protege contra duplicados creados desde
otros puntos de escritura. Si otra transacción gana la creación de una sesión,
el servicio utiliza un savepoint y recupera la sesión ya creada.

La sesión, asistencia, importación y caso se confirman en la misma transacción.
Un error revierte también la sesión nueva o la confirmación de una PROGRAMADA.
Los correos se programan después del commit, una vez por ausencia nueva. SMTP
con reintentos persistentes continúa fuera del alcance de este incremento.

## Migraciones y activación pendiente en el piloto

1. `0024_contexto_sesion`: agrega relaciones inicialmente anulables y permite
   mantener una sesión sin horario.
2. `0025_completar_contexto_sesion`: valida el histórico y completa aula, CLEI y
   docente desde su horario. No inventa asignaciones ni cambia identificadores.
3. `0026_restricciones_sesion`: exige contexto completo, unicidad e inicio < fin.

La migración se detiene ante duplicados, instituciones incoherentes, horas
inválidas o contradicciones del contexto. No fusiona ni elimina datos. Se debe
revisar el conflicto antes de continuar. Cada migración es atómica, pero una
migración anterior de la secuencia puede haber quedado aplicada si falla otra.

Antes de activar: respaldar la base y detener temporalmente procesos de Django y
sincronizadores mientras se completa la actualización del esquema. Desde el
directorio `Arando_p`:

```powershell
.\.venv\Scripts\python.exe manage.py migrate seguimiento 0026
.\.venv\Scripts\python.exe manage.py configurar_formulario_kobo --docente CODIGO_DOCENTE --aula CODIGO_KOBO_AULA --clei CODIGO_CLEI
```

Sustituir los marcadores por códigos existentes verificados. La configuración
utiliza `KOBO_FORM_UID` del entorno. Confirmar asignación y matrícula antes de la
primera sincronización. Esta entrega no ejecuta estos comandos sobre el piloto.

No retroceder al esquema anterior después de crear sesiones sin horario sin
preparar una estrategia que conserve esas sesiones: el esquema anterior exige
un horario y no puede representar directamente esos registros.

## Pruebas reproducibles

Pruebas rápidas con SQLite en memoria (las de concurrencia se omiten):

```powershell
.\.venv\Scripts\python.exe manage.py test seguimiento --settings=config.settings_test --verbosity 1
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run --settings=config.settings_test
```

Pruebas completas con PostgreSQL, incluidos bloqueos y migraciones históricas:

```powershell
.\.venv\Scripts\python.exe manage.py test seguimiento --settings=config.settings_test_postgres --verbosity 1
```

La configuración PostgreSQL crea una base de pruebas con nombre aleatorio
`test_arando_sesiones_*` y la elimina al terminar. Usa las credenciales locales
configuradas y la base de mantenimiento postgres; no prueba sobre arando_db.
El usuario de PostgreSQL necesita permisos para crear esa base. El correo usa
memoria y las notificaciones de los escenarios de asistencia se simulan.

La suite comprueba creación, reutilización, varios estudiantes, envíos repetidos
y simultáneos, vigencias, fecha local, rollback y reintento, horas reconocidas y
revalidación, alertas y notificaciones, compatibilidad del piloto, restricciones
SQL, serialización sin horario y preservación del histórico al migrar. No se
realizan envíos reales a Kobo ni Gmail.
