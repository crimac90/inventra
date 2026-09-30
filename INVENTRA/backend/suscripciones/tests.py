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

from datetime import timedelta

from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from seguridad.models import Rol, Usuario

from .models import Licorera, Plan, Suscripcion


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
        # La prueba corre sobre el plan Pro: el manual promete «todas las
        # funciones disponibles» durante los quince días.
        self.assertEqual(suscripcion.plan.nombre, "Pro")
        self.assertEqual(suscripcion.estado, Suscripcion.Estado.EN_PRUEBA)

    def test_la_prueba_no_se_cobra(self):
        """
        El precio pactado de la prueba es cero, no el del plan.

        El precio se congela el día que se contrata, en la fila que abra ese
        contrato (RF-SUS-02). Copiar aquí el precio del Pro diría que el negocio
        debe 109.900 pesos por unos días que son gratis.
        """
        self.registrar()
        suscripcion = Suscripcion.objects.get()
        self.assertEqual(suscripcion.precio_pactado, 0)

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


class SuscripcionVigenteTests(TestCase):
    """
    Qué suscripción manda hoy (RF-SUS-03).

    POR QUÉ EXISTE ESTA CLASE
    El 27/09/2026 se añadió el estado «en prueba» y se cambió la consulta que
    decide cuál es la suscripción vigente. Las 64 pruebas de entonces siguieron
    pasando, pero eso no probaba nada: ninguna creaba una suscripción en prueba ni
    ponía una fecha de fin, así que ninguna ejecutaba la línea que había cambiado.
    Es el mismo caso del 400 frente al 401 del módulo SEG: unas pruebas que pasan
    solo dicen que no se rompió lo que ya miraban.
    """

    def setUp(self):
        self.licorera = Licorera.objects.create(
            nombre="Licorera de prueba", correo="contacto@prueba.com")
        self.plan_basico = Plan.objects.get(nombre="Básico")
        self.plan_pro = Plan.objects.get(nombre="Pro")
        self.hoy = timezone.localdate()

    def crear(self, estado, dias_hasta_el_fin=None, plan=None, dias_desde_el_inicio=0):
        """Crea una suscripción con el estado y la vigencia que pida la prueba."""
        return Suscripcion.objects.create(
            licorera=self.licorera,
            plan=plan or self.plan_basico,
            estado=estado,
            fecha_inicio=self.hoy - timedelta(days=dias_desde_el_inicio),
            fecha_fin=(None if dias_hasta_el_fin is None
                       else self.hoy + timedelta(days=dias_hasta_el_fin)),
            precio_pactado=(plan or self.plan_basico).precio_mensual,
        )

    def test_una_prueba_vigente_es_la_suscripcion_que_manda(self):
        suscripcion = self.crear(Suscripcion.Estado.EN_PRUEBA, dias_hasta_el_fin=15)
        self.assertEqual(self.licorera.suscripcion_vigente(), suscripcion)
        self.assertEqual(self.licorera.plan_vigente(), self.plan_basico)

    def test_una_prueba_vencida_ayer_ya_no_vale(self):
        self.crear(Suscripcion.Estado.EN_PRUEBA, dias_hasta_el_fin=-1)
        self.assertIsNone(self.licorera.suscripcion_vigente())
        self.assertIsNone(self.licorera.plan_vigente())

    def test_una_prueba_que_termina_hoy_todavia_vale(self):
        """El último día de la prueba es un día completo, no medio día."""
        suscripcion = self.crear(Suscripcion.Estado.EN_PRUEBA, dias_hasta_el_fin=0)
        self.assertEqual(self.licorera.suscripcion_vigente(), suscripcion)

    def test_una_suscripcion_contratada_sin_fecha_de_fin_sigue_vigente(self):
        """Comprobación de que el cambio no rompió el caso que ya funcionaba."""
        suscripcion = self.crear(Suscripcion.Estado.ACTIVA)
        self.assertEqual(self.licorera.suscripcion_vigente(), suscripcion)

    def test_una_cuenta_en_mora_sigue_operando(self):
        suscripcion = self.crear(Suscripcion.Estado.EN_MORA)
        self.assertEqual(self.licorera.suscripcion_vigente(), suscripcion)

    def test_una_suspendida_no_manda_aunque_no_tenga_fecha_de_fin(self):
        """Suspendida deja consultar, pero no define un plan con el que operar."""
        self.crear(Suscripcion.Estado.SUSPENDIDA)
        self.assertIsNone(self.licorera.suscripcion_vigente())

    def test_una_cancelada_no_manda(self):
        self.crear(Suscripcion.Estado.CANCELADA)
        self.assertIsNone(self.licorera.suscripcion_vigente())

    def test_una_fila_historica_cerrada_no_desplaza_a_la_nueva(self):
        """
        Al cambiar de plan se cierra la fila anterior y se abre otra. La consulta
        debe devolver la nueva, no la vieja, aunque la vieja siga en estado activa.
        """
        self.crear(Suscripcion.Estado.ACTIVA, dias_hasta_el_fin=-30,
                   dias_desde_el_inicio=60)
        nueva = self.crear(Suscripcion.Estado.ACTIVA, plan=self.plan_pro)
        self.assertEqual(self.licorera.suscripcion_vigente(), nueva)
        self.assertEqual(self.licorera.plan_vigente(), self.plan_pro)

    def test_el_tope_de_usuarios_se_aplica_tambien_durante_la_prueba(self):
        """
        Una prueba no es una barra libre: entrega el plan Básico, con su tope de
        un usuario. Si esto fallara, quince días bastarían para saltarse el límite.
        """
        self.crear(Suscripcion.Estado.EN_PRUEBA, dias_hasta_el_fin=15)
        rol = Rol.objects.get(nombre=Rol.ADMINISTRADOR_LICORERA)
        Usuario.objects.create_user(
            correo="dueno@prueba.com", nombre_completo="Dueño",
            password="Licorera2026", licorera=self.licorera, rol=rol)
        self.assertFalse(self.licorera.puede_agregar_usuario())

    def test_sin_ninguna_suscripcion_no_hay_plan(self):
        self.assertIsNone(self.licorera.suscripcion_vigente())
        self.assertIsNone(self.licorera.plan_vigente())


