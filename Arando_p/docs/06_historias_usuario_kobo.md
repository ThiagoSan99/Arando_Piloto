# Historias de usuario y criterios de aceptación

Estas HDU describen el piloto individual y su evolución. Los criterios pendientes
se distinguen del comportamiento implementado. No autorizan nuevas limpiezas ni
cambios de datos institucionales por sí mismos.

| ID | Historia de usuario | Criterios de aceptación | Referencia |
|---|---|---|---|
| HU-01 | Como docente, quiero registrar fecha y horas de una clase para dejar constancia de su realización. | Envío válido crea/reutiliza REALIZADA; fecha futura se rechaza según Colombia; fin posterior a inicio; no se exige otra confirmación. | CP-01, 10, 11, 17 |
| HU-02 | Como docente, quiero que mi formulario tenga el contexto del grupo precargado para no escribir códigos. | UID vinculado a docente/aula/CLEI; códigos enviados coinciden; institución coherente; un docente admite varios formularios. Esto no autentica a quien posee el enlace. | CP-12, 15 |
| HU-03 | Como docente, quiero marcar PRESENTE o AUSENTE para registrar la participación del estudiante del piloto. | Una asistencia por estudiante/sesión; matrícula válida; los demás estudiantes de la BD no reciben ausencias implícitas. | CP-01, 05, 14, 19 |
| HU-04 | Como coordinador, quiero aceptar clases solo de docentes asignados al grupo para evitar registros no autorizados. | Asignación activa vigente para la fecha; cruces entre instituciones o grupos se rechazan antes de crear datos. | CP-12, 13 |
| HU-05 | Como operador, quiero repetir la sincronización para recuperar procesos sin duplicar registros ni correos. | Clave formulario/envío única; repetición no genera asistencia ni correo; otro envío equivalente reutiliza la asistencia. | CP-02, 03, 20 |
| HU-06 | Como responsable académico, quiero reconocer cinco horas por sesión válida para medir el avance de la matrícula. | PRESENTE o ausencia revalidada APROBADA en REALIZADA reconoce cinco horas; ausencia no revalidada o sesión CANCELADA reconoce cero. | CP-01, 08, 18 |
| HU-07 | Como coordinador, quiero un caso activo por estudiante que refleje sus ausencias efectivas para priorizar el acompañamiento. | 1 TEMPRANA, 2 AMARILLA, 3+ ROJA; 0 sin riesgo; revalidación permite disminuir nivel; cerrar caso no reinicia historia; conserva cerrados. | CP-05 a 09 |
| HU-08 | Como responsable de seguimiento, quiero recibir aviso por cada ausencia nueva para actuar oportunamente. | Un aviso por ausencia nueva aun en ROJA; ninguno por repetición; incluye contexto institucional, fecha/horas, asistencia, riesgo, conteos y estado del caso. | CP-05 a 07, 20, 23 |
| HU-09 | Como operador del piloto, quiero limpiar solo un grupo y revisar el impacto antes de borrar para preparar una ronda controlada. | Vista previa predeterminada; alcance explícito docente/aula/CLEI y rango opcional; ejecución exige base y huella; conserva maestros, matrículas y asignaciones. | CL-01, 02, 06, 07 |
| HU-10 | Como operador, quiero elegir si los envíos históricos se vuelven a procesar para controlar la repetición de pruebas. | Conserva marcas por defecto; elimina marcas vinculadas solo con opción explícita; advierte que un reproceso puede volver a notificar. No modifica Kobo. | CL-03, 04 |
| HU-11 | Como coordinador del piloto, quiero reiniciar alertas ficticias sin afectar historial ajeno para obtener resultados de prueba interpretables. | Exige opción explícita; incluye dependencias de alertas; bloquea estudiantes con asistencias fuera del alcance; no recalcula ni borra historia externa silenciosamente. | CL-05 |
| HU-12 | Como desarrollador, quiero procesar concurrentemente y revertir errores para mantener integridad. | PostgreSQL impide sesiones y asistencias duplicadas; operación atómica; fallo revierte también nueva sesión; correo después del commit. | CP-20, 22 |
| HU-13 | Como analista, quiero consultar sesiones por docente, institución, aula, CLEI y fecha para construir dashboards. | Sesión guarda contexto propio y horas; institución se consulta por aula y zona por institución; la API mantiene campos previos y admite horario null. El dashboard aún no se implementa. | CP-01, 04, 21 |
| HU-14 | Como docente, quiero registrar todos los estudiantes de mi grupo en un formulario para evitar envíos individuales. | Una cabecera de clase y varias asistencias; listado precargado de matriculados; un único envío trazable a varias asistencias. **Pendiente: el importador actual sigue siendo individual.** | CP-21 prepara el backend, no certifica formulario grupal |
| HU-15 | Como operador, quiero reintentar notificaciones fallidas sin duplicar asistencias para recuperar avisos no entregados. | Evento persistente por ausencia, estados e intentos, reintento controlado y trazabilidad; distinguir resultado SMTP incierto. **Pendiente: todavía no existe esa cola.** | CP-23 describe el límite actual |

La identidad autenticada del remitente de Kobo, los datos institucionales reales,
la nomenclatura definitiva y el tratamiento de matrículas/asignaciones ya
cerradas en cargas históricas requieren sus definiciones específicas. No se
resuelven inventando códigos, relaciones ni autorizaciones.
