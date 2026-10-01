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

from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from seguridad.models import Rol, Usuario

from .models import Licorera, Plan, Suscripcion
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
