"""
Pruebas del catálogo de productos (RF-INV-01 a 04).

Se ejecutan con `py manage.py test inventario`.
"""

from datetime import timedelta

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from seguridad.models import Rol, Usuario
from suscripciones.models import Licorera, Plan, Suscripcion
from suscripciones.puesta_en_marcha import preparar_licorera_nueva

from .models import Categoria, Producto

CLAVE = "Licorera2026"


def crear_negocio(nombre, plan_nombre="Pro"):
    """Una licorera lista para trabajar: con suscripción vigente, sede y categorías."""
    plan = Plan.objects.get(nombre=plan_nombre)
    licorera = Licorera.objects.create(nombre=nombre, correo=f"{nombre.lower()}@prueba.com")
    Suscripcion.objects.create(
        licorera=licorera, plan=plan, estado=Suscripcion.Estado.ACTIVA,
        fecha_inicio=timezone.localdate(),
        fecha_fin=timezone.localdate() + timedelta(days=30),
        precio_pactado=plan.precio_mensual,
    )
    preparar_licorera_nueva(licorera)
    return licorera


def crear_usuario(licorera, correo, rol_nombre):
    return Usuario.objects.create_user(
        correo=correo, nombre_completo="Persona de Prueba", password=CLAVE,
        licorera=licorera, rol=Rol.objects.get(nombre=rol_nombre),
        correo_verificado=True,
    )


class CatalogoBase(TestCase):
    def setUp(self):
        cache.clear()
        self.licorera = crear_negocio("Aurora")
        self.administrador = crear_usuario(
            self.licorera, "admin@prueba.com", Rol.ADMINISTRADOR_LICORERA)
        self.categoria = Categoria.objects.get(licorera=self.licorera, nombre="Ron")

    def entrar(self, correo=None):
        respuesta = self.client.post(
            reverse("ingresar"),
            {"correo": correo or self.administrador.correo, "password": CLAVE},
            content_type="application/json",
        )
        return {"HTTP_AUTHORIZATION": "Bearer %s" % respuesta.json()["acceso"]}

    def crear(self, **cambios):
        cuerpo = {
            "nombre": "Ron Medellín Añejo 750 ml",
            "categoria": self.categoria.id,
            "presentacion": Producto.Presentacion.BOTELLA,
            "codigo_barras": "7701234567890",
            "precio_venta": "48500.00",
            "stock_minimo": 5,
        }
        cuerpo.update(cambios)
        return self.client.post(reverse("producto-list"), cuerpo,
                                content_type="application/json", **self.entrar())


class CategoriasSembradasTests(CatalogoBase):
    """Las categorías nacen con la licorera y no se gestionan (RF-INV-01)."""

    def test_toda_licorera_nace_con_las_seis_categorias(self):
        nombres = list(
            Categoria.objects.filter(licorera=self.licorera)
            .order_by("id").values_list("nombre", flat=True))
        self.assertEqual(nombres, list(Categoria.POR_DEFECTO))

    def test_sembrar_dos_veces_no_duplica(self):
        Categoria.sembrar(self.licorera)
        self.assertEqual(Categoria.objects.filter(licorera=self.licorera).count(),
                         len(Categoria.POR_DEFECTO))

    def test_la_lista_solo_devuelve_las_de_la_propia_licorera(self):
        otra = crear_negocio("Bolivar")
        respuesta = self.client.get(reverse("categorias"), **self.entrar())

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(len(respuesta.json()), len(Categoria.POR_DEFECTO))
        ajenas = Categoria.objects.filter(licorera=otra).values_list("id", flat=True)
        devueltas = {fila["id"] for fila in respuesta.json()}
        self.assertFalse(devueltas & set(ajenas))


