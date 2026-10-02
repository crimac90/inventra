"""
Pruebas del módulo de suscripciones.

Cubren el registro de licoreras (CU-SUS-01 y RF-SEG-01), el catálogo de planes,
el límite de peticiones del registro, el comando que carga las cuentas de
demostración y el ciclo de estados de la suscripción (RF-SUS-03).

Se ejecutan con `py manage.py test suscripciones`.
"""

from io import StringIO
from tempfile import TemporaryDirectory
from pathlib import Path

from datetime import timedelta

from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from seguridad.models import Rol, Usuario

from .models import Licorera, Plan, Suscripcion
from .cambio_de_plan import abrir_periodo, corregir_vencimiento, es_bajada, excesos
from .correo import enviar_correo_vencimiento
from .modulos import MODULOS
from .permissions import PuedeRegistrarOperaciones


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


class EstadoPorFechaTests(TestCase):
    """
    El escalón entre vencer y quedar suspendido (RF-SUS-03, decisión D-25).

    POR QUÉ ESTA CLASE MIRA DÍA A DÍA
    Lo que se construyó no es «vencida sí o no», son cuatro días en los que la
    cuenta está vencida y sigue trabajando. Una prueba que solo comprobara
    «antes» y «mucho después» pasaría sin ejecutar nunca la rama de la mora, que
    es la única línea nueva. Se comprueban los dos bordes: el primer día de
    gracia y el primero sin ella.
    """

    def setUp(self):
        self.licorera = Licorera.objects.create(
            nombre="Licorera de prueba", correo="contacto@prueba.com")
        self.plan = Plan.objects.get(nombre="Básico")
        self.hoy = timezone.localdate()

    def crear(self, estado, vencida_hace=None, precio=None):
        """`vencida_hace` en días: 0 es «vence hoy», 3 es «venció hace tres días»."""
        return Suscripcion.objects.create(
            licorera=self.licorera,
            plan=self.plan,
            estado=estado,
            fecha_inicio=self.hoy - timedelta(days=60),
            fecha_fin=(None if vencida_hace is None
                       else self.hoy - timedelta(days=vencida_hace)),
            precio_pactado=self.plan.precio_mensual if precio is None else precio,
        )

    # --- dentro de la vigencia ---

    def test_con_la_fecha_por_delante_conserva_su_estado(self):
        suscripcion = self.crear(Suscripcion.Estado.ACTIVA, vencida_hace=-10)
        self.assertEqual(suscripcion.estado_por_fecha(), Suscripcion.Estado.ACTIVA)
        self.assertTrue(suscripcion.esta_vigente())

    def test_el_dia_del_vencimiento_todavia_esta_activa(self):
        """La fecha de fin es el último día completo, no el primero sin servicio."""
        suscripcion = self.crear(Suscripcion.Estado.ACTIVA, vencida_hace=0)
        self.assertEqual(suscripcion.estado_por_fecha(), Suscripcion.Estado.ACTIVA)
        self.assertTrue(suscripcion.esta_vigente())

    # --- los cuatro días de gracia ---

    def test_al_dia_siguiente_entra_en_mora_y_sigue_operando(self):
        suscripcion = self.crear(Suscripcion.Estado.ACTIVA, vencida_hace=1)
        self.assertEqual(suscripcion.estado_por_fecha(), Suscripcion.Estado.EN_MORA)
        self.assertTrue(suscripcion.esta_vigente())

    def test_el_ultimo_dia_de_gracia_sigue_en_mora(self):
        suscripcion = self.crear(Suscripcion.Estado.ACTIVA,
                                 vencida_hace=Suscripcion.DIAS_DE_GRACIA)
        self.assertEqual(suscripcion.estado_por_fecha(), Suscripcion.Estado.EN_MORA)
        self.assertTrue(suscripcion.esta_vigente())

    def test_pasada_la_gracia_queda_suspendida(self):
        suscripcion = self.crear(Suscripcion.Estado.ACTIVA,
                                 vencida_hace=Suscripcion.DIAS_DE_GRACIA + 1)
        self.assertEqual(suscripcion.estado_por_fecha(), Suscripcion.Estado.SUSPENDIDA)
        self.assertFalse(suscripcion.esta_vigente())

    def test_los_dias_para_la_suspension_se_cuentan_desde_el_vencimiento(self):
        suscripcion = self.crear(Suscripcion.Estado.ACTIVA, vencida_hace=1)
        self.assertEqual(suscripcion.dias_para_suspension(), Suscripcion.DIAS_DE_GRACIA)
        vigente = self.crear(Suscripcion.Estado.ACTIVA, vencida_hace=-5)
        self.assertIsNone(vigente.dias_para_suspension())

    # --- la prueba no tiene gracia ---

    def test_la_prueba_vencida_pasa_directa_a_suspendida(self):
        suscripcion = self.crear(Suscripcion.Estado.EN_PRUEBA, vencida_hace=1, precio=0)
        self.assertEqual(suscripcion.estado_por_fecha(), Suscripcion.Estado.SUSPENDIDA)
        self.assertFalse(suscripcion.esta_vigente())

    def test_una_prueba_se_reconoce_por_el_precio_cuando_ya_no_lo_dice_su_estado(self):
        """
        Una vez la orden diaria la marca como suspendida, el estado deja de decir
        que fue una prueba. Si la gracia dependiera del estado, esa fila volvería
        a entrar en mora y el negocio ganaría cuatro días que nunca pagó.
        """
        suscripcion = self.crear(Suscripcion.Estado.SUSPENDIDA, vencida_hace=1, precio=0)
        self.assertTrue(suscripcion.es_periodo_gratuito)
        self.assertEqual(suscripcion.estado_por_fecha(), Suscripcion.Estado.SUSPENDIDA)

    # --- los casos que ninguna fecha cambia ---

    def test_una_cancelada_no_vuelve_por_ninguna_fecha(self):
        suscripcion = self.crear(Suscripcion.Estado.CANCELADA, vencida_hace=-30)
        self.assertEqual(suscripcion.estado_por_fecha(), Suscripcion.Estado.CANCELADA)
        self.assertFalse(suscripcion.esta_vigente())

    def test_sin_fecha_de_fin_conserva_su_estado(self):
        suscripcion = self.crear(Suscripcion.Estado.ACTIVA)
        self.assertEqual(suscripcion.estado_por_fecha(), Suscripcion.Estado.ACTIVA)
        self.assertTrue(suscripcion.esta_vigente())

    # --- lo que devuelve la consulta de la licorera ---

    def test_la_suscripcion_actual_aparece_aunque_este_suspendida(self):
        suscripcion = self.crear(Suscripcion.Estado.SUSPENDIDA, vencida_hace=30)
        self.assertEqual(self.licorera.suscripcion_actual(), suscripcion)
        self.assertIsNone(self.licorera.suscripcion_vigente())

    def test_una_cuenta_en_mora_manda_aunque_su_fecha_haya_pasado(self):
        """
        Es el caso que la consulta anterior no podía devolver: filtraba por fecha
        no pasada, y una cuenta en mora tiene la fecha pasada por definición.
        """
        suscripcion = self.crear(Suscripcion.Estado.ACTIVA, vencida_hace=2)
        self.assertEqual(self.licorera.suscripcion_vigente(), suscripcion)

    def test_la_cancelada_no_es_la_suscripcion_actual(self):
        self.crear(Suscripcion.Estado.CANCELADA, vencida_hace=10)
        self.assertIsNone(self.licorera.suscripcion_actual())