class PeriodoDePruebaTests(TestCase):
    """
    Comprueba la prueba gratuita de quince días (RF-SUS-01 y RF-SUS-03).

    Lo que se vigila aquí es el borde del calendario, que es donde estas cosas
    fallan: el primer día, el último día y el día siguiente. Los tres se
    comprueban moviendo la fecha de fin de la suscripción, no esperando quince
    días.
    """

    DATOS = {
        "nombre_negocio": "Licorera de Prueba",
        "nombre_completo": "Dueña de Prueba",
        "correo": "duena@prueba.com",
        "password": "Licorera2026",
    }

    def setUp(self):
        cache.clear()
        self.client.post(reverse("registrar-licorera"), self.DATOS,
                         content_type="application/json")
        self.licorera = Licorera.objects.get(nombre=self.DATOS["nombre_negocio"])
        self.suscripcion = Suscripcion.objects.get(licorera=self.licorera)
        self.url = reverse("mi-suscripcion")

    def entrar(self):
        respuesta = self.client.post(
            reverse("ingresar"),
            {"correo": self.DATOS["correo"], "password": self.DATOS["password"]},
            content_type="application/json",
        )
        return respuesta.json()["acceso"]

    def consultar(self):
        return self.client.get(self.url, HTTP_AUTHORIZATION=f"Bearer {self.entrar()}")

    # --- cómo nace ---

    def test_la_prueba_dura_quince_dias(self):
        self.assertEqual(self.suscripcion.fecha_inicio, timezone.localdate())
        self.assertEqual(
            self.suscripcion.fecha_fin,
            timezone.localdate() + timedelta(days=Suscripcion.DIAS_DE_PRUEBA),
        )

    def test_la_prueba_habilita_todas_las_funciones(self):
        """Con el plan Pro, el negocio puede crear más de un usuario durante la prueba."""
        plan = self.licorera.plan_vigente()
        self.assertEqual(plan.nombre, "Pro")
        self.assertIsNone(plan.maximo_usuarios)
        self.assertTrue(self.licorera.puede_agregar_usuario())

    # --- el borde del calendario ---

    def test_recien_registrada_quedan_quince_dias(self):
        self.assertEqual(self.suscripcion.dias_restantes(), Suscripcion.DIAS_DE_PRUEBA)
        self.assertTrue(self.suscripcion.esta_vigente())

    def test_el_ultimo_dia_quedan_cero_dias_y_todavia_opera(self):
        self.suscripcion.fecha_fin = timezone.localdate()
        self.suscripcion.save(update_fields=["fecha_fin"])
        self.assertEqual(self.suscripcion.dias_restantes(), 0)
        self.assertTrue(self.suscripcion.esta_vigente())
        self.assertIsNotNone(self.licorera.suscripcion_vigente())

    def test_al_dia_siguiente_deja_de_estar_vigente(self):
        self.suscripcion.fecha_fin = timezone.localdate() - timedelta(days=1)
        self.suscripcion.save(update_fields=["fecha_fin"])
        self.assertEqual(self.suscripcion.dias_restantes(), 0)
        self.assertFalse(self.suscripcion.esta_vigente())
        self.assertIsNone(self.licorera.suscripcion_vigente())

    def test_una_suscripcion_sin_fecha_de_fin_no_cuenta_dias(self):
        self.suscripcion.fecha_fin = None
        self.suscripcion.estado = Suscripcion.Estado.ACTIVA
        self.suscripcion.save(update_fields=["fecha_fin", "estado"])
        self.assertIsNone(self.suscripcion.dias_restantes())
        self.assertTrue(self.suscripcion.esta_vigente())

    def test_un_estado_no_operativo_no_esta_vigente_aunque_falten_dias(self):
        self.suscripcion.estado = Suscripcion.Estado.SUSPENDIDA
        self.suscripcion.save(update_fields=["estado"])
        self.assertFalse(self.suscripcion.esta_vigente())
        self.assertGreater(self.suscripcion.dias_restantes(), 0)

    # --- lo que ve el frontend ---

    def test_la_consulta_devuelve_el_estado_de_la_prueba(self):
        datos = self.consultar().json()
        self.assertEqual(datos["plan"], "Pro")
        self.assertEqual(datos["estado"], Suscripcion.Estado.EN_PRUEBA)
        self.assertTrue(datos["es_prueba"])
        self.assertEqual(datos["dias_restantes"], Suscripcion.DIAS_DE_PRUEBA)
        self.assertTrue(datos["puede_operar"])

    def test_la_consulta_exige_sesion(self):
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_sin_suscripcion_vigente_avisa_que_no_puede_operar(self):
        self.suscripcion.estado = Suscripcion.Estado.SUSPENDIDA
        self.suscripcion.save(update_fields=["estado"])
        datos = self.consultar().json()
        self.assertFalse(datos["puede_operar"])
        self.assertIsNone(datos["plan"])

    def test_cada_licorera_ve_su_propia_suscripcion(self):
        """El identificador no viaja en la dirección: se toma de la sesión."""
        otra = Licorera.objects.create(nombre="Otra Licorera", correo="otra@licorera.com")
        Suscripcion.objects.create(
            licorera=otra, plan=Plan.objects.get(nombre="Básico"),
            estado=Suscripcion.Estado.ACTIVA, fecha_inicio=timezone.localdate(),
            precio_pactado=Plan.objects.get(nombre="Básico").precio_mensual,
        )
        datos = self.consultar().json()
        self.assertEqual(datos["plan"], "Pro")   # la suya, no la de la otra