class RegistroDeProductoTests(CatalogoBase):
    """RF-INV-01: registrar una referencia."""

    def test_se_registra_en_la_licorera_de_quien_pide(self):
        respuesta = self.crear()

        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        producto = Producto.objects.get(id=respuesta.json()["id"])
        self.assertEqual(producto.licorera, self.licorera)

    def test_la_licorera_no_viaja_en_la_peticion(self):
        """
        Aunque alguien la mande, se ignora: sale de la sesión. Si se aceptara,
        bastaría cambiar un número para registrar en el catálogo de otro negocio.
        """
        otra = crear_negocio("Caldas")
        respuesta = self.crear(licorera=otra.id)

        producto = Producto.objects.get(id=respuesta.json()["id"])
        self.assertEqual(producto.licorera, self.licorera)

    def test_no_se_puede_usar_una_categoria_de_otra_licorera(self):
        otra = crear_negocio("Dorada")
        ajena = Categoria.objects.filter(licorera=otra).first()

        respuesta = self.crear(categoria=ajena.id)
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_el_producto_no_guarda_costo_ni_existencias(self):
        """
        RF-INV-01 y el MER: el costo entra con cada lote y la existencia se
        deriva de ellos. La prueba vigila la forma de la tabla, porque es una
        decisión que se puede deshacer sin querer al añadir un campo.

        No se comprueba aquí el nombre en inglés de las existencias: esa palabra
        la vigila la comprobación de terminología sobre TODO el código, no solo
        sobre este modelo, y repetirla aquí duplicaba un control que ya existe
        mejor puesto. De hecho fue esa comprobación la que marcó esta línea.
        """
        columnas = {campo.name for campo in Producto._meta.get_fields()}
        self.assertNotIn("costo", columnas)
        self.assertNotIn("precio_compra", columnas)
        self.assertNotIn("existencias", columnas)

    def test_el_precio_de_venta_tiene_que_ser_positivo(self):
        self.assertEqual(self.crear(precio_venta="0").status_code,
                         status.HTTP_400_BAD_REQUEST)

    def test_la_presentacion_es_una_lista_cerrada(self):
        self.assertEqual(self.crear(presentacion="Botella 750ml").status_code,
                         status.HTTP_400_BAD_REQUEST)


