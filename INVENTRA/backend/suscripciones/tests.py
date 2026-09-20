"""
Pruebas del registro de licoreras (CU-SUS-01 y RF-SEG-01).

Se ejecutan con `py manage.py test suscripciones`.
"""

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework import status

from seguridad.models import Rol, Usuario

from .models import Licorera, Suscripcion


class RegistroLicoreraTests(TestCase):

    DATOS = {
        "nombre_negocio": "Licorera La Esquina",
        "nombre_completo": "Cristian Macías",
        "correo": "duena@laesquina.com",
        "password": "Licorera2026",
    }

    def setUp(self):
        cache.clear()   # el contador del límite de peticiones parte de cero
        self.url = reverse("registrar-licorera")

    def registrar(self, **cambios):
        datos = {**self.DATOS, **cambios}
        return self.client.post(self.url, datos, content_type="application/json")

    def test_registro_crea_licorera_suscripcion_y_usuario(self):
        respuesta = self.registrar()
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)

        licorera = Licorera.objects.get(nombre=self.DATOS["nombre_negocio"])
        usuario = Usuario.objects.get(correo=self.DATOS["correo"])
        suscripcion = Suscripcion.objects.get(licorera=licorera)

        self.assertEqual(usuario.licorera_id, licorera.id)
        self.assertEqual(usuario.rol.nombre, Rol.ADMINISTRADOR_LICORERA)
        self.assertEqual(suscripcion.plan.nombre, "Básico")
        self.assertEqual(suscripcion.estado, Suscripcion.Estado.ACTIVA)

    def test_el_precio_queda_congelado_en_la_suscripcion(self):
        """El precio pactado se copia al contratar: los aumentos no cambian el histórico."""
        self.registrar()
        suscripcion = Suscripcion.objects.get()
        self.assertEqual(suscripcion.precio_pactado, suscripcion.plan.precio_mensual)

    def test_registro_devuelve_tokens_para_entrar_de_una_vez(self):
        respuesta = self.registrar().json()
        self.assertIn("acceso", respuesta)
        self.assertIn("refresco", respuesta)
        self.assertEqual(respuesta["usuario"]["rol"], Rol.ADMINISTRADOR_LICORERA)

    def test_no_se_puede_repetir_el_correo(self):
        self.registrar()
        respuesta = self.registrar(nombre_negocio="Otra Licorera")
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Licorera.objects.count(), 1)

    def test_contrasena_corta_se_rechaza(self):
        respuesta = self.registrar(password="Abc123")
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_contrasena_sin_numeros_se_rechaza(self):
        """La especificación exige combinar letras y números."""
        respuesta = self.registrar(password="licoreradelbarrio")
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_si_falla_algo_no_queda_nada_a_medias(self):
        """
        Comprueba el efecto de la transacción: un registro rechazado no deja
        licoreras ni suscripciones sueltas en la base de datos.
        """
        self.registrar(password="123")
        self.assertEqual(Licorera.objects.count(), 0)
        self.assertEqual(Suscripcion.objects.count(), 0)
        self.assertEqual(Usuario.objects.count(), 0)

    def test_el_correo_se_guarda_en_minusculas(self):
        self.registrar(correo="DUENA@LaEsquina.com")
        self.assertTrue(Usuario.objects.filter(correo="duena@laesquina.com").exists())


class PlanesTests(TestCase):

    def test_catalogo_publico_muestra_los_dos_planes(self):
        respuesta = self.client.get(reverse("planes"))
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        nombres = [plan["nombre"] for plan in respuesta.json()]
        self.assertEqual(nombres, ["Básico", "Pro"])

    def test_el_plan_basico_no_incluye_facturacion(self):
        planes = {p["nombre"]: p for p in self.client.get(reverse("planes")).json()}
        self.assertFalse(planes["Básico"]["permite_facturacion"])
        self.assertTrue(planes["Pro"]["permite_facturacion"])


class LimiteDeRegistroTests(TestCase):
    """
    El registro es público, así que sin límite admitiría la creación de cuentas
    en masa (decisión D-11). Cinco por hora y origen: nadie abre cinco licorerías
    en una hora.
    """

    def setUp(self):
        cache.clear()   # el contador del límite de peticiones parte de cero
        self.url = reverse("registrar-licorera")

    def registrar(self, numero):
        return self.client.post(
            self.url,
            {
                "nombre_negocio": f"Licorera {numero}",
                "nombre_completo": "Persona de Prueba",
                "correo": f"negocio{numero}@ejemplo.com",
                "password": "ClaveSegura2026",
            },
            content_type="application/json",
        )

    def test_el_registro_se_limita_por_origen(self):
        for numero in range(5):
            self.assertEqual(self.registrar(numero).status_code, status.HTTP_201_CREATED)

        respuesta = self.registrar(99)
        self.assertEqual(respuesta.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        # Y no quedó creada a medias
        self.assertEqual(Licorera.objects.filter(nombre="Licorera 99").count(), 0)
