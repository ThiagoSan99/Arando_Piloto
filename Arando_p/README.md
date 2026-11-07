# Arando la Educación

Backend Django del piloto para gestionar sesiones, matrículas y asistencias por
CLEI, importar registros desde KoboToolbox y generar alertas de inasistencia.
`core` y `seguimiento` contienen las aplicaciones. La configuración y los
perfiles de pruebas están en `config`.

## Preparar el nuevo equipo

Con el repositorio clonado y en la rama del piloto, ejecuta desde su raíz en
PowerShell. La versión local de referencia es Python 3.13.6.

```powershell
Set-Location Arando_p
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .venv_example .env
```

Copia la plantilla solo si aún no existe `.env`. Completa allí la contraseña
de PostgreSQL y, si vas a usar las integraciones, los valores de Kobo y correo.
Transfiere las credenciales por un canal privado. Git ignora `.env` y la
carpeta `.venv`.

Puedes comprobar la instalación con SQLite en memoria y correo simulado, sin
conectarte a la base del piloto.

```powershell
.\.venv\Scripts\python.exe manage.py check --settings=config.settings_test
.\.venv\Scripts\python.exe manage.py test --settings=config.settings_test
```

## Trasladar el estado del piloto

Git conserva el código, las migraciones y la documentación. La base local
`arando_db` contiene los registros del piloto, los formularios y mapeos de Kobo
configurados y el historial de notificaciones.

Para conservar esos datos, crea un respaldo en el equipo anterior con las
herramientas de PostgreSQL disponibles en el PATH.

```powershell
pg_dump -h localhost -p 5432 -U postgres -d arando_db -Fc -f arando_db.dump
```

Transfiere `arando_db.dump` por un canal privado. En el equipo nuevo, con
PostgreSQL instalado y escuchando en `localhost:5432`, crea una base vacía y
restaura el archivo desde el directorio en que lo guardaste.

```powershell
createdb -h localhost -p 5432 -U postgres arando_db
pg_restore -h localhost -p 5432 -U postgres -d arando_db --exit-on-error arando_db.dump
```

Si prefieres comenzar con una base vacía, ejecuta solo `createdb`. En ambos
casos, desde `Arando_p`, aplica las migraciones pendientes y arranca Django.

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

## Retomar el trabajo

- [Sesiones automáticas](docs/03_sesiones_automaticas.md). Flujo de creación de
  sesiones a partir de los registros de Kobo.
- [Recepción grupal activa](docs/10_recepcion_grupal_activa.md). Contrato
  `GRUPAL_V1` y configuración registrada de los dos formularios del piloto.
- [Diagnóstico SMTP](docs/11_diagnostico_smtp.md) y
  [reenvío controlado](docs/12_reenvio_controlado_2026-10-28.md). Diagnóstico de
  correo, registro persistente de notificaciones y recuperación de avisos.
- Las pruebas que requieren comportamientos propios de PostgreSQL usan
  `--settings=config.settings_test_postgres`, que crea una base temporal
  separada y usa correo en memoria.