class CodigoDeBarrasTests(CatalogoBase):
    """El código es único dentro de la licorera, y opcional."""

    def test_no_se_repite_dentro_de_la_misma_licorera(self):
        self.crear()
        respuesta = self.crear(nombre="Otro producto")

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("codigo_barras", respuesta.json())

    def test_dos_licoreras_pueden_tener_el_mismo_codigo(self):
        """
        Dos negocios distintos venden el mismo aguardiente y comparten su código
        de barras. Un único global dejaría al segundo sin poder registrarlo.
        """
        self.crear()
        otra = crear_negocio("Envigado")
        vendedora = crear_usuario(otra, "otra@prueba.com", Rol.ADMINISTRADOR_LICORERA)
        categoria = Categoria.objects.filter(licorera=otra).first()

        respuesta = self.client.post(
            reverse("producto-list"),
            {"nombre": "Mismo producto", "categoria": categoria.id,
             "presentacion": Producto.Presentacion.BOTELLA,
             "codigo_barras": "7701234567890", "precio_venta": "48500.00",
             "stock_minimo": 5},
            content_type="application/json", **self.entrar(vendedora.correo))

        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)

    def test_la_base_tambien_rechaza_el_codigo_repetido(self):
        """
        La prueba de arriba pasa por el servidor de la aplicación, que valida
        antes de guardar. Esta se salta esa validación y escribe directamente
        en la base, que es lo que haría una carga masiva, una corrección a mano
        o un error de programación futuro.

        Existe por un aviso del propio Django al migrar: la primera versión de
        la restricción llevaba condición, MySQL no las admite y la restricción
        **no se creaba**. La validación del serializador seguía pasando, así que
        sin esta prueba el hueco no se habría visto nunca.
        """
        self.crear()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Producto.objects.create(
                    licorera=self.licorera, categoria=self.categoria,
                    nombre="Duplicado por la puerta de atrás",
                    presentacion=Producto.Presentacion.BOTELLA,
                    codigo_barras="7701234567890",
                    precio_venta=1000, stock_minimo=1)

    def test_la_base_admite_varios_productos_sin_codigo(self):
        """
        La otra mitad, y la razón de que la restricción no necesite condición:
        en SQL dos nulos no son iguales entre sí.
        """
        for numero in range(3):
            Producto.objects.create(
                licorera=self.licorera, categoria=self.categoria,
                nombre="Sin código %d" % numero,
                presentacion=Producto.Presentacion.BOTELLA,
                codigo_barras=None, precio_venta=1000, stock_minimo=1)

        self.assertEqual(
            Producto.objects.filter(licorera=self.licorera,
                                    codigo_barras__isnull=True).count(), 3)

    def test_sin_codigo_se_guarda_vacio_y_no_choca(self):
        """
        Dos productos sin código tienen que poder convivir. Guardados como
        cadena vacía chocarían contra la restricción de unicidad; como nulo, no.
        """
        primero = self.crear(codigo_barras="")
        segundo = self.crear(nombre="Segundo sin código", codigo_barras="")

        self.assertEqual(primero.status_code, status.HTTP_201_CREATED)
        self.assertEqual(segundo.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(Producto.objects.get(id=primero.json()["id"]).codigo_barras)


class ConsultaDelCatalogoTests(CatalogoBase):
    """RF-INV-02: listar, buscar y filtrar."""

    def setUp(self):
        super().setUp()
        self.cerveza = Categoria.objects.get(licorera=self.licorera, nombre="Cerveza")
        self.ron = Producto.objects.create(
            licorera=self.licorera, categoria=self.categoria,
            nombre="Ron Viejo de Caldas 750 ml",
            presentacion=Producto.Presentacion.BOTELLA,
            codigo_barras="7700000000001", precio_venta=46000, stock_minimo=5)
        self.aguila = Producto.objects.create(
            licorera=self.licorera, categoria=self.cerveza,
            nombre="Cerveza Águila 330 ml",
            presentacion=Producto.Presentacion.UNIDAD,
            precio_venta=3500, stock_minimo=24)

    def listar(self, **filtros):
        return self.client.get(reverse("producto-list"), filtros, **self.entrar())

    def test_solo_se_ve_el_catalogo_propio(self):
        otra = crear_negocio("Fredonia")
        Producto.objects.create(
            licorera=otra, categoria=Categoria.objects.filter(licorera=otra).first(),
            nombre="Ajeno", presentacion=Producto.Presentacion.BOTELLA,
            precio_venta=1000, stock_minimo=1)

        nombres = [p["nombre"] for p in self.listar().json()["results"]]
        self.assertNotIn("Ajeno", nombres)
        self.assertEqual(len(nombres), 2)

    def test_busca_por_nombre(self):
        resultados = self.listar(buscar="águila").json()["results"]
        self.assertEqual([p["nombre"] for p in resultados], ["Cerveza Águila 330 ml"])

    def test_busca_por_categoria(self):
        resultados = self.listar(buscar="Ron").json()["results"]
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0]["categoria_nombre"], "Ron")

    def test_busca_por_codigo_de_barras(self):
        resultados = self.listar(buscar="7700000000001").json()["results"]
        self.assertEqual(len(resultados), 1)

    def test_filtra_por_estado(self):
        self.aguila.activo = False
        self.aguila.save(update_fields=["activo"])

        activos = self.listar(estado="activo").json()["results"]
        inactivos = self.listar(estado="inactivo").json()["results"]

        self.assertEqual(len(activos), 1)
        self.assertEqual(len(inactivos), 1)
        self.assertEqual(inactivos[0]["nombre"], "Cerveza Águila 330 ml")

    def test_sin_filtro_salen_los_dos_estados(self):
        self.aguila.activo = False
        self.aguila.save(update_fields=["activo"])
        self.assertEqual(len(self.listar().json()["results"]), 2)


