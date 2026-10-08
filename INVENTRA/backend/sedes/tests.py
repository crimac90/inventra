"""
Pruebas de la sede (decisión D-30).

Son pocas a propósito: el módulo SED no se construye. Lo que estas pruebas
vigilan es la única promesa que esta entrega sí hace —que toda licorera nace con
su sede— y las dos puertas por las que puede incumplirse.
"""

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from seguridad.models import Usuario
from suscripciones.models import Licorera, Plan

from .models import Sede


class SedePrincipalTests(TestCase):
    """Toda licorera nace con una sede, venga por la puerta que venga."""

    DATOS = {
        "nombre_negocio": "Licorera de Prueba",
        "nombre_completo": "Dueña de Prueba",
        "correo": "duena@prueba.com",
        "password": "Licorera2026",
    }

    def setUp(self):
        cache.clear()

    def test_el_registro_por_autoservicio_crea_la_sede(self):
        self.client.post(reverse("registrar-licorera"), self.DATOS,
                         content_type="application/json")
        licorera = Licorera.objects.get(nombre=self.DATOS["nombre_negocio"])

        self.assertEqual(licorera.sedes.count(), 1)
        self.assertEqual(licorera.sedes.first().nombre, Sede.NOMBRE_PRINCIPAL)

    def test_el_alta_por_la_plataforma_tambien_la_crea(self):
        """
        La segunda puerta (D-26). Si solo la creara el autoservicio, los clientes
        dados de alta por INVENTRA no podrían registrar inventario, y el fallo
        aparecería meses después y en otro módulo.
        """
        operador = Usuario.objects.create_superuser(
            correo="plataforma@inventra.co", nombre_completo="Operador",
            password="Licorera2026")
        acceso = self.client.post(
            reverse("ingresar"),
            {"correo": operador.correo, "password": "Licorera2026"},
            content_type="application/json").json()["acceso"]

        respuesta = self.client.post(
            reverse("alta-licorera"),
            {
                "nombre_negocio": "Licorera Dada de Alta",
                "nombre_completo": "Dueño",
                "correo": "dueno@alta.com",
                "plan": Plan.objects.get(nombre="Pro").id,
                "fecha_fin": str(timezone.localdate() + timedelta(days=30)),
            },
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer %s" % acceso,
        )

        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        licorera = Licorera.objects.get(nombre="Licorera Dada de Alta")
        self.assertEqual(licorera.sedes.count(), 1)

    def test_la_sede_se_pregunta_y_no_se_supone(self):
        """
        `principal_de()` es el único sitio que responde en qué sede se registra el
        inventario. Mientras SED no exista la respuesta no cambia, y por eso mismo
        conviene que exista la pregunta (D-31).
        """
        licorera = Licorera.objects.create(nombre="Sin registro", correo="x@prueba.com")
        self.assertIsNone(Sede.principal_de(licorera))

        creada = Sede.crear_principal(licorera)
        self.assertEqual(Sede.principal_de(licorera), creada)

    def test_una_sede_inactiva_no_se_devuelve(self):
        licorera = Licorera.objects.create(nombre="Cerrada", correo="y@prueba.com")
        sede = Sede.crear_principal(licorera)
        sede.activo = False
        sede.save(update_fields=["activo"])

        self.assertIsNone(Sede.principal_de(licorera))

    def test_la_sede_de_una_licorera_no_es_de_otra(self):
        """El aislamiento entre negocios, que aquí también aplica."""
        una = Licorera.objects.create(nombre="Una", correo="una@prueba.com")
        otra = Licorera.objects.create(nombre="Otra", correo="otra@prueba.com")
        Sede.crear_principal(una)

        self.assertIsNone(Sede.principal_de(otra))