class OrdenDeEstadosTests(TestCase):
    """
    La orden que copia el estado calculado a la columna (decisión D-25).

    Se comprueba sobre todo lo que la orden NO debe hacer, que es donde está el
    riesgo: retroceder, tocar la fecha o revivir una cancelada.
    """

    def setUp(self):
        self.licorera = Licorera.objects.create(
            nombre="Licorera de prueba", correo="contacto@prueba.com")
        self.plan = Plan.objects.get(nombre="Básico")
        self.hoy = timezone.localdate()

    def crear(self, estado, vencida_hace, precio=None):
        return Suscripcion.objects.create(
            licorera=self.licorera, plan=self.plan, estado=estado,
            fecha_inicio=self.hoy - timedelta(days=60),
            fecha_fin=self.hoy - timedelta(days=vencida_hace),
            precio_pactado=self.plan.precio_mensual if precio is None else precio,
        )

    def correr(self, *argumentos):
        salida = StringIO()
        call_command("actualizar_estados_suscripciones", *argumentos, stdout=salida)
        return salida.getvalue()

    def test_una_activa_recien_vencida_pasa_a_mora(self):
        suscripcion = self.crear(Suscripcion.Estado.ACTIVA, vencida_hace=1)
        self.correr()
        suscripcion.refresh_from_db()
        self.assertEqual(suscripcion.estado, Suscripcion.Estado.EN_MORA)

    def test_pasada_la_gracia_la_orden_la_suspende(self):
        suscripcion = self.crear(Suscripcion.Estado.EN_MORA,
                                 vencida_hace=Suscripcion.DIAS_DE_GRACIA + 1)
        self.correr()
        suscripcion.refresh_from_db()
        self.assertEqual(suscripcion.estado, Suscripcion.Estado.SUSPENDIDA)

    def test_no_retrocede_una_suspendida_cuya_fecha_se_amplio(self):
        """
        Renovar abre una fila nueva; la vieja se queda como está. Si la orden
        pudiera retroceder, ampliar una fecha por error resucitaría una cuenta
        que alguien suspendió a conciencia.
        """
        suscripcion = self.crear(Suscripcion.Estado.SUSPENDIDA, vencida_hace=-30)
        self.correr()
        suscripcion.refresh_from_db()
        self.assertEqual(suscripcion.estado, Suscripcion.Estado.SUSPENDIDA)

    def test_no_toca_una_cancelada(self):
        suscripcion = self.crear(Suscripcion.Estado.CANCELADA, vencida_hace=90)
        self.correr()
        suscripcion.refresh_from_db()
        self.assertEqual(suscripcion.estado, Suscripcion.Estado.CANCELADA)

    def test_no_modifica_la_fecha_de_fin(self):
        """
        De esto depende que la orden no mande correos: el aviso al administrador
        de la licorera cuelga de quien escribe la fecha, y la orden no la escribe.
        """
        suscripcion = self.crear(Suscripcion.Estado.ACTIVA, vencida_hace=2)
        fecha = suscripcion.fecha_fin
        self.correr()
        suscripcion.refresh_from_db()
        self.assertEqual(suscripcion.fecha_fin, fecha)

    def test_simular_no_escribe_pero_lo_cuenta(self):
        suscripcion = self.crear(Suscripcion.Estado.ACTIVA, vencida_hace=2)
        salida = self.correr("--simular")
        suscripcion.refresh_from_db()
        self.assertEqual(suscripcion.estado, Suscripcion.Estado.ACTIVA)
        self.assertIn("cambiarían", salida)

    def test_la_fecha_del_argumento_permite_demostrar_sin_esperar(self):
        suscripcion = self.crear(Suscripcion.Estado.ACTIVA, vencida_hace=-10)
        futuro = self.hoy + timedelta(days=30)
        self.correr("--fecha", futuro.isoformat())
        suscripcion.refresh_from_db()
        self.assertEqual(suscripcion.estado, Suscripcion.Estado.SUSPENDIDA)

    def test_una_fecha_mal_escrita_se_rechaza(self):
        with self.assertRaises(CommandError):
            self.correr("--fecha", "31/12/2026")


