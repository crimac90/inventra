"""
Pruebas del módulo de seguridad.

Cubren el inicio y cierre de sesión (RF-SEG-02 y RF-SEG-03), la gestión de
usuarios (RF-SEG-01, 05, 06 y 07), el aislamiento entre licoreras y el límite
de usuarios que impone el plan contratado (RF-SUS-04).

Se ejecutan con `py manage.py test seguridad`.
"""

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from suscripciones.models import Licorera, Plan, Suscripcion

from .models import Rol, Usuario


def crear_licorera(nombre, plan_nombre="Básico"):
    """Crea un negocio con su suscripción vigente, como lo haría el registro."""
    plan = Plan.objects.get(nombre=plan_nombre)
    licorera = Licorera.objects.create(nombre=nombre, correo=f"contacto@{nombre.lower()}.com")
    Suscripcion.objects.create(
        licorera=licorera, plan=plan, estado=Suscripcion.Estado.ACTIVA,
        fecha_inicio=timezone.localdate(), precio_pactado=plan.precio_mensual,
    )
    return licorera


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
        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)

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
        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)

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



class GestionUsuariosTests(TestCase):

    CLAVE = "Licorera2026"

    def setUp(self):
        self.licorera = crear_licorera("Aurora", plan_nombre="Pro")
        self.administrador = Usuario.objects.create_user(
            correo="admin@aurora.com", nombre_completo="Administradora Aurora",
            password=self.CLAVE, licorera=self.licorera,
            rol=Rol.objects.get(nombre=Rol.ADMINISTRADOR_LICORERA),
        )
        self.url_lista = reverse("usuario-list")

    def autenticar(self, usuario):
        respuesta = self.client.post(
            reverse("ingresar"),
            {"correo": usuario.correo, "password": self.CLAVE},
            content_type="application/json",
        )
        return {"Authorization": f"Bearer {respuesta.json()['acceso']}"}

    def test_administrador_crea_un_vendedor(self):
        respuesta = self.client.post(
            self.url_lista,
            {
                "nombre_completo": "Vendedor Nuevo",
                "correo": "vendedor@aurora.com",
                "rol": Rol.objects.get(nombre=Rol.VENDEDOR).id,
                "password": self.CLAVE,
            },
            content_type="application/json",
            headers=self.autenticar(self.administrador),
        )
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)

        creado = Usuario.objects.get(correo="vendedor@aurora.com")
        self.assertEqual(creado.licorera_id, self.licorera.id)

    def test_el_vendedor_no_puede_gestionar_usuarios(self):
        vendedor = Usuario.objects.create_user(
            correo="cajero@aurora.com", nombre_completo="Cajero", password=self.CLAVE,
            licorera=self.licorera, rol=Rol.objects.get(nombre=Rol.VENDEDOR),
        )
        respuesta = self.client.get(self.url_lista, headers=self.autenticar(vendedor))
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_sin_token_no_hay_acceso(self):
        self.assertEqual(self.client.get(self.url_lista).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_una_licorera_no_ve_los_usuarios_de_otra(self):
        """Comprobación del aislamiento multiempresa."""
        otra = crear_licorera("Bolivar", plan_nombre="Pro")
        Usuario.objects.create_user(
            correo="admin@bolivar.com", nombre_completo="Administrador Bolívar",
            password=self.CLAVE, licorera=otra,
            rol=Rol.objects.get(nombre=Rol.ADMINISTRADOR_LICORERA),
        )

        respuesta = self.client.get(self.url_lista, headers=self.autenticar(self.administrador))
        correos = [u["correo"] for u in respuesta.json()["results"]]

        self.assertIn(self.administrador.correo, correos)
        self.assertNotIn("admin@bolivar.com", correos)

    def test_inactivar_no_borra_el_registro(self):
        vendedor = Usuario.objects.create_user(
            correo="temporal@aurora.com", nombre_completo="Temporal", password=self.CLAVE,
            licorera=self.licorera, rol=Rol.objects.get(nombre=Rol.VENDEDOR),
        )
        respuesta = self.client.delete(
            reverse("usuario-detail", args=[vendedor.id]),
            headers=self.autenticar(self.administrador),
        )
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)

        vendedor.refresh_from_db()
        self.assertFalse(vendedor.activo)
        self.assertTrue(Usuario.objects.filter(id=vendedor.id).exists())

    def test_no_se_puede_inactivar_la_propia_cuenta(self):
        respuesta = self.client.delete(
            reverse("usuario-detail", args=[self.administrador.id]),
            headers=self.autenticar(self.administrador),
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_se_puede_modificar_un_usuario_de_otra_licorera(self):
        otra = crear_licorera("Caldas", plan_nombre="Pro")
        ajeno = Usuario.objects.create_user(
            correo="ajeno@caldas.com", nombre_completo="Ajeno", password=self.CLAVE,
            licorera=otra, rol=Rol.objects.get(nombre=Rol.VENDEDOR),
        )
        respuesta = self.client.patch(
            reverse("usuario-detail", args=[ajeno.id]),
            {"nombre_completo": "Nombre cambiado"},
            content_type="application/json",
            headers=self.autenticar(self.administrador),
        )
        self.assertEqual(respuesta.status_code, status.HTTP_404_NOT_FOUND)


class LimitePorPlanTests(TestCase):
    """El plan contratado limita cuántos usuarios activos puede haber (RF-SUS-04)."""

    CLAVE = "Licorera2026"

    def setUp(self):
        self.licorera = crear_licorera("Basica")   # plan Básico: un solo usuario
        self.administrador = Usuario.objects.create_user(
            correo="admin@basica.com", nombre_completo="Administrador", password=self.CLAVE,
            licorera=self.licorera, rol=Rol.objects.get(nombre=Rol.ADMINISTRADOR_LICORERA),
        )
        respuesta = self.client.post(
            reverse("ingresar"),
            {"correo": self.administrador.correo, "password": self.CLAVE},
            content_type="application/json",
        )
        self.cabecera = {"Authorization": f"Bearer {respuesta.json()['acceso']}"}

    def test_el_plan_basico_no_admite_un_segundo_usuario(self):
        respuesta = self.client.post(
            reverse("usuario-list"),
            {
                "nombre_completo": "Segundo Usuario",
                "correo": "segundo@basica.com",
                "rol": Rol.objects.get(nombre=Rol.VENDEDOR).id,
                "password": self.CLAVE,
            },
            content_type="application/json",
            headers=self.cabecera,
        )
        self.assertEqual(respuesta.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("Básico", respuesta.json()["detalle"])