class EdicionYBajaTests(CatalogoBase):
    """RF-INV-03 y RF-INV-04."""

    def setUp(self):
        super().setUp()
        self.producto = Producto.objects.create(
            licorera=self.licorera, categoria=self.categoria,
            nombre="Ron Medellín Añejo 750 ml",
            presentacion=Producto.Presentacion.BOTELLA,
            precio_venta=48500, stock_minimo=5)

    def test_se_edita_el_precio(self):
        respuesta = self.client.patch(
            reverse("producto-detail", args=[self.producto.id]),
            {"precio_venta": "52000.00"},
            content_type="application/json", **self.entrar())

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.producto.refresh_from_db()
        self.assertEqual(str(self.producto.precio_venta), "52000.00")

    def test_no_se_edita_un_producto_de_otra_licorera(self):
        otra = crear_negocio("Guarne")
        ajeno = Producto.objects.create(
            licorera=otra, categoria=Categoria.objects.filter(licorera=otra).first(),
            nombre="Ajeno", presentacion=Producto.Presentacion.BOTELLA,
            precio_venta=1000, stock_minimo=1)

        respuesta = self.client.patch(
            reverse("producto-detail", args=[ajeno.id]), {"precio_venta": "2000.00"},
            content_type="application/json", **self.entrar())
        self.assertEqual(respuesta.status_code, status.HTTP_404_NOT_FOUND)

    def test_inactivar_no_borra(self):
        respuesta = self.client.delete(
            reverse("producto-detail", args=[self.producto.id]), **self.entrar())

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.producto.refresh_from_db()
        self.assertFalse(self.producto.activo)


class QuienPuedeTocarElCatalogoTests(CatalogoBase):
    """El vendedor consulta; registrar es del administrador y de la cuenta al día."""

    def setUp(self):
        super().setUp()
        self.vendedor = crear_usuario(self.licorera, "vendedor@prueba.com", Rol.VENDEDOR)

    def test_el_vendedor_consulta_el_catalogo(self):
        """Lo necesita para vender, así que no se le cierra la consulta."""
        respuesta = self.client.get(reverse("producto-list"),
                                    **self.entrar(self.vendedor.correo))
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)

    def test_el_vendedor_no_registra_productos(self):
        cuerpo = {"nombre": "X", "categoria": self.categoria.id,
                  "presentacion": Producto.Presentacion.BOTELLA,
                  "precio_venta": "1000.00", "stock_minimo": 1}
        respuesta = self.client.post(reverse("producto-list"), cuerpo,
                                     content_type="application/json",
                                     **self.entrar(self.vendedor.correo))
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_el_permiso_de_escritura_sigue_enganchado(self):
        """
        Comprobar el 403 no basta: si alguien quitara el permiso de la vista, el
        403 desaparecería y con él la prueba que lo vigila.
        """
        from suscripciones.permissions import PuedeRegistrarOperaciones
        from .views import ProductoViewSet

        vista = ProductoViewSet()
        vista.request = type("P", (), {"method": "POST"})()
        self.assertIn(PuedeRegistrarOperaciones,
                      [type(p) for p in vista.get_permissions()])

    def test_con_la_suscripcion_vencida_no_se_registra(self):
        suscripcion = self.licorera.suscripcion_actual()
        suscripcion.fecha_fin = timezone.localdate() - timedelta(days=30)
        suscripcion.save(update_fields=["fecha_fin"])

        cuerpo = {"nombre": "X", "categoria": self.categoria.id,
                  "presentacion": Producto.Presentacion.BOTELLA,
                  "precio_venta": "1000.00", "stock_minimo": 1}
        respuesta = self.client.post(reverse("producto-list"), cuerpo,
                                     content_type="application/json", **self.entrar())
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_con_la_suscripcion_vencida_si_se_consulta(self):
        suscripcion = self.licorera.suscripcion_actual()
        suscripcion.fecha_fin = timezone.localdate() - timedelta(days=30)
        suscripcion.save(update_fields=["fecha_fin"])

        respuesta = self.client.get(reverse("producto-list"), **self.entrar())
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