class PermisoDeEscrituraTests(TestCase):
    """
    Una cuenta suspendida consulta pero no registra (RF-SUS-03).

    Se comprueba sobre la gestión de usuarios, que es la única escritura que la
    aplicación tiene hoy y el primer sitio donde se aplica la regla. INV y VEN
    usarán el mismo permiso.
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
        self.vendedor = Rol.objects.get(nombre=Rol.VENDEDOR)

    def entrar(self):
        respuesta = self.client.post(
            reverse("ingresar"),
            {"correo": self.DATOS["correo"], "password": self.DATOS["password"]},
            content_type="application/json",
        )
        return {"HTTP_AUTHORIZATION": "Bearer %s" % respuesta.json()["acceso"]}

    def vencer(self, hace_dias):
        self.suscripcion.fecha_fin = timezone.localdate() - timedelta(days=hace_dias)
        self.suscripcion.save(update_fields=["fecha_fin"])

    def crear_vendedor(self):
        return self.client.post(
            reverse("usuario-list"),
            {"nombre_completo": "Vendedor", "correo": "vendedor@prueba.com",
             "password": "Licorera2026", "rol": self.vendedor.id},
            content_type="application/json", **self.entrar())

    def test_la_gestion_de_usuarios_lleva_puesto_el_permiso(self):
        """
        Comprobar el 403 no basta: si alguien quitara el permiso de la vista, el
        403 desaparecería y con él la prueba que lo vigila. Esto mira que la
        regla siga enganchada donde debe.
        """
        from seguridad.views import UsuarioViewSet
        self.assertIn(PuedeRegistrarOperaciones, UsuarioViewSet.permission_classes)

    def test_con_la_suscripcion_vigente_se_puede_crear(self):
        self.assertEqual(self.crear_vendedor().status_code, status.HTTP_201_CREATED)

    def test_una_prueba_vencida_no_deja_crear(self):
        self.vencer(1)
        self.assertEqual(self.crear_vendedor().status_code, status.HTTP_403_FORBIDDEN)

    def test_la_cuenta_suspendida_sigue_pudiendo_consultar(self):
        """La mitad del requisito que no se puede olvidar: consultar sí se puede."""
        self.vencer(1)
        respuesta = self.client.get(reverse("usuario-list"), **self.entrar())
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)

    def test_no_deja_inactivar_con_la_cuenta_suspendida(self):
        usuario = Usuario.objects.get(correo=self.DATOS["correo"])
        self.vencer(1)
        respuesta = self.client.delete(
            reverse("usuario-detail", args=[usuario.id]), **self.entrar())
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)


class ConsultaDeEstadoTests(TestCase):
    """Lo que el panel recibe cuando la cuenta entra en mora (RF-SUS-03)."""

    DATOS = PermisoDeEscrituraTests.DATOS

    def setUp(self):
        cache.clear()
        self.client.post(reverse("registrar-licorera"), self.DATOS,
                         content_type="application/json")
        self.licorera = Licorera.objects.get(nombre=self.DATOS["nombre_negocio"])
        self.suscripcion = Suscripcion.objects.get(licorera=self.licorera)

    def consultar(self):
        respuesta = self.client.post(
            reverse("ingresar"),
            {"correo": self.DATOS["correo"], "password": self.DATOS["password"]},
            content_type="application/json")
        return self.client.get(
            reverse("mi-suscripcion"),
            HTTP_AUTHORIZATION="Bearer %s" % respuesta.json()["acceso"]).json()

    def test_la_consulta_devuelve_el_estado_calculado_y_no_el_guardado(self):
        """
        La fila sigue diciendo «en prueba» porque la orden diaria no ha corrido.
        Lo que el panel muestra no puede depender de que anoche corriera.
        """
        self.suscripcion.plan = Plan.objects.get(nombre="Básico")
        self.suscripcion.precio_pactado = self.suscripcion.plan.precio_mensual
        self.suscripcion.estado = Suscripcion.Estado.ACTIVA
        self.suscripcion.fecha_fin = timezone.localdate() - timedelta(days=1)
        self.suscripcion.save()
        datos = self.consultar()
        self.assertEqual(datos["estado"], Suscripcion.Estado.EN_MORA)
        self.assertEqual(datos["dias_para_suspension"], Suscripcion.DIAS_DE_GRACIA)
        self.assertTrue(datos["puede_operar"])
        self.assertFalse(datos["es_prueba"])

    def test_avisa_solo_cuando_el_vencimiento_esta_cerca(self):
        """
        El umbral lo resuelve el servidor. Con la prueba recién abierta faltan
        quince días y no hay nada que avisar; movida la fecha al borde, sí.
        """
        self.assertFalse(self.consultar()["avisa_vencimiento"])
        self.suscripcion.fecha_fin = (
            timezone.localdate() + timedelta(days=Suscripcion.DIAS_DE_AVISO))
        self.suscripcion.save(update_fields=["fecha_fin"])
        datos = self.consultar()
        self.assertTrue(datos["avisa_vencimiento"])
        self.assertEqual(datos["dias_restantes"], Suscripcion.DIAS_DE_AVISO)


class CaracteristicasDelPlanTests(TestCase):
    """Qué habilita cada plan, preguntado por su nombre (RF-SUS-04)."""

    def setUp(self):
        self.basico = Plan.objects.get(nombre="Básico")
        self.pro = Plan.objects.get(nombre="Pro")

    def test_el_basico_es_de_un_usuario_y_una_sede(self):
        self.assertFalse(self.basico.incluye(Plan.Caracteristica.MULTIUSUARIO))
        self.assertFalse(self.basico.incluye(Plan.Caracteristica.MULTISEDE))

    def test_el_basico_no_trae_facturacion_ni_reportes_avanzados(self):
        self.assertFalse(self.basico.incluye(Plan.Caracteristica.FACTURACION))
        self.assertFalse(self.basico.incluye(Plan.Caracteristica.REPORTES_AVANZADOS))

    def test_el_pro_las_trae_todas(self):
        for caracteristica in Plan.Caracteristica:
            self.assertTrue(self.pro.incluye(caracteristica), caracteristica)

    def test_un_tope_mayor_que_uno_si_es_multiusuario(self):
        """
        El tope y la característica responden preguntas distintas: un plan de
        cinco usuarios incluye multiusuario y sigue teniendo límite. Si se
        confundieran, el día que exista un plan intermedio no habría forma de
        decir que admite varios y a la vez no admite infinitos.
        """
        intermedio = Plan.objects.create(
            nombre="Intermedio", precio_mensual=1, maximo_usuarios=5, maximo_sedes=1)
        self.assertTrue(intermedio.incluye(Plan.Caracteristica.MULTIUSUARIO))
        self.assertEqual(intermedio.maximo_usuarios, 5)

    def test_un_nombre_que_no_existe_no_pasa_en_silencio(self):
        """Devolver «no incluida» sería una restricción invisible."""
        with self.assertRaises(ValueError):
            self.basico.incluye("teletransporte")


class ModulosSegunElPlanTests(TestCase):
    """
    En qué estado le llega cada módulo del menú a una licorera (RF-SUS-04).

    POR QUÉ IMPORTA EL CASO DEL BÁSICO
    Antes, el menú anunciaba Sedes como «Pronto» a todo el mundo. A quien tiene
    plan Básico eso le promete algo que no va a llegar nunca, porque multisede
    es del Pro. Es la diferencia que este bloque viene a arreglar y la que estas
    pruebas vigilan.
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
        self.url = reverse("mis-modulos")

    def consultar(self):
        respuesta = self.client.post(
            reverse("ingresar"),
            {"correo": self.DATOS["correo"], "password": self.DATOS["password"]},
            content_type="application/json")
        datos = self.client.get(
            self.url,
            HTTP_AUTHORIZATION="Bearer %s" % respuesta.json()["acceso"]).json()
        return {m["clave"]: m["estado"] for m in datos["modulos"]}

    def pasar_a_basico(self):
        self.suscripcion.plan = Plan.objects.get(nombre="Básico")
        self.suscripcion.save(update_fields=["plan"])

    def test_la_consulta_exige_sesion(self):
        self.assertEqual(self.client.get(self.url).status_code,
                         status.HTTP_401_UNAUTHORIZED)

    def test_lo_construido_aparece_disponible(self):
        estados = self.consultar()
        self.assertEqual(estados["panel"], "disponible")
        self.assertEqual(estados["usuarios"], "disponible")

    def test_lo_que_falta_por_construir_aparece_como_pronto(self):
        estados = self.consultar()
        self.assertEqual(estados["inventario"], "pronto")
        self.assertEqual(estados["ventas"], "pronto")

    def test_con_plan_pro_sedes_esta_pendiente_de_construir(self):
        """La prueba corre sobre Pro, así que multisede sí entra en su plan."""
        self.assertEqual(self.consultar()["sedes"], "pronto")

    def test_con_plan_basico_sedes_no_entra_en_el_plan(self):
        self.pasar_a_basico()
        self.assertEqual(self.consultar()["sedes"], "plan")

    def test_el_plan_pesa_mas_que_lo_construido(self):
        """
        Aunque Sedes se construyera mañana, a una licorera con plan Básico le
        sigue sin corresponder. Por eso el estado del plan se decide primero.
        """
        modulo = next(m for m in MODULOS if m.clave == "sedes")
        construido = modulo.construido
        modulo.construido = True
        try:
            self.pasar_a_basico()
            self.assertEqual(self.consultar()["sedes"], "plan")
        finally:
            modulo.construido = construido

    def test_reportes_no_se_cierra_por_plan(self):
        """
        El Básico incluye los reportes básicos; lo que el Pro añade son la
        rotación y la utilidad. La restricción va dentro del módulo, no en la
        puerta, y el menú no debe cerrarlo.
        """
        self.pasar_a_basico()
        self.assertEqual(self.consultar()["reportes"], "pronto")

    def test_la_cuenta_suspendida_sigue_viendo_su_plan(self):
        """
        Suspendida no es «sin plan»: el negocio contrató algo y su menú tiene que
        seguir diciendo la verdad sobre lo que ese plan incluye. Lo que no puede
        hacer —registrar— lo corta el permiso de escritura, que es otra cosa.
        """
        self.pasar_a_basico()
        self.suscripcion.fecha_fin = timezone.localdate() - timedelta(days=30)
        self.suscripcion.save(update_fields=["fecha_fin"])
        self.assertEqual(self.consultar()["sedes"], "plan")

    def test_sin_suscripcion_no_se_inventan_restricciones(self):
        """
        Sin plan no se sabe qué incluye, y suponer que no incluye nada sería
        inventar una restricción. Queda lo único cierto: qué está construido.
        """
        self.suscripcion.delete()
        self.assertEqual(self.consultar()["sedes"], "pronto")


