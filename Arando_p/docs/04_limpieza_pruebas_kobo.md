# Limpieza controlada del piloto y preparación de una nueva prueba

El script ejecutable es el comando Django
`seguimiento/management/commands/limpiar_pruebas_kobo.py`. No es SQL global ni
`flush`: actúa únicamente sobre un docente, aula y CLEI indicados explícitamente.
La ejecución predeterminada es una vista previa sin escrituras.

No se ha ejecutado sobre los datos del piloto.

## Qué conserva y qué puede limpiar

Siempre conserva proyectos, departamentos, zonas, instituciones, aulas, CLEI,
docentes, estudiantes, matrículas, asignaciones docentes, usuarios y vinculación
del formulario. No cambia códigos ni reinicia secuencias de IDs.

| Registro | Comportamiento |
|---|---|
| Sesiones del docente/aula/CLEI y rango indicado | Se eliminan al confirmar el plan. Incluye todos sus estados. |
| Asistencias y revalidaciones de esas sesiones | Se eliminan junto con las sesiones. |
| Horarios de esa combinación | Solo con `--incluir-horarios`; conserva los usados por sesiones fuera del alcance. |
| Alertas, casos abiertos/cerrados y seguimientos de estudiantes afectados | Exigen `--reiniciar-alertas`; si no se permite, bloquean la limpieza. |
| Historial global de un estudiante con asistencias fuera del alcance | Bloquea el reinicio de sus alertas. No se elimina parcialmente ni se recalcula de forma implícita. |
| Importaciones ligadas a las asistencias seleccionadas | Conserva su clave formulario/envío y desvincula la asistencia para impedir reimportación automática. |
| Esas mismas importaciones con `--permitir-reimportacion` | Se eliminan; Kobo podrá volver a procesarlas y las ausencias podrán volver a notificar. |
| Importaciones sin asistencia asociada | Se conservan: no se puede atribuirlas con seguridad al grupo. |
| Respuestas almacenadas en Kobo y correos enviados | No se modifican. |

El reinicio de alertas elimina también sus decisiones administrativas e historial
de seguimiento: debe usarse únicamente para los registros ficticios del piloto
que se desee reiniciar. El sistema no dispone de una marca universal que pruebe
si cada fila es ficticia; la revisión del alcance corresponde al operador.

## Uso desde PowerShell

Ubicarse en `E:\Arando\Arando_Piloto\Arando_p`. Detener la sincronización mientras
se limpia y tener un respaldo de la base, por ejemplo mediante pgAdmin. Sustituir
los marcadores por los códigos existentes y verificados de ese grupo.

### Opción recomendada: limpiar y usar envíos nuevos

Primero obtener el plan. Sin fechas se incluyen todas las sesiones de esa
combinación de docente, aula y CLEI:

```powershell
.\.venv\Scripts\python.exe manage.py limpiar_pruebas_kobo --docente CODIGO_DOCENTE --aula CODIGO_KOBO_AULA --clei CODIGO_CLEI --incluir-horarios --reiniciar-alertas
```

Revisar cantidades y bloqueos. Copiar la huella completa mostrada. Ejecutar con
los mismos filtros y opciones, agregando la base y huella verificadas:

```powershell
.\.venv\Scripts\python.exe manage.py limpiar_pruebas_kobo --docente CODIGO_DOCENTE --aula CODIGO_KOBO_AULA --clei CODIGO_CLEI --incluir-horarios --reiniciar-alertas --ejecutar --confirmar-base arando_db --confirmar-plan HUELLA_DEL_PLAN
```

Si la base tiene otro nombre, usar exactamente el que muestre el plan. Si cambia
el contenido seleccionado o las opciones, se debe generar otra vista previa.
El script no crea ni solicita contraseñas y no muestra datos personales.

Para limitar las sesiones por fecha, agregar a AMBOS comandos:

```powershell
--desde 2026-10-20 --hasta 2026-10-27
```

Las fechas son inclusivas y solo ilustran la sintaxis; elegir el intervalo real
del piloto. Los horarios no tienen fecha: se borran los de ese contexto que no
queden usados, incluso si ya estaban vacíos. Si se quiere conservar planificación,
omitir `--incluir-horarios`.

### Repetir los mismos envíos de Kobo

Agregar `--permitir-reimportacion` tanto a la vista previa como a la ejecución.
Esto elimina las marcas de los envíos vinculados a las asistencias limpiadas.
La próxima sincronización recorrerá las respuestas que continúan en Kobo y
podrá recrear sesiones, asistencias, casos y notificaciones. No usar esta opción
si se desea probar exclusivamente con envíos nuevos.

Esta decisión se toma ANTES de limpiar: las marcas que una limpieza anterior ya
desvinculó de sus asistencias no se borran después con este comando, porque ya no
se puede demostrar su grupo a partir de esa relación. Para esas rondas, enviar
nuevas respuestas o planificar por separado un reinicio del formulario verificado.

El comando también funciona sobre el esquema anterior, desde `0022_casoalerta`,
para limpiar datos ficticios que impidan aplicar las migraciones de sesiones.
Detecta el estado de migraciones aplicado y no consulta columnas aún inexistentes.
No elimina tablas ni migraciones. En PostgreSQL la ejecución bloquea las tablas
operativas mientras se realiza la limpieza; si no obtiene el bloqueo en cinco
segundos o hay una dependencia protegida, revierte la transacción.

## Retomar las pruebas

1. Si aún no se aplicaron, ejecutar las migraciones del nuevo backend:

   ```powershell
   .\.venv\Scripts\python.exe manage.py migrate seguimiento 0026
   ```

2. Vincular el formulario configurado en `.env` con registros existentes:

   ```powershell
   .\.venv\Scripts\python.exe manage.py configurar_formulario_kobo --docente CODIGO_DOCENTE --aula CODIGO_KOBO_AULA --clei CODIGO_CLEI
   ```

3. Verificar que existen asignación activa y matrícula EN_CURSO, ambas vigentes
   para las fechas de prueba. No es necesario crear horarios ni sesiones.
4. Reiniciar los procesos Django para recargar `.env` y enviar una respuesta NUEVA
   en Kobo con fecha pasada o actual de Colombia, horas coherentes y PRESENTE.
5. Sincronizar y revisar el resumen:

   ```powershell
   .\.venv\Scripts\python.exe manage.py sincronizar_kobo
   ```

6. Consultar las sesiones/asistencias mediante la API autenticada o pgAdmin.
   Repetir la sincronización: no debe crear otra asistencia ni enviar otro correo.
7. Ejecutar los escenarios de `05_casos_prueba_kobo.md`. Usar únicamente datos
   ficticios y destinatarios de prueba autorizados al probar notificaciones.

`--limite` en sincronización indica tamaño de página, no una frontera que impida
procesar respuestas antiguas. Para mantener aislada una ronda, usar nuevos IDs de
envío y conservar las marcas previas, o un formulario y base de pruebas separados.

## Verificación del script sin tocar el piloto

```powershell
.\.venv\Scripts\python.exe manage.py test seguimiento.tests_limpieza seguimiento.tests_migraciones --settings=config.settings_test --verbosity 1
.\.venv\Scripts\python.exe manage.py test seguimiento --settings=config.settings_test_postgres --verbosity 1
```

La segunda opción crea y elimina una base PostgreSQL temporal con nombre
aleatorio y correo en memoria, como se explica en la entrega anterior.
