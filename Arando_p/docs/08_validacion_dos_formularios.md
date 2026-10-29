# Validación de dos formularios con varios estudiantes — 2026-10-28

Estado posterior: estos dos UID fueron retirados de la configuración local por
solicitud del usuario. Consultar `09_nuevos_formularios_grupales.md` para sus
sustitutos y las limitaciones de recepción del nuevo formato grupal.

## Configuración verificada y registrada

| Formulario UID | Docente | Aula | CLEI | Opciones con matrícula compatible |
|---|---|---|---|---|
| ahY7XJ8XWxktEDcMJ3PmXx | DOC-DEMO-001 | DEMO-NAR-Z1-I1-A1 | III | 3 de 3 |
| aPE9NpdweqBP6FeJafbiRV | DOC-DEMO-003 | DEMO-CAU-Z1-I1-A1 | III | 2 de 2 |

Se consultaron los metadatos de Kobo, no las respuestas. Para la fecha indicada
se encontró una asignación activa y vigente en cada grupo, y matrículas
compatibles para todas las opciones de sus selectores. Los dos UID se vincularon
en Django con esos contextos y pasaron el diagnóstico local. No se modificaron
personas, matrículas ni asignaciones.

Las cantidades son una instantánea de la revisión: si se agregan matrículas,
también hay que actualizar las opciones del formulario en Kobo. La base no
actualiza automáticamente el selector de estudiantes de un formulario existente.

## Qué permiten estos formularios

Ambos usan `codigo_estudiante` de tipo `select_one`. El docente selecciona un
estudiante y registra PRESENTE/AUSENTE; cada envío contiene una sola asistencia.
El mismo formulario admite muchos estudiantes mediante envíos sucesivos.

Para una clase, mantener iguales fecha, inicio y fin al registrar cada
estudiante. El servidor reutiliza una sola sesión por docente/aula/CLEI/fecha/
inicio y crea una asistencia por estudiante. Una hora final contradictoria se
rechaza. Un alumno de otro grupo o sin matrícula correspondiente se rechaza.

Esta estructura no es una lista grupal de todos los estudiantes en un solo envío.
Esa modalidad requeriría otro contrato de captura/importación; no se introdujeron
migraciones ni cambios innecesarios para validar estos dos formularios.

## Diagnóstico repetible sin importar respuestas

Desde `Arando_p`:

```powershell
.\.venv\Scripts\python.exe manage.py inspeccionar_formularios_kobo --formulario-uid ahY7XJ8XWxktEDcMJ3PmXx --formulario-uid aPE9NpdweqBP6FeJafbiRV
```

Este comando consulta únicamente metadatos de Kobo y compara los códigos
precargados y cantidades de estudiantes con las matrículas locales. Se puede
agregar `--fecha YYYY-MM-DD` para verificar las vigencias de la clase que se
quiere probar. No crea configuraciones ni imprime nombres de estudiantes.

La verificación exclusivamente local se mantiene disponible:

```powershell
.\.venv\Scripts\python.exe manage.py verificar_formulario_kobo --formulario-uid ahY7XJ8XWxktEDcMJ3PmXx --fecha 2026-10-28
.\.venv\Scripts\python.exe manage.py verificar_formulario_kobo --formulario-uid aPE9NpdweqBP6FeJafbiRV --fecha 2026-10-28
```

## Guion de la reunión

1. Elegir una fecha actual o pasada con asignación y matrículas vigentes.
2. Primer formulario: enviar por separado las asistencias de sus tres estudiantes
   para la misma clase, por ejemplo dos PRESENTE y uno AUSENTE.
3. Segundo formulario: enviar las de sus dos estudiantes, por ejemplo un PRESENTE
   y uno AUSENTE. Mantener coherentes las horas dentro de cada grupo.
4. Sincronizar únicamente estos dos formularios:

   ```powershell
   .\.venv\Scripts\python.exe manage.py sincronizar_kobo --formulario-uid ahY7XJ8XWxktEDcMJ3PmXx --formulario-uid aPE9NpdweqBP6FeJafbiRV
   ```

5. Para una clase nueva en cada grupo, el resultado esperado de esos cinco envíos
   es dos sesiones y cinco asistencias. Las tres presencias reconocen cinco horas
   cada una; las ausencias no revalidadas reconocen cero. Cada ausencia nueva
   actualiza su caso y programa el correo a los destinatarios configurados.
6. Repetir la sincronización. No debe agregar sesiones, asistencias ni correos.

El sincronizador recorre también los envíos anteriores que continúen en cada UID.
Por eso, el resumen total puede incluir otros registros. Los conteos anteriores
describen el incremento de estos cinco envíos si son nuevos y válidos. Ejecutar
`sincronizar_kobo` sin argumentos ahora consulta todos los formularios activos,
igual que `--todos`. Para excluir los otros formularios activos de esta
demostración, mantener los dos UID explícitos del ejemplo.
No se ejecutó sincronización real ni se enviaron correos en esta entrega.

## Evidencia automatizada

Se ejecutaron 15 pruebas sobre PostgreSQL temporal para los comandos de
formularios, diagnóstico de metadatos y recepción de varios estudiantes. Se
simularon dos UID con dos estudiantes cada uno, reutilizando los mismos IDs
numéricos entre formularios. Se verificó una sesión por grupo, cuatro asistencias,
cuatro importaciones independientes, dos notificaciones de ausencia y ningún
duplicado al repetir la sincronización. También se probaron matrícula faltante,
estudiante de otro grupo y cambio contradictorio de estado.

```powershell
.\.venv\Scripts\python.exe manage.py test seguimiento.tests_varios_estudiantes seguimiento.tests_formularios --settings=config.settings_test_postgres --verbosity 1
```

Las pruebas usan datos ficticios, respuesta del cliente simulada y correo
simulado. Verifican el procesamiento del backend, pero no sustituyen la prueba
con envíos reales desde los formularios y la comprobación de entrega de Gmail.
