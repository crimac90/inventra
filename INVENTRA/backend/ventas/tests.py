"""
Pruebas de los cimientos del módulo de ventas.

Se ejecutan con `py manage.py test ventas`.

Este bloque construye las tablas y la definición de jornada; la operación de
vender llega después. Lo que se comprueba aquí es lo que ninguna pantalla podrá
arreglar más tarde: que una venta de madrugada caiga en la jornada correcta, y
que la base impida por sí misma dos ventas con el mismo número o dos cierres de
la misma jornada.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

# El helper de INV en vez de uno propio: una licorera lista para trabajar se
# arma igual en los dos módulos, y VEN depende de INV de todas formas.
from django.core.exceptions import ValidationError

from inventario.existencias import existencias_de
from inventario.models import MovimientoInventario
from inventario.operaciones import registrar_entrada
from inventario.models import Categoria, Producto
from inventario.tests import crear_negocio, crear_usuario
from sedes.models import Sede
from seguridad.models import Rol

from .jornada import INICIO_DE_JORNADA, jornada_actual, jornada_de, limites_de
from .models import CierreCaja, DetalleVenta, MedioPago, Venta
from .operaciones import registrar_venta


def crear_producto(licorera, nombre, precio):
    """Una referencia del catálogo, sin existencias: esas entran con su compra."""
    return Producto.objects.create(
        licorera=licorera, categoria=Categoria.objects.filter(licorera=licorera).first(),
        nombre=nombre, presentacion=Producto.Presentacion.BOTELLA,
        precio_venta=Decimal(precio), stock_minimo=1)


def momento(dia, hora, minuto=0):
    """Un instante del 2026-10, con la zona horaria del proyecto."""
    return timezone.make_aware(
        datetime(2026, 10, dia, hora, minuto), timezone.get_current_timezone())


class JornadaTests(TestCase):
    """
    La definición de día del módulo (D-36).

    Es la pieza con más consecuencias del bloque: de ella dependen el cierre, el
    indicador del panel y el filtro del historial.
    """

    def test_la_tarde_y_la_noche_son_del_mismo_dia(self):
        self.assertEqual(jornada_de(momento(18, 19, 30)), date(2026, 10, 18))
        self.assertEqual(jornada_de(momento(18, 23, 59)), date(2026, 10, 18))

    def test_la_madrugada_pertenece_a_la_noche_anterior(self):
        """
        El caso que decidió D-36: el negocio abre el 18 a las 19:00 y cierra el
        19 a las 02:00. Esas dos horas se cierran con la noche en la que se
        vendieron, porque el cajón no se vacía a medianoche.
        """
        for hora in (0, 2, 5):
            self.assertEqual(jornada_de(momento(19, hora, 30)), date(2026, 10, 18),
                             "las %02d:30 deberían ser de la jornada del 18" % hora)

    def test_a_las_seis_empieza_la_jornada_nueva(self):
        self.assertEqual(jornada_de(momento(19, 5, 59)), date(2026, 10, 18))
        self.assertEqual(jornada_de(momento(19, 6, 0)), date(2026, 10, 19))

    def test_los_limites_cubren_veinticuatro_horas_sin_huecos(self):
        inicio, fin = limites_de(date(2026, 10, 18))

        self.assertEqual(timezone.localtime(inicio).time(), INICIO_DE_JORNADA)
        self.assertEqual(fin - inicio, timedelta(days=1))
        # El final es exclusivo: ya es de la jornada siguiente.
        self.assertEqual(jornada_de(fin), date(2026, 10, 19))
        self.assertEqual(jornada_de(fin - timedelta(seconds=1)), date(2026, 10, 18))

    def test_la_jornada_actual_sale_del_reloj(self):
        esperada = jornada_de(timezone.now())
        self.assertEqual(jornada_actual(), esperada)


class MediosDePagoTests(TestCase):
    def test_los_tres_del_requisito_se_siembran(self):
        self.assertEqual(set(MedioPago.objects.values_list("nombre", flat=True)),
                         set(MedioPago.POR_DEFECTO))

    def test_el_efectivo_se_reconoce_sin_comparar_textos_sueltos(self):
        efectivo = MedioPago.objects.get(nombre=MedioPago.EFECTIVO)
        tarjeta = MedioPago.objects.get(nombre=MedioPago.TARJETA)

        self.assertTrue(efectivo.es_efectivo)
        self.assertFalse(tarjeta.es_efectivo)


class VentaBase(TestCase):
    def setUp(self):
        self.licorera = crear_negocio("Envigado")
        self.sede = Sede.principal_de(self.licorera)
        self.usuario = crear_usuario(self.licorera, "cajero@prueba.com", Rol.VENDEDOR)
        self.efectivo = MedioPago.objects.get(nombre=MedioPago.EFECTIVO)

    def vender(self, consecutivo, total="10000", recibido=None, licorera=None):
        return Venta.objects.create(
            licorera=licorera or self.licorera, sede=self.sede, usuario=self.usuario,
            consecutivo=consecutivo, total=Decimal(total), medio_pago=self.efectivo,
            monto_recibido=None if recibido is None else Decimal(recibido))


class ConsecutivoTests(VentaBase):
    def test_no_se_repite_dentro_de_la_licorera(self):
        self.vender(1)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.vender(1)

    def test_dos_licoreras_tienen_cada_una_su_numero_uno(self):
        """
        El número es el que ve el negocio, no un identificador del sistema: dos
        licoreras distintas empiezan las dos por el uno.
        """
        otra = crear_negocio("Sabaneta")
        self.vender(1)
        self.vender(1, licorera=otra)

        self.assertEqual(Venta.objects.filter(consecutivo=1).count(), 2)


class CambioTests(VentaBase):
    def test_el_cambio_es_lo_recibido_menos_el_total(self):
        venta = self.vender(1, total="173500", recibido="200000")

        self.assertEqual(venta.cambio, Decimal("26500"))

    def test_sin_efectivo_recibido_no_hay_cambio_que_devolver(self):
        self.assertIsNone(self.vender(2, total="173500").cambio)


class CierreCajaTests(VentaBase):
    def cerrar(self, jornada, contado="100000", diferencia="0", observacion=None):
        return CierreCaja.objects.create(
            licorera=self.licorera, sede=self.sede, fecha=jornada,
            total_efectivo=Decimal("100000"), total_transferencia=Decimal("0"),
            total_tarjeta=Decimal("0"), efectivo_contado=Decimal(contado),
            diferencia=Decimal(diferencia), usuario=self.usuario,
            observacion=observacion)

    def test_una_sede_no_cierra_dos_veces_la_misma_jornada(self):
        self.cerrar(date(2026, 10, 18))

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.cerrar(date(2026, 10, 18))

    def test_la_misma_sede_cierra_jornadas_distintas(self):
        self.cerrar(date(2026, 10, 18))
        self.cerrar(date(2026, 10, 19))

        self.assertEqual(CierreCaja.objects.count(), 2)

    def test_una_diferencia_sin_explicar_es_la_que_el_panel_mantiene_a_la_vista(self):
        cierre = self.cerrar(date(2026, 10, 18), contado="92000", diferencia="-8000")

        self.assertTrue(cierre.hay_que_explicar)

    def test_explicarla_retira_el_aviso(self):
        cierre = self.cerrar(date(2026, 10, 18), contado="92000", diferencia="-8000",
                             observacion="Se pagó un domicilio con efectivo de la caja")

        self.assertFalse(cierre.hay_que_explicar)

    def test_un_cierre_cuadrado_no_pide_explicacion(self):
        self.assertFalse(self.cerrar(date(2026, 10, 18)).hay_que_explicar)

    def test_el_espacio_en_blanco_no_es_una_explicacion(self):
        cierre = self.cerrar(date(2026, 10, 18), contado="92000", diferencia="-8000",
                             observacion="   ")

        self.assertTrue(cierre.hay_que_explicar)


class RegistrarVentaTests(TestCase):
    """
    La operación central del módulo (RF-VEN-01 y RF-VEN-02).

    Lo que se comprueba aquí no es que la venta se guarde, sino que al guardarse
    el inventario quede diciendo lo mismo que la caja.
    """

    def setUp(self):
        self.licorera = crear_negocio("Itagüí")
        self.sede = Sede.principal_de(self.licorera)
        self.usuario = crear_usuario(self.licorera, "cajero@venta.com", Rol.VENDEDOR)
        self.efectivo = MedioPago.objects.get(nombre=MedioPago.EFECTIVO)
        self.tarjeta = MedioPago.objects.get(nombre=MedioPago.TARJETA)
        self.ron = crear_producto(self.licorera, "Ron de prueba", precio="46000")

    def comprar(self, cantidad, costo):
        """Una entrada de mercancía, que es la única forma de tener existencias."""
        return registrar_entrada(
            licorera=self.licorera, usuario=self.usuario,
            lineas=[{"producto": self.ron, "cantidad": cantidad,
                     "costo_unitario": Decimal(costo)}])

    def vender(self, cantidad=1, medio=None, recibido=None, producto=None):
        return registrar_venta(
            licorera=self.licorera, usuario=self.usuario, medio_pago=medio or self.efectivo,
            monto_recibido=None if recibido is None else Decimal(recibido),
            lineas=[{"producto": producto or self.ron, "cantidad": cantidad}])

    def test_la_venta_descuenta_las_existencias(self):
        self.comprar(10, "30000")

        self.vender(3)

        self.assertEqual(existencias_de(self.ron, self.sede), 7)

    def test_el_precio_se_congela_en_la_linea(self):
        """
        Cambiar mañana el precio del catálogo no puede cambiar lo que se cobró
        hoy. Es la otra mitad de RF-INV-03.
        """
        self.comprar(10, "30000")
        venta = self.vender(2)

        self.ron.precio_venta = Decimal("99000")
        self.ron.save(update_fields=["precio_venta"])

        linea = venta.lineas.get()
        self.assertEqual(linea.precio_unitario, Decimal("46000"))
        self.assertEqual(venta.total, Decimal("92000"))

    def test_una_venta_que_cruza_dos_lotes_sale_a_dos_costos(self):
        """
        El PEPS en una venta: cinco unidades del lote viejo y dos del nuevo,
        cada tramo con el costo de su compra. Un movimiento único no podría
        llevar costo, porque no hay un solo costo.
        """
        self.comprar(5, "30000")
        self.comprar(4, "35000")

        self.vender(7)

        salidas = (MovimientoInventario.objects
                   .filter(producto=self.ron,
                           tipo=MovimientoInventario.Tipo.VENTA)
                   .order_by("id"))
        self.assertEqual([(m.cantidad, m.costo_unitario) for m in salidas],
                         [(-5, Decimal("30000")), (-2, Decimal("35000"))])

    def test_el_kardex_apunta_a_la_venta_que_lo_causo(self):
        self.comprar(5, "30000")
        venta = self.vender(2)

        movimiento = MovimientoInventario.objects.get(
            producto=self.ron, tipo=MovimientoInventario.Tipo.VENTA)
        self.assertEqual(movimiento.documento_tipo,
                         MovimientoInventario.Documento.VENTA)
        self.assertEqual(movimiento.documento_id, venta.id)

    def test_sin_existencias_suficientes_no_se_vende_nada(self):
        """
        La venta entera se deshace: ni línea, ni movimiento, ni consecutivo
        gastado. Una venta a medias es peor que una venta rechazada.
        """
        self.comprar(3, "30000")

        with self.assertRaises(ValidationError):
            self.vender(5)

        self.assertEqual(Venta.objects.count(), 0)
        self.assertEqual(DetalleVenta.objects.count(), 0)
        self.assertEqual(existencias_de(self.ron, self.sede), 3)

    def test_no_se_vende_una_referencia_descontinuada(self):
        self.comprar(5, "30000")
        self.ron.activo = False
        self.ron.save(update_fields=["activo"])

        with self.assertRaises(ValidationError):
            self.vender(1)

    def test_no_se_vende_el_producto_de_otra_licorera(self):
        ajeno = crear_producto(crear_negocio("Bello"), "Ajeno", precio="1000")

        with self.assertRaises(ValidationError):
            self.vender(1, producto=ajeno)

    def test_una_venta_sin_lineas_se_rechaza(self):
        with self.assertRaises(ValidationError):
            registrar_venta(licorera=self.licorera, usuario=self.usuario,
                            medio_pago=self.efectivo, lineas=[])

    def test_el_consecutivo_avanza_de_uno_en_uno(self):
        self.comprar(10, "30000")

        self.assertEqual([self.vender().consecutivo for _ in range(3)], [1, 2, 3])

    def test_el_efectivo_recibido_tiene_que_alcanzar(self):
        self.comprar(5, "30000")

        with self.assertRaises(ValidationError):
            self.vender(1, recibido="10000")

        self.assertEqual(Venta.objects.count(), 0)

    def test_el_cambio_se_calcula_con_lo_recibido(self):
        self.comprar(5, "30000")

        venta = self.vender(1, recibido="50000")

        self.assertEqual(venta.cambio, Decimal("4000"))

    def test_pagar_justo_no_obliga_a_escribir_nada(self):
        self.comprar(5, "30000")

        self.assertIsNone(self.vender(1).cambio)

    def test_los_demas_medios_no_llevan_monto_recibido(self):
        """Un cambio calculado sobre una tarjeta sería dinero que nadie entregó."""
        self.comprar(5, "30000")

        with self.assertRaises(ValidationError):
            self.vender(1, medio=self.tarjeta, recibido="100000")
