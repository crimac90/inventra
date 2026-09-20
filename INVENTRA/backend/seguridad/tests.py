"""
Pruebas del módulo de seguridad.

Cubren el inicio y cierre de sesión (RF-SEG-02 y RF-SEG-03), la recuperación de
contraseña (RF-SEG-04), la gestión de usuarios y el perfil propio (RF-SEG-01, 05,
06 y 07), el aislamiento entre licoreras y el límite de usuarios que impone el
plan contratado (RF-SUS-04).

Se ejecutan con `py manage.py test seguridad`.
"""

from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
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
        cache.clear()   # el contador del límite de peticiones parte de cero
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
        cache.clear()   # el contador del límite de peticiones parte de cero
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
        cache.clear()   # el contador del límite de peticiones parte de cero
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
        cache.clear()   # el contador del límite de peticiones parte de cero
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


class RecuperacionContrasenaTests(TestCase):
    """
    Comprueba el restablecimiento de contraseña (RF-SEG-04).

    Durante las pruebas Django no envía los correos: los guarda en una lista en
    memoria, `mail.outbox`, que se vacía antes de cada prueba. Por eso se puede
    comprobar que el mensaje salió y leer su contenido sin necesitar un servidor
    de correo.
    """

    CONTRASENA = "ClaveSegura2026"
    NUEVA = "OtraClave2026"

    def setUp(self):
        cache.clear()   # el contador del límite de peticiones parte de cero
        self.licorera = crear_licorera("Recuperacion")
        self.usuario = Usuario.objects.create_user(
            correo="olvidadizo@licorera.com",
            nombre_completo="Usuario Olvidadizo",
            password=self.CONTRASENA,
            licorera=self.licorera,
            rol=Rol.objects.get(nombre=Rol.ADMINISTRADOR_LICORERA),
        )
        self.url_recuperar = reverse("recuperar")
        self.url_restablecer = reverse("restablecer")

    def solicitar(self, correo=None):
        return self.client.post(
            self.url_recuperar,
            {"correo": correo or self.usuario.correo},
            content_type="application/json",
        )

    def datos_del_enlace(self, usuario=None):
        """Reproduce los dos valores que el correo lleva en la dirección."""
        usuario = usuario or self.usuario
        return {
            "uid": urlsafe_base64_encode(force_bytes(usuario.pk)),
            "token": default_token_generator.make_token(usuario),
        }

    def restablecer(self, contrasena=None, **cambios):
        datos = self.datos_del_enlace()
        datos["password"] = contrasena or self.NUEVA
        datos.update(cambios)
        return self.client.post(self.url_restablecer, datos, content_type="application/json")

    def test_solicitud_envia_el_correo_con_el_enlace(self):
        respuesta = self.solicitar()
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.usuario.correo])
        self.assertIn("restablecer-contrasena", mail.outbox[0].body)

    def test_correo_desconocido_responde_igual_y_no_envia_nada(self):
        """El mensaje es el mismo, para no revelar qué cuentas existen."""
        conocido = self.solicitar()
        mail.outbox.clear()
        desconocido = self.solicitar(correo="nadie@ejemplo.com")

        self.assertEqual(desconocido.status_code, status.HTTP_200_OK)
        self.assertEqual(desconocido.json(), conocido.json())
        self.assertEqual(len(mail.outbox), 0)

    def test_cuenta_inactiva_no_recibe_enlace(self):
        self.usuario.activo = False
        self.usuario.save(update_fields=["activo"])
        respuesta = self.solicitar()
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 0)

    def test_enlace_valido_cambia_la_contrasena(self):
        respuesta = self.restablecer()
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)

        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password(self.NUEVA))
        self.assertFalse(self.usuario.check_password(self.CONTRASENA))

    def test_el_enlace_solo_sirve_una_vez(self):
        datos = self.datos_del_enlace()

        primera = self.client.post(
            self.url_restablecer, dict(datos, password=self.NUEVA), content_type="application/json"
        )
        segunda = self.client.post(
            self.url_restablecer, dict(datos, password="TerceraClave2026"), content_type="application/json"
        )

        self.assertEqual(primera.status_code, status.HTTP_200_OK)
        self.assertEqual(segunda.status_code, status.HTTP_400_BAD_REQUEST)

        # La segunda no tuvo efecto: sigue valiendo la contraseña de la primera
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password(self.NUEVA))

    def test_token_manipulado_se_rechaza(self):
        respuesta = self.restablecer(token="token-inventado")
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password(self.CONTRASENA))

    def test_identificador_manipulado_se_rechaza(self):
        respuesta = self.restablecer(uid="XYZ")
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_la_contrasena_nueva_cumple_la_politica(self):
        respuesta = self.restablecer(contrasena="12345678")
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password(self.CONTRASENA))

    def test_restablecer_libera_el_bloqueo_por_intentos(self):
        """Quien olvidó la contraseña y agotó los intentos debe poder volver a entrar."""
        for _ in range(Usuario.MAXIMO_INTENTOS):
            self.client.post(
                reverse("ingresar"),
                {"correo": self.usuario.correo, "password": "claveEquivocada"},
                content_type="application/json",
            )
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.esta_bloqueado())

        self.restablecer()

        self.usuario.refresh_from_db()
        self.assertFalse(self.usuario.esta_bloqueado())
        self.assertEqual(self.usuario.intentos_fallidos, 0)

    def test_se_puede_ingresar_con_la_contrasena_nueva(self):
        self.restablecer()
        respuesta = self.client.post(
            reverse("ingresar"),
            {"correo": self.usuario.correo, "password": self.NUEVA},
            content_type="application/json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)


class PerfilPropioTests(TestCase):
    """Comprueba la edición del perfil y el cambio de contraseña (RF-SEG-06)."""

    CONTRASENA = "ClaveSegura2026"
    NUEVA = "OtraClave2026"

    def setUp(self):
        cache.clear()   # el contador del límite de peticiones parte de cero
        self.licorera = crear_licorera("Perfil")
        self.usuario = Usuario.objects.create_user(
            correo="vendedor@perfil.com",
            nombre_completo="Nombre Inicial",
            password=self.CONTRASENA,
            licorera=self.licorera,
            rol=Rol.objects.get(nombre=Rol.VENDEDOR),
        )
        respuesta = self.client.post(
            reverse("ingresar"),
            {"correo": self.usuario.correo, "password": self.CONTRASENA},
            content_type="application/json",
        )
        self.cabecera = {"HTTP_AUTHORIZATION": f"Bearer {respuesta.json()['acceso']}"}

    def test_el_usuario_corrige_su_nombre_y_telefono(self):
        respuesta = self.client.patch(
            reverse("perfil"),
            {"nombre_completo": "Nombre Corregido", "telefono": "3001234567"},
            content_type="application/json",
            **self.cabecera,
        )
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)

        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.nombre_completo, "Nombre Corregido")
        self.assertEqual(self.usuario.telefono, "3001234567")

    def test_el_usuario_no_puede_cambiarse_el_correo_ni_el_rol(self):
        """Los campos que no admite el serializador se descartan en silencio."""
        administrador = Rol.objects.get(nombre=Rol.ADMINISTRADOR_LICORERA)
        self.client.patch(
            reverse("perfil"),
            {"correo": "otro@perfil.com", "rol": administrador.id, "activo": False},
            content_type="application/json",
            **self.cabecera,
        )

        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.correo, "vendedor@perfil.com")
        self.assertEqual(self.usuario.rol.nombre, Rol.VENDEDOR)
        self.assertTrue(self.usuario.activo)

    def test_cambio_de_contrasena_exige_la_actual(self):
        respuesta = self.client.post(
            reverse("cambiar-contrasena"),
            {"contrasena_actual": "claveEquivocada", "contrasena_nueva": self.NUEVA},
            content_type="application/json",
            **self.cabecera,
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password(self.CONTRASENA))

    def test_cambio_de_contrasena_correcto(self):
        respuesta = self.client.post(
            reverse("cambiar-contrasena"),
            {"contrasena_actual": self.CONTRASENA, "contrasena_nueva": self.NUEVA},
            content_type="application/json",
            **self.cabecera,
        )
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password(self.NUEVA))

    def test_la_contrasena_nueva_debe_ser_distinta(self):
        respuesta = self.client.post(
            reverse("cambiar-contrasena"),
            {"contrasena_actual": self.CONTRASENA, "contrasena_nueva": self.CONTRASENA},
            content_type="application/json",
            **self.cabecera,
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_el_perfil_no_se_edita_sin_token(self):
        respuesta = self.client.patch(
            reverse("perfil"),
            {"nombre_completo": "Intruso"},
            content_type="application/json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)


class LimiteDePeticionesTests(TestCase):
    """
    Comprueba el límite de peticiones por origen (decisión D-11).

    Conviene tener clara la diferencia con el bloqueo de RF-SEG-02, porque
    parecen lo mismo y protegen de cosas distintas:

    | Defensa | Cuenta por | De qué protege |
    |---|---|---|
    | Bloqueo de cinco intentos | Cuenta | Insistir contra UNA cuenta |
    | Límite de peticiones | Origen | Probar una contraseña contra MUCHAS cuentas |

    El segundo ataque se llama «password spraying» y el bloqueo por cuenta no lo
    ve: si se prueban tres contraseñas contra mil correos, ninguna cuenta llega a
    cinco fallos y ninguna se bloquea.
    """

    CONTRASENA = "ClaveSegura2026"

    def setUp(self):
        cache.clear()   # el contador del límite de peticiones parte de cero
        self.rol = Rol.objects.get(nombre=Rol.ADMINISTRADOR_LICORERA)
        self.url_ingresar = reverse("ingresar")

    def crear(self, numero):
        return Usuario.objects.create_user(
            correo=f"usuario{numero}@licorera.com",
            nombre_completo=f"Usuario {numero}",
            password=self.CONTRASENA,
            rol=self.rol,
        )

    def intentar(self, correo):
        return self.client.post(
            self.url_ingresar,
            {"correo": correo, "password": "claveEquivocada"},
            content_type="application/json",
        )

    def test_el_ingreso_se_limita_por_origen(self):
        """Veinte intentos pasan; el veintiuno recibe 429."""
        for _ in range(20):
            self.intentar("cualquiera@ejemplo.com")

        respuesta = self.intentar("cualquiera@ejemplo.com")
        self.assertEqual(respuesta.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_el_limite_es_por_origen_y_no_por_cuenta(self):
        """
        Siete cuentas, tres intentos cada una: ninguna llega a los cinco fallos
        que exige el bloqueo, así que ninguna queda bloqueada. Aun así, la
        petición número veintiuno se corta por origen.
        """
        usuarios = [self.crear(n) for n in range(7)]

        codigos = []
        for usuario in usuarios:
            for _ in range(3):
                codigos.append(self.intentar(usuario.correo).status_code)

        # Las veinte primeras llegan al servidor y se rechazan por credenciales
        self.assertEqual(codigos[:20], [status.HTTP_401_UNAUTHORIZED] * 20)
        # La veintiuna ni siquiera llega a comprobar la contraseña
        self.assertEqual(codigos[20], status.HTTP_429_TOO_MANY_REQUESTS)

        # Y, en efecto, el bloqueo por cuenta no habría detenido nada de esto
        for usuario in usuarios:
            usuario.refresh_from_db()
            self.assertFalse(usuario.esta_bloqueado())

    def test_la_recuperacion_se_limita_por_origen(self):
        """Cinco solicitudes pasan; la sexta recibe 429."""
        url = reverse("recuperar")
        for _ in range(5):
            self.client.post(
                url, {"correo": "alguien@ejemplo.com"}, content_type="application/json"
            )

        respuesta = self.client.post(
            url, {"correo": "alguien@ejemplo.com"}, content_type="application/json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_las_direcciones_sin_ambito_no_se_limitan(self):
        """
        El límite se declara «con ámbito»: solo afecta a las vistas que lo
        piden. El catálogo de planes no lo pide, así que aguanta las peticiones
        que hagan falta.
        """
        url = reverse("planes")
        for _ in range(30):
            respuesta = self.client.get(url)
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
