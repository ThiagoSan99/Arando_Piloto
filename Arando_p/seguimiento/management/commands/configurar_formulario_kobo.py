from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from seguimiento.kobo_client import KoboClient
from seguimiento.models import Aula, CLEI, Docente, FormularioKobo, CampoAsistenciaKobo, Estudiante, FormatoRegistroKobo


class Command(BaseCommand):
    help = "Vincula un formulario Kobo a un grupo existente sin crear personas ni aulas."

    def add_arguments(self, parser):
        parser.add_argument("--formulario-uid", default=KoboClient.FORM_UID)
        parser.add_argument("--docente", required=True, help="Código de docente existente.")
        parser.add_argument("--aula", required=True, help="Código Kobo del aula existente.")
        parser.add_argument("--clei", required=True, help="Código CLEI existente.")
        parser.add_argument("--formato", choices=FormatoRegistroKobo.values)
        parser.add_argument("--campo-asistencia", action="append", default=[],
                            help="Mapeo explícito CAMPO=CODIGO_ESTUDIANTE. Repetir por estudiante.")
        parser.add_argument("--activar", action="store_true", help="Activa tras validar la configuración.")

    def handle(self, *args, **options):
        mapas = []
        for texto in options["campo_asistencia"]:
            partes = texto.split("=", 1)
            if len(partes) != 2 or not all(partes):
                raise CommandError("Cada --campo-asistencia debe usar CAMPO=CODIGO_ESTUDIANTE.")
            mapas.append(tuple(partes))
        if len({campo for campo, _ in mapas}) != len(mapas) or len({codigo for _, codigo in mapas}) != len(mapas):
            raise CommandError("No repitas campos ni estudiantes en la lista.")
        try:
            with transaction.atomic():
                docente = Docente.objects.get(codigo=options["docente"])
                aula = Aula.objects.get(codigo_kobo=options["aula"])
                clei = CLEI.objects.get(codigo=options["clei"])
                contexto = {
                    "docente_id": docente.pk,
                    "aula_id": aula.pk,
                    "clei_id": clei.pk,
                }
                formulario = FormularioKobo.objects.filter(
                    formulario_uid=options["formulario_uid"]
                ).first()
                if formulario is not None:
                    if any(getattr(formulario, campo) != valor
                           for campo, valor in contexto.items()):
                        raise CommandError(
                            "El UID ya está vinculado a otro contexto. "
                            "No se modificó la configuración."
                        )
                else:
                    formulario = FormularioKobo(formulario_uid=options["formulario_uid"], **contexto)
                    if options["formato"] == FormatoRegistroKobo.GRUPAL_V1:
                        formulario.activo = False
                if options["formato"] is not None:
                    formulario.formato = options["formato"]
                if mapas and formulario.formato != FormatoRegistroKobo.GRUPAL_V1:
                    raise CommandError("Los campos de asistencia requieren formato GRUPAL_V1.")
                if formulario.formato == FormatoRegistroKobo.INDIVIDUAL and formulario.pk and formulario.campos_asistencia.exists():
                    raise CommandError("El formulario tiene campos grupales configurados; no se convirtió a individual.")
                formulario.full_clean()
                formulario.save()
                for campo, codigo in mapas:
                    estudiante = Estudiante.objects.get(codigo=codigo)
                    existente = formulario.campos_asistencia.filter(campo=campo).first()
                    if existente is not None and existente.estudiante_id != estudiante.pk:
                        raise CommandError("El campo ya está asignado a otro estudiante; no se reasignó.")
                    mapa = existente or CampoAsistenciaKobo(formulario=formulario, campo=campo, estudiante=estudiante)
                    mapa.full_clean()
                    mapa.save()
                if formulario.formato == FormatoRegistroKobo.GRUPAL_V1 and not formulario.campos_asistencia.exists():
                    raise CommandError("Un formulario grupal necesita al menos un campo de asistencia configurado.")
                if options["activar"]:
                    formulario.activo = True
                    formulario.save(update_fields=["activo", "fecha_actualizacion"])
        except ObjectDoesNotExist as error:
            raise CommandError(
                "No existe el docente, aula o CLEI indicado; no se crearon registros."
            ) from error
        except ValidationError as error:
            raise CommandError(
                "La vinculación no es válida. Revisa UID, docente e institución del aula."
            ) from error
        except IntegrityError as error:
            raise CommandError(
                "La configuración cambió simultáneamente. Repite el comando para verificarla."
            ) from error

        self.stdout.write(self.style.SUCCESS(
            f"Formulario configurado: {formulario.formato}; {'activo' if formulario.activo else 'inactivo'}."
        ))
