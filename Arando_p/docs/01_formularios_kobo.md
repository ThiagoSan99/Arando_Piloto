# Parte 1: vinculación de formularios Kobo con grupos

Cada formulario se identifica por un UID único y se vincula con un docente,
un aula y un CLEI. Un docente puede tener varios formularios para sus grupos.
La institución se obtiene del aula; no se duplica en esta configuración.

## Alcance de esta entrega

- Modelo `FormularioKobo` y migración aditiva `0023_formulario_kobo`.
- Validación de que docente y aula pertenezcan a la misma institución mediante
  `full_clean()`, que también ejecuta el formulario del administrador de Django.
- UID único en la base de datos y relaciones protegidas contra eliminación.
- Posibilidad de desactivar la configuración conservando sus relaciones.
- Gestión de la configuración desde `/admin/`, sujeta a los permisos de Django.
- Pruebas con datos ficticios y una base SQLite temporal en memoria.

No se ha aplicado la migración sobre PostgreSQL ni se ha registrado una
vinculación para el piloto: se necesitan los identificadores verificados de su
docente, aula y CLEI. No se infieren a partir de los demás estudiantes de la BD.

El importador individual y `KoboClient.FORM_UID` mantienen su funcionamiento
actual. En esta parte todavía no consumen la nueva configuración ni crean
sesiones automáticamente. El listado precargado de estudiantes y los envíos
grupales se incorporarán en incrementos posteriores.

La configuración no verifica quién utiliza el enlace del formulario. La futura
integración utilizará el UID de origen consultado por el backend, no un UID ni
una identidad docente declarados libremente en el contenido de la respuesta.
La vigencia de `AsignacionDocenteCLEI` y la matrícula se validarán para la fecha
de la sesión al integrar el procesamiento. Crear esta configuración no sustituye
esas validaciones.

## Verificación sin modificar PostgreSQL

Desde `E:\Arando\Arando_Piloto\Arando_p`:

```powershell
.\.venv\Scripts\python.exe manage.py test seguimiento --settings=config.settings_test --verbosity 2
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run --settings=config.settings_test
```

Las pruebas verifican el contexto institucional, varios grupos por docente,
rechazo de cruces de institución, obligatoriedad y unicidad del UID, desactivación,
protección de referencias, ausencia de efectos sobre sesiones/importaciones y
reimportación de un envío ya procesado sin exigir la nueva configuración.

La configuración de pruebas usa correo en memoria. SQLite no certifica los
bloqueos ni la concurrencia de PostgreSQL; estos se probarán al incorporar la
creación transaccional de sesiones. Esta entrega tampoco certifica el flujo
integral Kobo → PostgreSQL → Gmail.

## Aplicación en el piloto, pendiente del siguiente paso autorizado

Después de revisar esta entrega, la migración se puede aplicar con:

```powershell
.\.venv\Scripts\python.exe manage.py migrate seguimiento 0023
```

Este comando sí modifica el esquema de la base configurada. Después se podrá
registrar el formulario desde el administrador usando los IDs existentes y
verificados de docente, aula y CLEI. No se incluyen IDs institucionales ficticios
ni credenciales en esta entrega. Si se configura desde código, se debe ejecutar
`full_clean()` antes de `save()`, siguiendo el patrón de los servicios existentes.

El siguiente incremento propuesto es conectar el UID de origen con este contexto
y validar asignación/matrícula manteniendo el formulario individual. Las políticas
para fechas futuras y registros tardíos deben definirse antes de implementar la
creación automática de sesiones REALIZADAS. El envío válido será la confirmación
de clase impartida y no se agregará otra pregunta de confirmación al formulario.
