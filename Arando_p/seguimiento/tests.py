from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from .models import (
    Aula, CLEI, Departamento, Docente, FormularioKobo, Institucion,
    Proyecto, RegistroImportacionKobo, SesionClase, Zona,
)


class FormularioKoboTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        proyecto = Proyecto.objects.create(nombre="Proyecto ficticio de pruebas")
        departamento = Departamento.objects.create(nombre="Departamento ficticio")
        zona = Zona.objects.create(
            proyecto=proyecto, departamento=departamento, nombre="Zona ficticia",
        )
        cls.institucion = Institucion.objects.create(
            zona=zona, nombre="Institución ficticia A",
        )
        otra_institucion = Institucion.objects.create(
            zona=zona, nombre="Institución ficticia B",
        )
        cls.aula = Aula.objects.create(institucion=cls.institucion, nombre="Grupo A")
        cls.otra_aula = Aula.objects.create(
            institucion=cls.institucion, nombre="Grupo B",
        )
        cls.aula_otra_institucion = Aula.objects.create(
            institucion=otra_institucion, nombre="Grupo externo",
        )
        cls.clei = CLEI.objects.create(codigo="III", nombre="CLEI III")
        cls.docente = Docente.objects.create(
            institucion=cls.institucion, codigo="DOC-TEST-001",
            nombres="Docente", apellidos="Ficticio",
        )

    def formulario(self, **cambios):
        datos = {
            "formulario_uid": "formulario-ficticio-a",
            "docente": self.docente,
            "aula": self.aula,
            "clei": self.clei,
        }
        datos.update(cambios)
        return FormularioKobo(**datos)

    def test_registra_contexto_institucional_del_grupo(self):
        formulario = self.formulario()
        formulario.full_clean()
        formulario.save()
        formulario.refresh_from_db()
        self.assertEqual(formulario.aula.institucion_id, self.docente.institucion_id)
        self.assertEqual(formulario.clei_id, self.clei.pk)
        self.assertTrue(formulario.activo)

    def test_docente_puede_tener_formularios_para_varios_grupos(self):
        primero = self.formulario()
        primero.full_clean()
        primero.save()
        segundo = self.formulario(
            formulario_uid="formulario-ficticio-b", aula=self.otra_aula,
        )
        segundo.full_clean()
        segundo.save()
        self.assertEqual(self.docente.formularios_kobo.count(), 2)

    def test_rechaza_docente_de_otra_institucion(self):
        formulario = self.formulario(aula=self.aula_otra_institucion)
        with self.assertRaises(ValidationError) as error:
            formulario.full_clean()
        self.assertIn("docente", error.exception.message_dict)

    def test_uid_no_puede_asignarse_a_dos_grupos(self):
        self.formulario().save()
        with self.assertRaises(ValidationError):
            self.formulario(aula=self.otra_aula).full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.formulario(aula=self.otra_aula).save()

    def test_uid_es_obligatorio(self):
        with self.assertRaises(ValidationError):
            self.formulario(formulario_uid="").full_clean()

    def test_desactivar_conserva_el_contexto(self):
        formulario = self.formulario()
        formulario.save()
        formulario.activo = False
        formulario.save(update_fields=["activo", "fecha_actualizacion"])
        formulario.refresh_from_db()
        self.assertFalse(formulario.activo)
        self.assertEqual(formulario.docente_id, self.docente.pk)
        self.assertEqual(formulario.aula_id, self.aula.pk)

    def test_contexto_referenciado_esta_protegido(self):
        self.formulario().save()
        for relacionado in (self.docente, self.aula, self.clei):
            with self.subTest(modelo=relacionado._meta.label):
                with self.assertRaises(ProtectedError):
                    relacionado.delete()

    def test_configurar_formulario_no_crea_sesiones_ni_importaciones(self):
        formulario = self.formulario()
        formulario.full_clean()
        formulario.save()
        self.assertEqual(SesionClase.objects.count(), 0)
        self.assertEqual(RegistroImportacionKobo.objects.count(), 0)


class PilotoIndividualTests(TestCase):
    def test_reimportar_envio_procesado_no_exige_configuracion_nueva(self):
        from unittest.mock import patch

        from .kobo_client import KoboClient
        from .services import procesar_respuesta_kobo

        RegistroImportacionKobo.objects.create(
            formulario_uid=KoboClient.FORM_UID,
            envio_id=123,
            estado=RegistroImportacionKobo.Estado.EXISTENTE,
        )
        with patch("seguimiento.services.validar_asistencia_kobo") as validar:
            with patch("seguimiento.services.notificar_caso_alerta_segura") as notificar:
                resultado = procesar_respuesta_kobo({"_id": 123})
        validar.assert_not_called()
        notificar.assert_not_called()
        self.assertFalse(resultado["importacion_creada"])
        self.assertFalse(resultado["asistencia_creada"])
