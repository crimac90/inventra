"""
Pruebas del catálogo de productos (RF-INV-01 a 04).

Se ejecutan con `py manage.py test inventario`.
"""

from datetime import timedelta

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from seguridad.models import Rol, Usuario
from suscripciones.models import Licorera, Plan, Suscripcion
from suscripciones.puesta_en_marcha import preparar_licorera_nueva

from sedes.models import Sede

from .existencias import existencias_de, existencias_totales
from .kardex import registrar_movimiento
from .models import Categoria, EntradaMercancia, LoteInventario, MovimientoInventario, Producto
from .operaciones import registrar_entrada
from .peps import consumir, costo_total

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


class EntradaDeMercanciaTests(CatalogoBase):
    """La llegada de mercancía y los lotes que crea (RF-INV-05)."""

    def setUp(self):
        super().setUp()
        self.ron = Producto.objects.create(
            licorera=self.licorera, categoria=self.categoria,
            nombre="Ron Medellín Añejo 750 ml",
            presentacion=Producto.Presentacion.BOTELLA,
            precio_venta=48500, stock_minimo=5)
        self.cerveza = Producto.objects.create(
            licorera=self.licorera,
            categoria=Categoria.objects.get(licorera=self.licorera, nombre="Cerveza"),
            nombre="Cerveza Águila 330 ml",
            presentacion=Producto.Presentacion.UNIDAD,
            precio_venta=3500, stock_minimo=24)
        self.sede = Sede.principal_de(self.licorera)

    def registrar(self, lineas=None, **extra):
        cuerpo = {
            "proveedor": "Distribuidora del Valle",
            "lineas": lineas if lineas is not None else [
                {"producto": self.ron.id, "cantidad": 12, "costo_unitario": "38000.00"},
                {"producto": self.cerveza.id, "cantidad": 48, "costo_unitario": "2100.00"},
            ],
        }
        cuerpo.update(extra)
        return self.client.post(reverse("entrada-list"), cuerpo,
                                content_type="application/json", **self.entrar())

    def test_cada_linea_crea_un_lote_con_su_costo(self):
        respuesta = self.registrar()

        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        entrada = EntradaMercancia.objects.get(id=respuesta.json()["id"])
        self.assertEqual(entrada.lotes.count(), 2)
        self.assertEqual(
            str(entrada.lotes.get(producto=self.ron).costo_unitario), "38000.00")
        self.assertEqual(
            str(entrada.lotes.get(producto=self.cerveza).costo_unitario), "2100.00")

    def test_la_entrada_sube_las_existencias(self):
        self.registrar()

        self.assertEqual(existencias_de(self.ron, self.sede), 12)
        self.assertEqual(existencias_de(self.cerveza, self.sede), 48)

    def test_la_mercancia_llega_a_la_sede_del_negocio(self):
        self.registrar()
        self.assertTrue(
            LoteInventario.objects.filter(producto=self.ron, sede=self.sede).exists())

    def test_cada_linea_deja_su_movimiento_en_el_kardex(self):
        self.registrar()

        movimientos = MovimientoInventario.objects.filter(producto=self.ron)
        self.assertEqual(movimientos.count(), 1)
        movimiento = movimientos.first()
        self.assertEqual(movimiento.tipo, MovimientoInventario.Tipo.ENTRADA)
        self.assertEqual(movimiento.cantidad, 12)
        self.assertEqual(movimiento.saldo_resultante, 12)
        self.assertEqual(movimiento.documento_tipo,
                         MovimientoInventario.Documento.ENTRADA)

    def test_el_saldo_del_kardex_acumula_entre_entradas(self):
        """
        El saldo resultante es una foto del DESPUÉS, no de la entrada suelta.
        Si se calculara antes de mover los lotes, la segunda entrada diría 12.
        """
        self.registrar(lineas=[{"producto": self.ron.id, "cantidad": 12,
                                "costo_unitario": "38000.00"}])
        self.registrar(lineas=[{"producto": self.ron.id, "cantidad": 6,
                                "costo_unitario": "42000.00"}])

        saldos = list(
            MovimientoInventario.objects.filter(producto=self.ron)
            .order_by("id").values_list("saldo_resultante", flat=True))
        self.assertEqual(saldos, [12, 18])

    def test_una_compra_posterior_no_cambia_el_costo_de_la_anterior(self):
        """
        El corazón del PEPS (RF-INV-10): cada lote conserva su costo real. Si el
        costo viviera en el producto, la segunda compra habría reescrito hacia
        atrás lo que costó la primera.
        """
        self.registrar(lineas=[{"producto": self.ron.id, "cantidad": 12,
                                "costo_unitario": "38000.00"}])
        self.registrar(lineas=[{"producto": self.ron.id, "cantidad": 6,
                                "costo_unitario": "42000.00"}])

        costos = [str(c) for c in LoteInventario.objects
                  .filter(producto=self.ron).order_by("id")
                  .values_list("costo_unitario", flat=True)]
        self.assertEqual(costos, ["38000.00", "42000.00"])

    def test_el_catalogo_muestra_las_existencias_derivadas(self):
        self.registrar()
        filas = {p["nombre"]: p["existencias"]
                 for p in self.client.get(reverse("producto-list"),
                                          **self.entrar()).json()["results"]}

        self.assertEqual(filas["Ron Medellín Añejo 750 ml"], 12)
        self.assertEqual(filas["Cerveza Águila 330 ml"], 48)

    def test_un_producto_sin_lotes_tiene_cero(self):
        """No es un vacío ni un error: es una referencia de la que no ha entrado nada."""
        filas = {p["nombre"]: p["existencias"]
                 for p in self.client.get(reverse("producto-list"),
                                          **self.entrar()).json()["results"]}
        self.assertEqual(filas["Ron Medellín Añejo 750 ml"], 0)

    # -- Lo que se rechaza ------------------------------------------------

    def test_una_entrada_sin_lineas_se_rechaza(self):
        self.assertEqual(self.registrar(lineas=[]).status_code,
                         status.HTTP_400_BAD_REQUEST)

    def test_el_mismo_producto_dos_veces_se_rechaza(self):
        respuesta = self.registrar(lineas=[
            {"producto": self.ron.id, "cantidad": 6, "costo_unitario": "38000.00"},
            {"producto": self.ron.id, "cantidad": 6, "costo_unitario": "39000.00"},
        ])
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_se_recibe_mercancia_de_un_producto_ajeno(self):
        otra = crear_negocio("Itagui")
        ajeno = Producto.objects.create(
            licorera=otra, categoria=Categoria.objects.filter(licorera=otra).first(),
            nombre="Ajeno", presentacion=Producto.Presentacion.BOTELLA,
            precio_venta=1000, stock_minimo=1)

        respuesta = self.registrar(lineas=[{"producto": ajeno.id, "cantidad": 1,
                                            "costo_unitario": "100.00"}])
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_la_cantidad_tiene_que_ser_positiva(self):
        respuesta = self.registrar(lineas=[{"producto": self.ron.id, "cantidad": 0,
                                            "costo_unitario": "38000.00"}])
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_el_costo_no_puede_ser_negativo(self):
        respuesta = self.registrar(lineas=[{"producto": self.ron.id, "cantidad": 1,
                                            "costo_unitario": "-5.00"}])
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_una_entrada_no_se_edita_ni_se_borra(self):
        """
        Lo que corrige una entrada equivocada es un ajuste con su motivo. Si se
        pudiera editar, el saldo guardado de los movimientos posteriores dejaría
        de cuadrar y el kardex mentiría sobre el pasado.
        """
        entrada = EntradaMercancia.objects.get(id=self.registrar().json()["id"])
        direccion = reverse("entrada-detail", args=[entrada.id])

        self.assertEqual(
            self.client.patch(direccion, {"proveedor": "Otro"},
                              content_type="application/json",
                              **self.entrar()).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(self.client.delete(direccion, **self.entrar()).status_code,
                         status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_solo_se_ven_las_entradas_propias(self):
        self.registrar()
        otra = crear_negocio("Jerico")
        ajena = crear_usuario(otra, "jerico@prueba.com", Rol.ADMINISTRADOR_LICORERA)

        propias = self.client.get(reverse("entrada-list"), **self.entrar()).json()
        ajenas = self.client.get(reverse("entrada-list"),
                                 **self.entrar(ajena.correo)).json()
        self.assertEqual(propias["count"], 1)
        self.assertEqual(ajenas["count"], 0)

    def test_el_vendedor_no_recibe_mercancia(self):
        vendedor = crear_usuario(self.licorera, "vendedor@prueba.com", Rol.VENDEDOR)
        respuesta = self.client.post(
            reverse("entrada-list"),
            {"lineas": [{"producto": self.ron.id, "cantidad": 1,
                         "costo_unitario": "100.00"}]},
            content_type="application/json", **self.entrar(vendedor.correo))
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_con_la_suscripcion_vencida_no_se_recibe_mercancia(self):
        suscripcion = self.licorera.suscripcion_actual()
        suscripcion.fecha_fin = timezone.localdate() - timedelta(days=30)
        suscripcion.save(update_fields=["fecha_fin"])

        self.assertEqual(self.registrar().status_code, status.HTTP_403_FORBIDDEN)

    # -- La operación, por dentro -----------------------------------------

    def test_si_una_linea_falla_no_queda_nada_a_medias(self):
        """
        La entrada es una transacción. Se llama a la operación directamente,
        saltándose el formulario, porque es ahí donde puede llegar una línea
        imposible: desde una carga de datos o desde el código de mañana.
        """
        with self.assertRaises(ValidationError):
            registrar_entrada(
                licorera=self.licorera, usuario=self.administrador,
                lineas=[
                    {"producto": self.ron, "cantidad": 10, "costo_unitario": 38000},
                    {"producto": self.cerveza, "cantidad": 5, "costo_unitario": -1},
                ])

        self.assertEqual(EntradaMercancia.objects.count(), 0)
        self.assertEqual(LoteInventario.objects.count(), 0)
        self.assertEqual(MovimientoInventario.objects.count(), 0)

    def test_sin_sede_no_se_puede_recibir(self):
        """
        No debería ocurrir —toda licorera nace con la suya (D-30)—, pero la
        operación lo comprueba en vez de dar por hecho que está.
        """
        huerfana = Licorera.objects.create(nombre="Sin sede", correo="sin@prueba.com")
        producto = Producto.objects.create(
            licorera=huerfana, categoria=Categoria.sembrar(huerfana)[0],
            nombre="X", presentacion=Producto.Presentacion.BOTELLA,
            precio_venta=1000, stock_minimo=1)

        with self.assertRaises(ValidationError):
            registrar_entrada(licorera=huerfana, usuario=self.administrador,
                              lineas=[{"producto": producto, "cantidad": 1,
                                       "costo_unitario": 100}])


class KardexTests(CatalogoBase):
    """La única puerta por la que se escribe un movimiento (RF-INV-09)."""

    def setUp(self):
        super().setUp()
        self.producto = Producto.objects.create(
            licorera=self.licorera, categoria=self.categoria, nombre="Ron",
            presentacion=Producto.Presentacion.BOTELLA,
            precio_venta=48500, stock_minimo=5)
        self.sede = Sede.principal_de(self.licorera)

    def movimiento(self, **cambios):
        datos = {
            "producto": self.producto, "sede": self.sede,
            "tipo": MovimientoInventario.Tipo.ENTRADA, "cantidad": 10,
            "usuario": self.administrador,
            "documento_tipo": MovimientoInventario.Documento.ENTRADA,
            "documento_id": 1,
        }
        datos.update(cambios)
        return registrar_movimiento(**datos)

    def test_el_signo_lo_pone_el_kardex_y_no_quien_llama(self):
        """
        Quien llama dice QUÉ pasó, no cómo se anota. Registrar una venta con
        cantidad positiva es un error fácil y silencioso —el saldo subiría—, y
        aquí no se puede cometer.
        """
        salida = self.movimiento(tipo=MovimientoInventario.Tipo.VENTA,
                                 documento_tipo=MovimientoInventario.Documento.VENTA,
                                 cantidad=4)
        self.assertEqual(salida.cantidad, -4)

    def test_la_cantidad_siempre_se_pide_en_positivo(self):
        with self.assertRaises(ValidationError):
            self.movimiento(cantidad=-3)
        with self.assertRaises(ValidationError):
            self.movimiento(cantidad=0)

    def test_un_ajuste_exige_motivo(self):
        with self.assertRaises(ValidationError):
            self.movimiento(tipo=MovimientoInventario.Tipo.AJUSTE_NEGATIVO,
                            documento_tipo=MovimientoInventario.Documento.AJUSTE,
                            cantidad=2)

    def test_un_ajuste_con_motivo_se_registra(self):
        anotado = self.movimiento(tipo=MovimientoInventario.Tipo.AJUSTE_POSITIVO,
                                  documento_tipo=MovimientoInventario.Documento.AJUSTE,
                                  cantidad=2, motivo="Conteo físico")
        self.assertEqual(anotado.motivo, "Conteo físico")

    def test_un_motivo_en_blanco_no_cuenta_como_motivo(self):
        with self.assertRaises(ValidationError):
            self.movimiento(tipo=MovimientoInventario.Tipo.AJUSTE_NEGATIVO,
                            documento_tipo=MovimientoInventario.Documento.AJUSTE,
                            cantidad=2, motivo="   ")

    def test_una_entrada_no_exige_motivo(self):
        """La contraparte, y la que impide pasarse de frenada."""
        self.assertIsNone(self.movimiento().motivo)


class PepsTests(CatalogoBase):
    """
    El consumo de lotes por antigüedad (RF-INV-10).

    Es la pieza con más riesgo del proyecto, así que se prueba sola y a fondo
    antes de que nadie la use: el punto de venta solo la va a llamar.
    """

    def setUp(self):
        super().setUp()
        self.producto = Producto.objects.create(
            licorera=self.licorera, categoria=self.categoria, nombre="Ron",
            presentacion=Producto.Presentacion.BOTELLA,
            precio_venta=48500, stock_minimo=5)
        self.sede = Sede.principal_de(self.licorera)

    def recibir(self, cantidad, costo):
        return registrar_entrada(
            licorera=self.licorera, usuario=self.administrador,
            lineas=[{"producto": self.producto, "cantidad": cantidad,
                     "costo_unitario": costo}])

    def sacar(self, cantidad, **cambios):
        datos = {
            "producto": self.producto, "sede": self.sede, "cantidad": cantidad,
            "tipo": MovimientoInventario.Tipo.VENTA,
            "usuario": self.administrador,
            "documento_tipo": MovimientoInventario.Documento.VENTA,
            "documento_id": 1,
        }
        datos.update(cambios)
        return consumir(**datos)

    def test_sale_del_lote_mas_antiguo(self):
        self.recibir(10, 38000)
        self.recibir(10, 42000)

        consumos = self.sacar(4)

        self.assertEqual(len(consumos), 1)
        self.assertEqual(consumos[0].cantidad, 4)
        self.assertEqual(consumos[0].costo_unitario, 38000)

    def test_una_salida_puede_cruzar_dos_lotes(self):
        """
        El caso que distingue un PEPS de una resta: doce unidades cuando el
        primer lote tiene diez salen de los dos, y cada tramo lleva su costo.
        """
        self.recibir(10, 38000)
        self.recibir(10, 42000)

        consumos = self.sacar(12)

        self.assertEqual([(c.cantidad, c.costo_unitario) for c in consumos],
                         [(10, 38000), (2, 42000)])
        self.assertEqual(costo_total(consumos), 10 * 38000 + 2 * 42000)

    def test_el_lote_agotado_queda_en_cero_y_no_se_borra(self):
        """Un lote vacío conserva su historia: el kardex lo sigue citando."""
        self.recibir(10, 38000)
        self.recibir(10, 42000)
        self.sacar(12)

        lotes = list(LoteInventario.objects.filter(producto=self.producto)
                     .order_by("id").values_list("cantidad_disponible", flat=True))
        self.assertEqual(lotes, [0, 8])

    def test_el_consumo_descuenta_las_existencias(self):
        self.recibir(10, 38000)
        self.sacar(3)
        self.assertEqual(existencias_de(self.producto, self.sede), 7)

    def test_no_se_puede_sacar_mas_de_lo_que_hay(self):
        self.recibir(5, 38000)

        with self.assertRaises(ValidationError):
            self.sacar(6)

    def test_si_no_alcanza_no_se_saca_nada(self):
        """
        La mitad que importa: un rechazo que hubiera vaciado el primer lote
        antes de darse cuenta dejaría el inventario peor que antes de pedir.
        """
        self.recibir(5, 38000)

        with self.assertRaises(ValidationError):
            self.sacar(6)

        self.assertEqual(existencias_de(self.producto, self.sede), 5)
        self.assertEqual(
            MovimientoInventario.objects.filter(
                tipo=MovimientoInventario.Tipo.VENTA).count(), 0)

    def test_sin_existencias_tampoco(self):
        with self.assertRaises(ValidationError):
            self.sacar(1)

    def test_la_cantidad_tiene_que_ser_positiva(self):
        self.recibir(5, 38000)
        with self.assertRaises(ValidationError):
            self.sacar(0)

    def test_cada_tramo_deja_su_propio_movimiento(self):
        """
        Un movimiento por lote y no uno por salida: un movimiento único no
        podría llevar costo, porque una salida que cruza dos compras no tiene
        un solo costo.
        """
        self.recibir(10, 38000)
        self.recibir(10, 42000)
        self.sacar(12)

        ventas = list(
            MovimientoInventario.objects
            .filter(tipo=MovimientoInventario.Tipo.VENTA)
            .order_by("id").values_list("cantidad", "costo_unitario", "saldo_resultante"))
        self.assertEqual(ventas, [(-10, 38000, 10), (-2, 42000, 8)])

    def test_corregir_el_costo_de_un_lote_no_cambia_lo_ya_salido(self):
        """
        La no retroactividad de RF-INV-10: el costo se copia al salir. La
        utilidad de un mes cerrado no cambia porque hoy se corrija una factura.
        """
        self.recibir(10, 38000)
        self.sacar(4)

        lote = LoteInventario.objects.get(producto=self.producto)
        lote.costo_unitario = 99000
        lote.save(update_fields=["costo_unitario"])

        movimiento = MovimientoInventario.objects.get(
            tipo=MovimientoInventario.Tipo.VENTA)
        self.assertEqual(movimiento.costo_unitario, 38000)

    def test_con_la_misma_fecha_desempata_el_orden_de_creacion(self):
        """
        Dos lotes pueden compartir la fecha de ingreso al microsegundo. Sin un
        segundo criterio, el orden de consumo lo decidiría la base ese día y la
        misma venta podría costar distinto cada vez. Aquí las fechas se igualan
        a mano para forzar el empate, que es difícil de provocar por azar y muy
        fácil de sufrir en producción.
        """
        self.recibir(5, 1000)
        self.recibir(5, 3000)

        primero = LoteInventario.objects.filter(producto=self.producto).order_by("id").first()
        LoteInventario.objects.filter(producto=self.producto).update(
            fecha_ingreso=primero.fecha_ingreso)

        consumos = self.sacar(7)
        self.assertEqual([(c.cantidad, c.costo_unitario) for c in consumos],
                         [(5, 1000), (2, 3000)])

    def test_el_peps_no_toca_los_lotes_de_otra_sede_ni_de_otro_producto(self):
        otro = Producto.objects.create(
            licorera=self.licorera, categoria=self.categoria, nombre="Otro",
            presentacion=Producto.Presentacion.BOTELLA,
            precio_venta=1000, stock_minimo=1)
        registrar_entrada(
            licorera=self.licorera, usuario=self.administrador,
            lineas=[{"producto": otro, "cantidad": 9, "costo_unitario": 500}])
        self.recibir(10, 38000)

        self.sacar(10)

        self.assertEqual(existencias_de(otro, self.sede), 9)


class ConsultaDelKardexTests(CatalogoBase):
    """El historial de una referencia (RF-INV-09)."""

    def setUp(self):
        super().setUp()
        self.producto = Producto.objects.create(
            licorera=self.licorera, categoria=self.categoria, nombre="Ron",
            presentacion=Producto.Presentacion.BOTELLA,
            precio_venta=48500, stock_minimo=5)
        self.sede = Sede.principal_de(self.licorera)
        registrar_entrada(
            licorera=self.licorera, usuario=self.administrador,
            lineas=[{"producto": self.producto, "cantidad": 10,
                     "costo_unitario": 38000}])

    def pedir(self, producto=None, correo=None):
        return self.client.get(
            reverse("producto-kardex", args=[(producto or self.producto).id]),
            **self.entrar(correo))

    def test_devuelve_los_movimientos_de_la_referencia(self):
        respuesta = self.pedir()

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        filas = respuesta.json()["results"]
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]["tipo"], MovimientoInventario.Tipo.ENTRADA)
        self.assertEqual(filas[0]["cantidad"], 10)
        self.assertEqual(filas[0]["saldo_resultante"], 10)

    def test_el_vendedor_puede_consultarlo(self):
        vendedor = crear_usuario(self.licorera, "vendedor@prueba.com", Rol.VENDEDOR)
        self.assertEqual(self.pedir(correo=vendedor.correo).status_code,
                         status.HTTP_200_OK)

    def test_no_se_ve_el_kardex_de_otra_licorera(self):
        otra = crear_negocio("Marinilla")
        ajeno = Producto.objects.create(
            licorera=otra, categoria=Categoria.objects.filter(licorera=otra).first(),
            nombre="Ajeno", presentacion=Producto.Presentacion.BOTELLA,
            precio_venta=1000, stock_minimo=1)

        self.assertEqual(self.pedir(producto=ajeno).status_code,
                         status.HTTP_404_NOT_FOUND)

    def test_el_kardex_es_de_solo_lectura(self):
        respuesta = self.client.post(
            reverse("producto-kardex", args=[self.producto.id]), {},
            content_type="application/json", **self.entrar())
        self.assertEqual(respuesta.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class AjusteDeExistenciasTests(CatalogoBase):
    """Merma, rotura y conteo físico (RF-INV-06)."""

    def setUp(self):
        super().setUp()
        self.producto = Producto.objects.create(
            licorera=self.licorera, categoria=self.categoria, nombre="Ron",
            presentacion=Producto.Presentacion.BOTELLA,
            precio_venta=48500, stock_minimo=5)
        self.sede = Sede.principal_de(self.licorera)
        registrar_entrada(
            licorera=self.licorera, usuario=self.administrador,
            lineas=[{"producto": self.producto, "cantidad": 10,
                     "costo_unitario": 38000}])

    def ajustar(self, cantidad, motivo="Conteo físico", producto=None, correo=None):
        return self.client.post(
            reverse("producto-ajustar", args=[(producto or self.producto).id]),
            {"cantidad": cantidad, "motivo": motivo},
            content_type="application/json", **self.entrar(correo))

    def test_un_ajuste_negativo_descuenta(self):
        respuesta = self.ajustar(-3, motivo="Dos botellas rotas y una vencida")

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(existencias_de(self.producto, self.sede), 7)

    def test_el_ajuste_negativo_toma_el_costo_del_lote(self):
        """
        Una merma vale lo que costó la mercancía perdida, no el precio al que
        se iba a vender. Por eso consume lotes como una venta.
        """
        self.ajustar(-3, motivo="Rotura")

        movimiento = MovimientoInventario.objects.get(
            tipo=MovimientoInventario.Tipo.AJUSTE_NEGATIVO)
        self.assertEqual(movimiento.costo_unitario, 38000)
        self.assertEqual(movimiento.cantidad, -3)
        self.assertEqual(movimiento.motivo, "Rotura")

    def test_no_se_puede_ajustar_por_debajo_de_cero(self):
        respuesta = self.ajustar(-11, motivo="Conteo")

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(existencias_de(self.producto, self.sede), 10)

    def test_un_ajuste_positivo_crea_un_lote_al_costo_del_ultimo(self):
        """
        D-32: unas unidades que aparecen en un conteo son mercancía ya
        comprada, y su costo más probable es el de la compra más reciente.
        """
        registrar_entrada(
            licorera=self.licorera, usuario=self.administrador,
            lineas=[{"producto": self.producto, "cantidad": 5,
                     "costo_unitario": 42000}])

        self.ajustar(3, motivo="Aparecieron en bodega")

        lote = LoteInventario.objects.get(
            origen=LoteInventario.Origen.AJUSTE_POSITIVO)
        self.assertEqual(lote.costo_unitario, 42000)
        self.assertEqual(lote.cantidad_disponible, 3)
        self.assertEqual(existencias_de(self.producto, self.sede), 18)

    def test_sin_una_compra_previa_el_ajuste_positivo_se_rechaza(self):
        """
        No se inventa un costo: lo que corresponde ahí es registrar la entrada
        con el costo real, y el mensaje lo dice.
        """
        nuevo = Producto.objects.create(
            licorera=self.licorera, categoria=self.categoria, nombre="Sin compras",
            presentacion=Producto.Presentacion.BOTELLA,
            precio_venta=1000, stock_minimo=1)

        respuesta = self.ajustar(5, motivo="Conteo", producto=nuevo)

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("entrada de mercancía", respuesta.json()["detalle"])
        self.assertEqual(existencias_totales(nuevo), 0)

    def test_el_ajuste_exige_motivo(self):
        self.assertEqual(self.ajustar(-1, motivo="   ").status_code,
                         status.HTTP_400_BAD_REQUEST)

    def test_un_ajuste_de_cero_se_rechaza(self):
        self.assertEqual(self.ajustar(0).status_code, status.HTTP_400_BAD_REQUEST)

    def test_el_vendedor_no_ajusta(self):
        vendedor = crear_usuario(self.licorera, "vendedor@prueba.com", Rol.VENDEDOR)
        self.assertEqual(self.ajustar(-1, correo=vendedor.correo).status_code,
                         status.HTTP_403_FORBIDDEN)

    def test_con_la_suscripcion_vencida_no_se_ajusta(self):
        suscripcion = self.licorera.suscripcion_actual()
        suscripcion.fecha_fin = timezone.localdate() - timedelta(days=30)
        suscripcion.save(update_fields=["fecha_fin"])

        self.assertEqual(self.ajustar(-1).status_code, status.HTTP_403_FORBIDDEN)

    def test_no_se_ajusta_un_producto_de_otra_licorera(self):
        otra = crear_negocio("Rionegro")
        ajeno = Producto.objects.create(
            licorera=otra, categoria=Categoria.objects.filter(licorera=otra).first(),
            nombre="Ajeno", presentacion=Producto.Presentacion.BOTELLA,
            precio_venta=1000, stock_minimo=1)

        self.assertEqual(self.ajustar(-1, producto=ajeno).status_code,
                         status.HTTP_404_NOT_FOUND)

    def test_el_ajuste_queda_en_el_kardex_con_su_motivo(self):
        self.ajustar(-2, motivo="Botellas rotas en el traslado")

        kardex = self.client.get(
            reverse("producto-kardex", args=[self.producto.id]),
            **self.entrar()).json()["results"]
        ultimo = [m for m in kardex
                  if m["tipo"] == MovimientoInventario.Tipo.AJUSTE_NEGATIVO][0]
        self.assertEqual(ultimo["motivo"], "Botellas rotas en el traslado")
        self.assertEqual(ultimo["saldo_resultante"], 8)


class NivelDeExistenciasTests(CatalogoBase):
    """El filtro por nivel (RF-INV-02) y la alerta del panel (RF-INV-07)."""

    def setUp(self):
        super().setUp()
        self.sede = Sede.principal_de(self.licorera)
        self.sobrado = self.crear_producto("Con existencias de sobra", minimo=5, entran=20)
        self.justo = self.crear_producto("En el mínimo", minimo=5, entran=5)
        self.bajo = self.crear_producto("Por debajo del mínimo", minimo=10, entran=3)
        self.agotado = self.crear_producto("Agotado", minimo=5, entran=0)

    def crear_producto(self, nombre, minimo, entran):
        producto = Producto.objects.create(
            licorera=self.licorera, categoria=self.categoria, nombre=nombre,
            presentacion=Producto.Presentacion.BOTELLA,
            precio_venta=1000, stock_minimo=minimo)
        if entran:
            registrar_entrada(
                licorera=self.licorera, usuario=self.administrador,
                lineas=[{"producto": producto, "cantidad": entran,
                         "costo_unitario": 500}])
        return producto

    def nombres(self, **filtros):
        respuesta = self.client.get(reverse("producto-list"), filtros, **self.entrar())
        return {fila["nombre"] for fila in respuesta.json()["results"]}

    def test_el_filtro_de_agotados_solo_trae_los_de_cero(self):
        self.assertEqual(self.nombres(existencias="agotado"), {"Agotado"})

    def test_el_filtro_de_bajos_no_incluye_los_agotados(self):
        """
        Agotado y bajo se separan a propósito: lo que ya no se puede vender es
        más urgente que lo que solo hay que reponer, y mezclarlos esconde lo
        primero entre lo segundo.
        """
        self.assertEqual(self.nombres(existencias="bajo"),
                         {"En el mínimo", "Por debajo del mínimo"})

    def test_el_que_esta_justo_en_el_minimo_cuenta_como_bajo(self):
        """«Igual o inferior», dice el requisito. El borde entra."""
        self.assertIn("En el mínimo", self.nombres(existencias="bajo"))

    def test_sin_filtro_salen_todos(self):
        self.assertEqual(len(self.nombres()), 4)

    def test_un_producto_sin_lotes_cuenta_como_agotado_y_no_desaparece(self):
        """
        La suma de un producto sin lotes está vacía, no es cero. Sin convertirla
        a cero, esta referencia se caería de la lista y del filtro.
        """
        self.assertIn("Agotado", self.nombres())
        self.assertIn("Agotado", self.nombres(existencias="agotado"))

    # -- La alerta del panel ----------------------------------------------

    def alertas(self, correo=None):
        return self.client.get(reverse("alertas-inventario"), **self.entrar(correo))

    def test_la_alerta_incluye_los_agotados(self):
        """
        El requisito dice «igual o inferior al mínimo», y cero lo es. Una
        referencia agotada es el caso más urgente del mismo problema.
        """
        nombres = [fila["nombre"] for fila in self.alertas().json()]
        self.assertEqual(set(nombres),
                         {"Agotado", "En el mínimo", "Por debajo del mínimo"})

    def test_la_alerta_ordena_por_lo_mas_urgente(self):
        existencias = [fila["existencias"] for fila in self.alertas().json()]
        self.assertEqual(existencias, sorted(existencias))

    def test_la_alerta_no_avisa_de_referencias_descontinuadas(self):
        """Avisar de reponer algo que ya no se vende es ruido, y el ruido se deja de leer."""
        self.agotado.activo = False
        self.agotado.save(update_fields=["activo"])

        nombres = [fila["nombre"] for fila in self.alertas().json()]
        self.assertNotIn("Agotado", nombres)

    def test_la_alerta_es_de_la_propia_licorera(self):
        otra = crear_negocio("Sabaneta")
        Producto.objects.create(
            licorera=otra, categoria=Categoria.objects.filter(licorera=otra).first(),
            nombre="Ajeno agotado", presentacion=Producto.Presentacion.BOTELLA,
            precio_venta=1000, stock_minimo=5)

        nombres = [fila["nombre"] for fila in self.alertas().json()]
        self.assertNotIn("Ajeno agotado", nombres)

    def test_el_vendedor_ve_las_alertas(self):
        """Es quien está en el mostrador y el primero que nota que algo se acabó."""
        vendedor = crear_usuario(self.licorera, "vendedor@prueba.com", Rol.VENDEDOR)
        self.assertEqual(self.alertas(correo=vendedor.correo).status_code,
                         status.HTTP_200_OK)