class CambioDePlanTests(TestCase):
    """
    Bajar y subir de plan (RF-SUS-02, decisiones D-23 y D-25).

    La licorera nace en prueba sobre Pro, así que casi todas las pruebas la pasan
    antes a un Pro contratado: la prueba tiene reglas propias y se comprueban
    aparte.
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
        self.basico = Plan.objects.get(nombre="Básico")
        self.pro = Plan.objects.get(nombre="Pro")
        self.url = reverse("cambiar-plan")
        self.hoy = timezone.localdate()

    # --- utilidades ---

    def contratar_pro(self, vence_en=20):
        """Saca la licorera de la prueba y la deja con un Pro contratado."""
        self.suscripcion.estado = Suscripcion.Estado.ACTIVA
        self.suscripcion.precio_pactado = self.pro.precio_mensual
        self.suscripcion.fecha_fin = self.hoy + timedelta(days=vence_en)
        self.suscripcion.save()

    def cabecera(self, correo=None, password=None):
        respuesta = self.client.post(
            reverse("ingresar"),
            {"correo": correo or self.DATOS["correo"],
             "password": password or self.DATOS["password"]},
            content_type="application/json")
        return {"HTTP_AUTHORIZATION": "Bearer %s" % respuesta.json()["acceso"]}

    def pedir(self, plan=None, **cabecera):
        return self.client.post(
            self.url, {"plan": plan.id if plan else None},
            content_type="application/json", **(cabecera or self.cabecera()))

    def segundo_usuario(self, activo=True):
        return Usuario.objects.create_user(
            correo="vendedor@prueba.com", nombre_completo="Vendedor",
            password="Licorera2026", licorera=self.licorera,
            rol=Rol.objects.get(nombre=Rol.VENDEDOR), activo=activo)

    # --- el sentido del cambio ---

    def test_bajar_es_pasar_a_un_plan_mas_barato(self):
        self.assertTrue(es_bajada(self.pro, self.basico))
        self.assertFalse(es_bajada(self.basico, self.pro))

    def test_el_negocio_no_puede_subir_de_plan_por_su_cuenta(self):
        """Subir implica cobrar, y el cobro no pasa por la aplicación (D-23)."""
        self.contratar_pro()
        self.suscripcion.plan = self.basico
        self.suscripcion.precio_pactado = self.basico.precio_mensual
        self.suscripcion.save()
        respuesta = self.pedir(self.pro)
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("INVENTRA", respuesta.json()["detalle"])

    # --- la bajada que procede ---

    def test_bajar_cierra_la_fila_anterior_y_abre_otra(self):
        self.contratar_pro()
        vence = self.suscripcion.fecha_fin
        respuesta = self.pedir(self.basico)
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)

        self.suscripcion.refresh_from_db()
        self.assertEqual(self.suscripcion.fecha_fin, self.hoy)

        nueva = self.licorera.suscripcion_actual()
        self.assertEqual(nueva.plan, self.basico)
        self.assertEqual(nueva.fecha_inicio, self.hoy)
        self.assertEqual(nueva.estado, Suscripcion.Estado.ACTIVA)
        self.assertEqual(self.licorera.suscripciones.count(), 2)

    def test_la_fila_nueva_hereda_la_fecha_de_vencimiento(self):
        """
        El cliente no escribe fechas: si la fila nueva estrenara vigencia,
        cambiar de plan sería una forma de regalársela (D-25).
        """
        self.contratar_pro()
        vence = self.suscripcion.fecha_fin
        self.pedir(self.basico)
        self.assertEqual(self.licorera.suscripcion_actual().fecha_fin, vence)

    def test_el_precio_del_plan_nuevo_queda_congelado(self):
        self.contratar_pro()
        self.pedir(self.basico)
        self.assertEqual(self.licorera.suscripcion_actual().precio_pactado,
                         self.basico.precio_mensual)

    def test_cerrar_una_fila_vencida_no_le_alarga_la_vigencia(self):
        """
        Una cuenta suspendida que se pasa al plan barato antes de ponerse al día
        conserva la fecha en que venció. Ponerle la de hoy le regalaría los días
        que estuvo sin servicio y el historial diría que estuvo vigente.
        """
        self.contratar_pro(vence_en=-30)
        vencio = self.suscripcion.fecha_fin
        self.pedir(self.basico)
        self.suscripcion.refresh_from_db()
        self.assertEqual(self.suscripcion.fecha_fin, vencio)
        self.assertEqual(self.licorera.suscripcion_actual().fecha_fin, vencio)

    def test_la_licorera_suspendida_puede_bajar_de_plan(self):
        """
        Es el camino de vuelta que describe D-25: bajar, pagar y que INVENTRA
        renueve. Si el permiso de escritura cerrara esta puerta, esa licorera se
        quedaría sin salida dentro de la aplicación.
        """
        self.contratar_pro(vence_en=-30)
        self.assertIsNone(self.licorera.suscripcion_vigente())
        self.assertEqual(self.pedir(self.basico).status_code, status.HTTP_200_OK)

    def test_la_fila_nueva_nace_suspendida_si_hereda_una_fecha_pasada(self):
        self.contratar_pro(vence_en=-30)
        self.pedir(self.basico)
        self.assertEqual(self.licorera.suscripcion_actual().estado,
                         Suscripcion.Estado.SUSPENDIDA)

    # --- la bajada que no cabe ---

    def test_no_se_baja_con_mas_usuarios_de_los_que_admite_el_plan(self):
        self.contratar_pro()
        self.segundo_usuario()
        respuesta = self.pedir(self.basico)
        self.assertEqual(respuesta.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(self.licorera.suscripciones.count(), 1)

    def test_el_rechazo_dice_el_limite_y_cuantos_hay(self):
        """
        «Excede el límite» no deja actuar a nadie: hay que decir cuántos admite
        el plan y cuántos tiene la licorera, en castellano y sin paréntesis.
        """
        self.contratar_pro()
        self.segundo_usuario()
        detalle = self.pedir(self.basico).json()["detalle"]
        self.assertIn("un usuario", detalle)
        self.assertIn("2 usuarios activos", detalle)
        self.assertNotIn("(s)", detalle)

    def test_los_usuarios_inactivos_no_estorban(self):
        """Quien fue dado de baja no ocupa un cupo, aquí tampoco."""
        self.contratar_pro()
        self.segundo_usuario(activo=False)
        self.assertEqual(self.pedir(self.basico).status_code, status.HTTP_200_OK)

    def test_el_calculo_de_lo_que_sobra_se_puede_preguntar_aparte(self):
        """
        `excesos()` es lo que el panel de INVENTRA necesitará para avisar antes
        de intentar el cambio, así que responde por su cuenta y no solo dentro
        del rechazo.
        """
        self.contratar_pro()
        self.assertEqual(excesos(self.licorera, self.basico), [])
        self.segundo_usuario()
        sobra = excesos(self.licorera, self.basico)
        self.assertEqual(len(sobra), 1)
        self.assertIn("2 usuarios activos", sobra[0])

    def test_el_plan_sin_tope_no_deja_nada_fuera(self):
        self.contratar_pro()
        self.segundo_usuario()
        self.assertEqual(excesos(self.licorera, self.pro), [])

    # --- la prueba tiene sus propias reglas ---

    def test_durante_la_prueba_no_se_cambia_de_plan(self):
        respuesta = self.pedir(self.basico)
        self.assertEqual(respuesta.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(self.licorera.suscripciones.count(), 1)

    def test_el_aviso_de_la_prueba_dice_que_es_pro_y_que_se_pierde_al_bajar(self):
        """
        Lo pidió así: que quede claro que la prueba es la versión Pro y que
        elegir el Básico después significa perder funciones.
        """
        detalle = self.pedir(self.basico).json()["detalle"]
        self.assertIn("Pro", detalle)
        self.assertIn("Básico", detalle)
        self.assertIn("un solo usuario", detalle)

    # --- lo que no procede por otros motivos ---

    def test_no_se_cambia_al_plan_que_ya_se_tiene(self):
        self.contratar_pro()
        respuesta = self.pedir(self.pro)
        self.assertEqual(respuesta.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("ya tiene", respuesta.json()["detalle"])

    def test_sin_plan_en_la_peticion_no_se_hace_nada(self):
        self.contratar_pro()
        self.assertEqual(self.pedir(None).status_code, status.HTTP_400_BAD_REQUEST)

    def test_un_vendedor_no_cambia_el_plan_del_negocio(self):
        self.contratar_pro()
        self.segundo_usuario()
        respuesta = self.pedir(
            self.basico,
            **self.cabecera("vendedor@prueba.com", "Licorera2026"))
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_la_peticion_exige_sesion(self):
        respuesta = self.client.post(self.url, {"plan": self.basico.id},
                                     content_type="application/json")
        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)


class PanelBase(TestCase):
    """Montaje común del panel: un operador de plataforma y una licorera con plan."""

    CLAVE = "Inventra2026"

    def setUp(self):
        cache.clear()
        self.basico = Plan.objects.get(nombre="Básico")
        self.pro = Plan.objects.get(nombre="Pro")
        self.hoy = timezone.localdate()

        self.operador = Usuario.objects.create_superuser(
            correo="plataforma@inventra.co", nombre_completo="Operador",
            password=self.CLAVE)

        self.licorera = Licorera.objects.create(
            nombre="Licorera La Esquina", correo="contacto@esquina.com")
        self.suscripcion = Suscripcion.objects.create(
            licorera=self.licorera, plan=self.basico,
            estado=Suscripcion.Estado.ACTIVA,
            fecha_inicio=self.hoy, fecha_fin=self.hoy + timedelta(days=20),
            precio_pactado=self.basico.precio_mensual)
        self.duena = Usuario.objects.create_user(
            correo="duena@esquina.com", nombre_completo="Dueña",
            password=self.CLAVE, licorera=self.licorera,
            rol=Rol.objects.get(nombre=Rol.ADMINISTRADOR_LICORERA))
        mail.outbox = []

    def cabecera(self, correo=None):
        respuesta = self.client.post(
            reverse("ingresar"),
            {"correo": correo or self.operador.correo, "password": self.CLAVE},
            content_type="application/json")
        return {"HTTP_AUTHORIZATION": "Bearer %s" % respuesta.json()["acceso"]}

    def url_suscripcion(self, licorera=None):
        return reverse("suscripcion-de-licorera",
                       args=[(licorera or self.licorera).id])


class AltaDeLicoreraTests(PanelBase):
    """Alta directa por el Administrador INVENTRA (RF-SUS-01, segunda vía)."""

    DATOS = {
        "nombre_negocio": "Licorera El Roble",
        "nombre_completo": "Pedro Roble",
        "correo": "pedro@roble.com",
    }

    def alta(self, **cambios):
        cuerpo = dict(self.DATOS, plan=self.pro.id,
                      fecha_fin=str(timezone.localdate() + timedelta(days=30)))
        cuerpo.update(cambios)
        return self.client.post(reverse("alta-licorera"), cuerpo,
                                content_type="application/json", **self.cabecera())

    def test_crea_el_negocio_con_su_plan_y_su_fecha(self):
        self.assertEqual(self.alta().status_code, status.HTTP_201_CREATED)
        licorera = Licorera.objects.get(nombre=self.DATOS["nombre_negocio"])
        suscripcion = licorera.suscripcion_actual()
        self.assertEqual(suscripcion.plan, self.pro)
        self.assertEqual(suscripcion.fecha_fin, self.hoy + timedelta(days=30))
        self.assertEqual(suscripcion.precio_pactado, self.pro.precio_mensual)
        self.assertEqual(suscripcion.estado, Suscripcion.Estado.ACTIVA)

    def test_la_cuenta_nace_sin_contrasena_utilizable(self):
        """
        INVENTRA no debe conocer la clave de un cliente. Mientras el dueño no
        defina la suya, no hay ninguna que sirva para entrar.
        """
        self.alta()
        usuario = Usuario.objects.get(correo=self.DATOS["correo"])
        self.assertFalse(usuario.has_usable_password())
        respuesta = self.client.post(
            reverse("ingresar"),
            {"correo": self.DATOS["correo"], "password": self.CLAVE},
            content_type="application/json")
        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_se_le_envia_al_dueno_el_enlace_para_definirla(self):
        self.alta()
        self.assertEqual(len(mail.outbox), 1)
        mensaje = mail.outbox[0]
        self.assertEqual(mensaje.to, [self.DATOS["correo"]])
        self.assertIn("restablecer-contrasena", mensaje.body)

    def test_no_se_repite_un_correo_ya_registrado(self):
        respuesta = self.alta(correo=self.duena.correo)
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_la_fecha_de_vencimiento_no_puede_ser_pasada(self):
        respuesta = self.alta(fecha_fin=str(self.hoy - timedelta(days=1)))
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_un_administrador_de_licorera_no_da_de_alta_a_nadie(self):
        respuesta = self.client.post(
            reverse("alta-licorera"), dict(self.DATOS, plan=self.pro.id,
                                           fecha_fin=str(self.hoy)),
            content_type="application/json", **self.cabecera(self.duena.correo))
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)


class PanelDeLaPlataformaTests(PanelBase):
    """Lo que ve el operador de la plataforma (RF-SUS-05)."""

    CAMPOS = {
        "id", "nombre", "nit", "correo", "telefono", "fecha_registro", "activo",
        "plan", "estado", "estado_texto", "fecha_fin", "dias_restantes",
        "puede_operar", "usuarios_activos",
    }

    def consultar(self):
        return self.client.get(reverse("panel"), **self.cabecera()).json()

    def test_lista_las_licoreras_con_su_plan_y_su_estado(self):
        datos = self.consultar()["licoreras"]
        fila = next(l for l in datos if l["nombre"] == self.licorera.nombre)
        self.assertEqual(fila["plan"], "Básico")
        self.assertEqual(fila["estado"], Suscripcion.Estado.ACTIVA)
        self.assertEqual(fila["usuarios_activos"], 1)

    def test_no_expone_informacion_comercial_del_negocio(self):
        """
        El requisito lo prohíbe expresamente. La prueba fija el juego de campos
        entero y no la ausencia de uno concreto: así, el día que alguien añada
        las ventas o el inventario «para que se vea mejor», falla aquí.
        """
        fila = self.consultar()["licoreras"][0]
        self.assertEqual(set(fila), self.CAMPOS)

    def test_las_metricas_cuentan_las_cuentas_activas_y_lo_que_facturan(self):
        metricas = self.consultar()["metricas"]
        self.assertEqual(metricas["licoreras_registradas"], 1)
        self.assertEqual(metricas["cuentas_activas"], 1)
        self.assertEqual(float(metricas["ingresos_mensuales_recurrentes"]),
                         float(self.basico.precio_mensual))

    def test_una_suspendida_no_cuenta_como_activa_ni_suma_ingresos(self):
        self.suscripcion.fecha_fin = self.hoy - timedelta(days=30)
        self.suscripcion.save(update_fields=["fecha_fin"])
        metricas = self.consultar()["metricas"]
        self.assertEqual(metricas["cuentas_activas"], 0)
        self.assertEqual(float(metricas["ingresos_mensuales_recurrentes"]), 0)

    def test_una_prueba_no_suma_ingresos(self):
        self.suscripcion.estado = Suscripcion.Estado.EN_PRUEBA
        self.suscripcion.precio_pactado = 0
        self.suscripcion.save()
        metricas = self.consultar()["metricas"]
        self.assertEqual(metricas["cuentas_activas"], 1)
        self.assertEqual(float(metricas["ingresos_mensuales_recurrentes"]), 0)

    def test_el_estado_que_muestra_es_el_calculado_y_no_el_guardado(self):
        """La columna la pone al día una orden; el panel no puede esperarla."""
        self.suscripcion.fecha_fin = self.hoy - timedelta(days=1)
        self.suscripcion.save(update_fields=["fecha_fin"])
        fila = self.consultar()["licoreras"][0]
        self.assertEqual(fila["estado"], Suscripcion.Estado.EN_MORA)

    def test_el_panel_es_solo_del_operador_de_la_plataforma(self):
        respuesta = self.client.get(reverse("panel"),
                                    **self.cabecera(self.duena.correo))
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)


class AbrirPeriodoTests(PanelBase):
    """Renovar y subir de plan, que son la misma operación (D-25)."""

    def pedir(self, plan=None, dias=30, correo=None):
        cuerpo = {"plan": (plan or self.basico).id}
        if dias is not None:
            cuerpo["fecha_fin"] = str(self.hoy + timedelta(days=dias))
        return self.client.post(self.url_suscripcion(), cuerpo,
                                content_type="application/json",
                                **self.cabecera(correo))

    def test_renovar_cierra_la_anterior_y_abre_otra_con_la_fecha_dada(self):
        self.assertEqual(self.pedir().status_code, status.HTTP_201_CREATED)
        self.suscripcion.refresh_from_db()
        self.assertEqual(self.suscripcion.fecha_fin, self.hoy)
        nueva = self.licorera.suscripcion_actual()
        self.assertEqual(nueva.fecha_fin, self.hoy + timedelta(days=30))
        self.assertEqual(self.licorera.suscripciones.count(), 2)

    def test_subir_de_plan_es_la_misma_operacion_con_otro_plan(self):
        self.pedir(plan=self.pro)
        nueva = self.licorera.suscripcion_actual()
        self.assertEqual(nueva.plan, self.pro)
        self.assertEqual(nueva.precio_pactado, self.pro.precio_mensual)

    def test_la_fecha_no_se_hereda_al_subir_la_escribe_quien_cobra(self):
        anterior = self.suscripcion.fecha_fin
        self.pedir(plan=self.pro, dias=60)
        self.assertNotEqual(self.licorera.suscripcion_actual().fecha_fin, anterior)
        self.assertEqual(self.licorera.suscripcion_actual().fecha_fin,
                         self.hoy + timedelta(days=60))

    def test_bajar_de_plan_no_se_hace_desde_el_panel(self):
        """
        El rechazo por exceso de usuarios tiene que salirle a quien decide qué
        inactiva, y esa persona no está en INVENTRA (D-23).
        """
        self.suscripcion.plan = self.pro
        self.suscripcion.precio_pactado = self.pro.precio_mensual
        self.suscripcion.save()
        respuesta = self.pedir(plan=self.basico)
        self.assertEqual(respuesta.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("administrador de la licorera", respuesta.json()["detalle"])

    def test_sin_fecha_no_se_abre_nada(self):
        self.assertEqual(self.pedir(dias=None).status_code, status.HTTP_409_CONFLICT)

    def test_la_fecha_no_puede_quedar_en_el_pasado(self):
        respuesta = self.pedir(dias=-1)
        self.assertEqual(respuesta.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("pasado", respuesta.json()["detalle"])

    def test_avisa_por_correo_al_administrador_de_la_licorera(self):
        self.pedir(dias=45)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.duena.correo])
        self.assertIn("Vigencia", mail.outbox[0].subject)

    def vendedor(self):
        return Usuario.objects.create_user(
            correo="vendedor@esquina.com", nombre_completo="Vendedor",
            password=self.CLAVE, licorera=self.licorera,
            rol=Rol.objects.get(nombre=Rol.VENDEDOR))

    def test_el_aviso_va_a_los_administradores_y_no_a_los_vendedores(self):
        """
        Se avisa a quien puede hacer algo con el aviso. Un vendedor no renueva
        nada y recibirlo solo le enseña a ignorar los correos del sistema.
        """
        self.suscripcion.plan = self.pro        # el Pro admite dos cuentas
        self.suscripcion.precio_pactado = self.pro.precio_mensual
        self.suscripcion.save()
        self.vendedor()
        self.pedir(plan=self.pro, dias=45)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.duena.correo])

    def test_renovar_el_mismo_plan_no_se_bloquea_por_exceso(self):
        """
        Renovar no cambia ningún límite, así que no hay nada que validar. Si se
        comprobara igual, una licorera que por lo que fuera excediera su propio
        plan no podría renovar —no podría pagar—, y negarle el cobro no arregla
        el exceso: lo congela.
        """
        self.vendedor()                         # dos cuentas en un plan de una
        self.assertEqual(self.pedir().status_code, status.HTTP_201_CREATED)

    def test_subir_de_plan_si_comprueba_que_quepa(self):
        """
        Lo contrario del caso anterior: al cambiar de plan sí cambian los
        límites, y ahí la comprobación es la que pide RF-SUS-02.
        """
        self.suscripcion.plan = self.pro
        self.suscripcion.precio_pactado = self.pro.precio_mensual
        self.suscripcion.save()
        self.vendedor()
        intermedio = Plan.objects.create(
            nombre="Intermedio", precio_mensual=self.pro.precio_mensual * 2,
            maximo_usuarios=1, maximo_sedes=1)
        respuesta = self.pedir(plan=intermedio)
        self.assertEqual(respuesta.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("no cabe", respuesta.json()["detalle"])

    def test_sin_administrador_activo_el_aviso_se_calla_en_vez_de_fallar(self):
        """
        No tener a quien avisar no es motivo para dejar la renovación a medias:
        el período se abrió igual, que es lo que importaba.
        """
        self.duena.activo = False
        self.duena.save(update_fields=["activo"])
        self.assertEqual(enviar_correo_vencimiento(self.licorera, self.suscripcion), [])
        self.assertEqual(self.pedir(dias=45).status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(mail.outbox), 0)

    def test_cerrar_una_fila_vencida_no_le_alarga_la_vigencia(self):
        self.suscripcion.fecha_fin = self.hoy - timedelta(days=30)
        self.suscripcion.save(update_fields=["fecha_fin"])
        vencio = self.suscripcion.fecha_fin
        self.pedir()
        self.suscripcion.refresh_from_db()
        self.assertEqual(self.suscripcion.fecha_fin, vencio)

    def test_el_servicio_se_puede_llamar_sin_pasar_por_la_vista(self):
        """Lo usará también el alta y, más adelante, cualquier proceso de cobro."""
        nueva = abrir_periodo(self.licorera, self.pro, self.hoy + timedelta(days=10))
        self.assertEqual(nueva.plan, self.pro)


class CorregirVencimientoTests(PanelBase):
    """La fecha mal escrita se arregla; nada queda irreparable (D-25)."""

    def corregir(self, dias, correo=None):
        return self.client.patch(
            self.url_suscripcion(),
            {"fecha_fin": str(self.hoy + timedelta(days=dias))},
            content_type="application/json", **self.cabecera(correo))

    def test_corrige_la_fila_vigente_sin_abrir_otra(self):
        self.assertEqual(self.corregir(60).status_code, status.HTTP_200_OK)
        self.suscripcion.refresh_from_db()
        self.assertEqual(self.suscripcion.fecha_fin, self.hoy + timedelta(days=60))
        self.assertEqual(self.licorera.suscripciones.count(), 1)

    def test_los_dos_anos_que_eran_dos_meses(self):
        """El caso que motivó la regla: una fecha larguísima se acorta."""
        self.corregir(730)
        self.corregir(60)
        self.suscripcion.refresh_from_db()
        self.assertEqual(self.suscripcion.fecha_fin, self.hoy + timedelta(days=60))

    def test_corregir_hacia_adelante_devuelve_a_la_vida_una_suspendida(self):
        """
        Si alguien tecleó una fecha demasiado temprana y la cuenta quedó
        suspendida, corregirla tiene que arreglarlo: de nada sirve poder editar
        si el daño ya es irreversible.
        """
        self.suscripcion.fecha_fin = self.hoy - timedelta(days=30)
        self.suscripcion.estado = Suscripcion.Estado.SUSPENDIDA
        self.suscripcion.save()
        self.corregir(30)
        self.suscripcion.refresh_from_db()
        self.assertEqual(self.suscripcion.estado, Suscripcion.Estado.ACTIVA)
        self.assertTrue(self.suscripcion.esta_vigente())

    def test_guardar_la_misma_fecha_no_manda_correo(self):
        """Avisar de algo que no pasó enseña a no leer los avisos."""
        dias = (self.suscripcion.fecha_fin - self.hoy).days
        self.assertEqual(self.corregir(dias).status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 0)

    def test_corregirla_de_verdad_si_manda_correo(self):
        """El correo lleva la fecha nueva escrita, no un «se actualizó»."""
        nueva = self.hoy + timedelta(days=99)
        self.corregir(99)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.duena.correo])
        self.assertIn(nueva.strftime("%d/%m/%Y"), mail.outbox[0].body)

    def test_no_se_puede_corregir_hacia_el_pasado(self):
        respuesta = self.corregir(-1)
        self.assertEqual(respuesta.status_code, status.HTTP_409_CONFLICT)

    def test_una_licorera_que_no_existe_responde_que_no_existe(self):
        respuesta = self.client.patch(
            reverse("suscripcion-de-licorera", args=[9999]),
            {"fecha_fin": str(self.hoy)},
            content_type="application/json", **self.cabecera())
        self.assertEqual(respuesta.status_code, status.HTTP_404_NOT_FOUND)

    def test_el_servicio_dice_si_hubo_cambio(self):
        cambio, _ = corregir_vencimiento(self.licorera, self.suscripcion.fecha_fin)
        self.assertFalse(cambio)
        cambio, _ = corregir_vencimiento(self.licorera, self.hoy + timedelta(days=5))
        self.assertTrue(cambio)

