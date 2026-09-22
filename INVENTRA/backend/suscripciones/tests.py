"""
Pruebas del módulo de suscripciones.

Cubren el registro de licoreras (CU-SUS-01 y RF-SEG-01), el catálogo de planes,
el límite de peticiones del registro y el comando que carga las cuentas de
demostración.

Se ejecutan con `py manage.py test suscripciones`.
"""

from io import StringIO
from tempfile import TemporaryDirectory
from pathlib import Path

from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
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


@override_settings(DEBUG=True)
class DatosDeDemostracionTests(TestCase):
    """
    Comprueba el comando que carga las cuentas de demostración.

    El SENA lo va a ejecutar para poder entrar al sistema, así que tiene que
    funcionar a la primera y poder repetirse sin estropear nada.

    OJO CON `override_settings(DEBUG=True)`. Django pone DEBUG en False durante
    las pruebas, siempre, para que el código se comporte como en producción y no
    con las facilidades del modo de depuración. Como el comando se niega a correr
    fuera del modo de depuración —esa es su red de seguridad—, aquí hay que
    simular un equipo de desarrollo. La negativa se comprueba aparte, en
    `ProteccionDatosDemoTests`.
    """

    def setUp(self):
        cache.clear()   # el contador del límite de peticiones parte de cero
        self.salida = StringIO()   # el comando escribe en pantalla; aquí no estorba

    def cargar(self, *argumentos):
        call_command("cargar_datos_demo", *argumentos, stdout=self.salida)

    def test_el_comando_crea_las_cuentas(self):
        self.cargar()

        self.assertEqual(Licorera.objects.count(), 2)
        self.assertEqual(Usuario.objects.count(), 4)

        # Una licorera con plan Pro y otra con Básico, para poder comprobar
        # tanto el aislamiento como el tope de usuarios.
        planes = [licorera.plan_vigente().nombre for licorera in Licorera.objects.all()]
        self.assertIn("Pro", planes)
        self.assertIn("Básico", planes)

        # El operador de la plataforma no pertenece a ninguna licorera
        operador = Usuario.objects.get(correo="plataforma@demo.inventra.co")
        self.assertIsNone(operador.licorera)
        self.assertTrue(operador.es_administrador_inventra)

    def test_se_puede_ejecutar_dos_veces_sin_duplicar(self):
        self.cargar()
        self.cargar()

        self.assertEqual(Licorera.objects.count(), 2)
        self.assertEqual(Usuario.objects.count(), 4)

    def test_las_cuentas_sirven_para_entrar(self):
        self.cargar()

        respuesta = self.client.post(
            reverse("ingresar"),
            {"correo": "admin@demo.inventra.co", "password": "Inventra2026"},
            content_type="application/json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)

    def test_limpiar_retira_todo_lo_que_cargo(self):
        self.cargar()
        self.cargar("--limpiar")

        self.assertEqual(Licorera.objects.count(), 0)
        self.assertEqual(Usuario.objects.count(), 0)


class ProteccionDatosDemoTests(TestCase):
    """
    Comprueba la red de seguridad del comando.

    Esta clase NO lleva `override_settings(DEBUG=True)`, justamente porque
    necesita el comportamiento que Django impone durante las pruebas: DEBUG en
    False, como en un servidor publicado.
    """

    def test_se_niega_a_correr_fuera_del_modo_de_depuracion(self):
        with self.assertRaises(CommandError):
            call_command("cargar_datos_demo", stdout=StringIO())

        self.assertEqual(Licorera.objects.count(), 0)
        self.assertEqual(Usuario.objects.count(), 0)

    def test_con_la_confirmacion_expresa_si_corre(self):
        call_command("cargar_datos_demo", "--si-estoy-seguro", stdout=StringIO())
        self.assertEqual(Licorera.objects.count(), 2)


class ScriptsSqlTests(TestCase):
    """
    Comprueba el comando que genera los scripts SQL.

    Son entregables del proyecto, así que tienen que poder regenerarse en
    cualquier momento. Se escriben en una carpeta temporal para no tocar los del
    repositorio durante las pruebas.
    """

    def generar(self):
        self.carpeta = TemporaryDirectory()
        call_command(
            "generar_scripts_sql", carpeta=self.carpeta.name, stdout=StringIO()
        )
        return Path(self.carpeta.name)

    def test_genera_los_dos_archivos(self):
        carpeta = self.generar()

        self.assertTrue((carpeta / "01_estructura.sql").exists())
        self.assertTrue((carpeta / "02_carga_inicial.sql").exists())

    @staticmethod
    def sentencias(ruta):
        """
        El contenido del archivo SIN los comentarios.

        No es un detalle: la primera versión de esta prueba buscaba la palabra
        «suscripcion» en el archivo entero, y la encontraba dentro del comentario
        «-- suscripciones.0001_initial». La prueba pasaba con un archivo que no
        tenía una sola línea de SQL. Una comprobación tiene que mirar lo que
        importa, no lo que está cerca.
        """
        return "\n".join(
            linea
            for linea in ruta.read_text(encoding="utf-8").splitlines()
            if linea.strip() and not linea.strip().startswith("--")
        )

    def test_la_estructura_crea_las_tablas_del_proyecto(self):
        sql = self.sentencias(self.generar() / "01_estructura.sql")

        for tabla in ("licorera", "plan", "suscripcion", "rol", "usuario"):
            self.assertIn(f"CREATE TABLE `{tabla}`", sql)

    def test_la_estructura_trae_las_llaves_foraneas(self):
        """
        Sin las llaves foráneas el script crearía tablas sueltas, sin las
        reglas que impiden borrar una licorera con usuarios colgando.
        """
        sql = self.sentencias(self.generar() / "01_estructura.sql")

        self.assertIn("FOREIGN KEY", sql.upper())
        self.assertIn("licorera_id", sql)

    def test_la_carga_inicial_trae_los_roles_y_los_planes(self):
        contenido = self.sentencias(self.generar() / "02_carga_inicial.sql")

        self.assertIn("INSERT INTO rol", contenido)
        self.assertIn("INSERT INTO plan", contenido)
        self.assertIn("administrador_licorera", contenido)
        self.assertIn("Básico", contenido)

    def test_la_carga_inicial_no_incluye_cuentas(self):
        """
        Las cuentas de demostración tienen contraseña publicada: no pueden
        viajar en el script que se ejecuta para preparar una base nueva.
        """
        contenido = self.sentencias(self.generar() / "02_carga_inicial.sql")

        self.assertNotIn("INSERT INTO usuario", contenido)
        self.assertNotIn("demo.inventra.co", contenido)
