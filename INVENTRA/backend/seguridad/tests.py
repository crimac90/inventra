"""
Pruebas del inicio y cierre de sesión (RF-SEG-02 y RF-SEG-03).

Cada prueba comprueba un comportamiento concreto de la especificación. Se
ejecutan con `py manage.py test seguridad`.
"""

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from .models import Rol, Usuario


class AutenticacionTests(TestCase):
    """Comprueba el ingreso al sistema en sus distintos escenarios."""

    CONTRASENA = "ClaveSegura2026"

    def setUp(self):
        """Prepara un usuario válido antes de cada prueba."""
        self.rol = Rol.objects.get(nombre=Rol.ADMINISTRADOR_LICORERA)
        self.usuario = Usuario.objects.create_user(
            correo="vendedor@licorera.com",
            nombre_completo="Usuario de prueba",
            password=self.CONTRASENA,
            rol=self.rol,
        )
        self.url_ingresar = reverse("ingresar")

    def ingresar(self, correo=None, contrasena=None):
        return self.client.post(
            self.url_ingresar,
            {"correo": correo or self.usuario.correo, "password": contrasena or self.CONTRASENA},
            content_type="application/json",
        )

    def test_ingreso_correcto_entrega_tokens(self):
        respuesta = self.ingresar()
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertIn("acceso", respuesta.json())
        self.assertIn("refresco", respuesta.json())
        self.assertEqual(respuesta.json()["usuario"]["correo"], self.usuario.correo)

    def test_contrasena_incorrecta_suma_un_intento(self):
        self.ingresar(contrasena="claveEquivocada")
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.intentos_fallidos, 1)

    def test_mensaje_no_revela_si_el_correo_existe(self):
        """El mensaje debe ser el mismo para un correo inexistente y para una clave errada."""
        sin_cuenta = self.ingresar(correo="nadie@ejemplo.com", contrasena="loquesea")
        clave_mala = self.ingresar(contrasena="claveEquivocada")
        self.assertEqual(sin_cuenta.json(), clave_mala.json())

    def test_cinco_intentos_fallidos_bloquean_la_cuenta(self):
        for _ in range(Usuario.MAXIMO_INTENTOS):
            self.ingresar(contrasena="claveEquivocada")

        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.esta_bloqueado())

        # Aun con la contraseña correcta, el ingreso se rechaza durante el bloqueo
        respuesta = self.ingresar()
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_ingreso_correcto_limpia_los_intentos(self):
        self.ingresar(contrasena="claveEquivocada")
        self.ingresar()
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.intentos_fallidos, 0)
        self.assertIsNotNone(self.usuario.last_login)

    def test_cuenta_inactiva_no_puede_ingresar(self):
        self.usuario.activo = False
        self.usuario.save(update_fields=["activo"])
        respuesta = self.ingresar()
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_la_contrasena_no_se_guarda_en_texto_plano(self):
        self.usuario.refresh_from_db()
        self.assertNotEqual(self.usuario.password, self.CONTRASENA)
        self.assertTrue(self.usuario.check_password(self.CONTRASENA))


class SesionTests(TestCase):
    """Comprueba el perfil y el cierre de sesión."""

    CONTRASENA = "ClaveSegura2026"

    def setUp(self):
        self.usuario = Usuario.objects.create_user(
            correo="admin@licorera.com",
            nombre_completo="Administrador de prueba",
            password=self.CONTRASENA,
            rol=Rol.objects.get(nombre=Rol.ADMINISTRADOR_LICORERA),
        )
        respuesta = self.client.post(
            reverse("ingresar"),
            {"correo": self.usuario.correo, "password": self.CONTRASENA},
            content_type="application/json",
        )
        self.acceso = respuesta.json()["acceso"]
        self.refresco = respuesta.json()["refresco"]

    def test_perfil_exige_token(self):
        respuesta = self.client.get(reverse("perfil"))
        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_perfil_devuelve_al_usuario_de_la_sesion(self):
        respuesta = self.client.get(
            reverse("perfil"), headers={"Authorization": f"Bearer {self.acceso}"}
        )
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(respuesta.json()["correo"], self.usuario.correo)

    def test_cierre_de_sesion_invalida_el_token_de_refresco(self):
        cierre = self.client.post(
            reverse("salir"),
            {"refresco": self.refresco},
            content_type="application/json",
            headers={"Authorization": f"Bearer {self.acceso}"},
        )
        self.assertEqual(cierre.status_code, status.HTTP_200_OK)

        # Con el token ya invalidado, la renovación debe fallar
        renovacion = self.client.post(
            reverse("renovar"), {"refresh": self.refresco}, content_type="application/json"
        )
        self.assertEqual(renovacion.status_code, status.HTTP_401_UNAUTHORIZED)
