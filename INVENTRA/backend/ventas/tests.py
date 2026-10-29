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
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

# El helper de INV en vez de uno propio: una licorera lista para trabajar se
# arma igual en los dos módulos, y VEN depende de INV de todas formas.
from io import StringIO

from django.core import mail
from django.core.management import call_command
from django.core.cache import cache
from django.core.exceptions import ValidationError

from inventario.existencias import existencias_de
from inventario.models import MovimientoInventario
from inventario.operaciones import registrar_entrada
from inventario.models import Categoria, LoteInventario, Producto
from inventario.tests import CLAVE, crear_negocio, crear_usuario
from sedes.models import Sede
from seguridad.models import Rol

from .caja import (cerrar_jornada, explicar_diferencia, jornadas_sin_cerrar,
                   jornadas_sin_explicar, ultimos_cierres,
                   resumen_de)
from .consultas import de_la_jornada, filtrar, resumen, utilidad_del_mes
from .jornada import INICIO_DE_JORNADA, jornada_actual, jornada_de, limites_de
from .rotacion import DIAS_POR_OMISION, dias_validos, sin_rotacion
from .models import CierreCaja, DetalleVenta, MedioPago, Venta
from .operaciones import anular_venta, registrar_venta, se_puede_anular


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
    La definición de día del módulo.

    Es la pieza con más consecuencias del bloque: de ella dependen el cierre, el
    indicador del panel y el filtro del historial.
    """

    def test_la_tarde_y_la_noche_son_del_mismo_dia(self):
        self.assertEqual(jornada_de(momento(18, 19, 30)), date(2026, 10, 18))
        self.assertEqual(jornada_de(momento(18, 23, 59)), date(2026, 10, 18))

    def test_la_madrugada_pertenece_a_la_noche_anterior(self):
        """
        El negocio abre el 18 a las 19:00 y cierra el 19 a las 02:00. Esas dos
        horas se cierran con la noche en la que se vendieron, porque el cajón
        no se vacía a medianoche.
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

    def test_no_se_vende_una_referencia_sin_precio(self):
        """
        El precio se fija al recibir la primera mercancía. Entre la creación de
        la ficha y esa entrada, la referencia existe pero no se cobra: venderla
        sacaría unidades del inventario sin que entrara nada en la caja.
        """
        self.comprar(5, "30000")
        self.ron.precio_venta = Decimal("0")
        self.ron.save(update_fields=["precio_venta"])

        with self.assertRaises(ValidationError):
            self.vender(1)

        self.assertEqual(Venta.objects.count(), 0)
        self.assertEqual(existencias_de(self.ron, self.sede), 5)

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


class AnularVentaTests(TestCase):
    """
    Deshacer una venta (RF-VEN-04).

    Lo que importa no es que la venta quede marcada, sino dónde vuelve la
    mercancía: si no volviera a su lote, el costo de lo devuelto dejaría de
    corresponder a la compra por la que entró.
    """

    def setUp(self):
        self.licorera = crear_negocio("La Estrella")
        self.sede = Sede.principal_de(self.licorera)
        self.usuario = crear_usuario(self.licorera, "cajero@anular.com", Rol.VENDEDOR)
        self.efectivo = MedioPago.objects.get(nombre=MedioPago.EFECTIVO)
        self.ron = crear_producto(self.licorera, "Ron de prueba", precio="46000")

    def comprar(self, cantidad, costo):
        return registrar_entrada(
            licorera=self.licorera, usuario=self.usuario,
            lineas=[{"producto": self.ron, "cantidad": cantidad,
                     "costo_unitario": Decimal(costo)}])

    def vender(self, cantidad):
        return registrar_venta(
            licorera=self.licorera, usuario=self.usuario, medio_pago=self.efectivo,
            lineas=[{"producto": self.ron, "cantidad": cantidad}])

    def anular(self, venta, motivo="El cliente devolvió la mercancía"):
        return anular_venta(venta=venta, usuario=self.usuario, motivo=motivo)

    def test_las_existencias_vuelven(self):
        self.comprar(10, "30000")
        venta = self.vender(4)

        self.anular(venta)

        self.assertEqual(existencias_de(self.ron, self.sede), 10)

    def test_cada_unidad_vuelve_al_lote_del_que_salio(self):
        """
        El corazón del requisito. La venta cruzó dos lotes; al anularla, cada
        uno recupera exactamente lo que puso, y no aparece un lote nuevo que se
        vendería después de lo comprado más tarde.
        """
        self.comprar(5, "30000")
        self.comprar(4, "35000")
        venta = self.vender(7)

        self.anular(venta)

        lotes = self.ron.lotes.order_by("fecha_ingreso", "id")
        self.assertEqual([l.cantidad_disponible for l in lotes], [5, 4])
        self.assertEqual(lotes.count(), 2)

    def test_lo_devuelto_vale_lo_que_valio_al_salir(self):
        self.comprar(5, "30000")
        self.comprar(4, "35000")
        venta = self.vender(7)

        self.anular(venta)

        vueltas = (MovimientoInventario.objects
                   .filter(tipo=MovimientoInventario.Tipo.ANULACION_VENTA)
                   .order_by("id"))
        self.assertEqual([(m.cantidad, m.costo_unitario) for m in vueltas],
                         [(5, Decimal("30000")), (2, Decimal("35000"))])

    def test_la_venta_no_se_borra(self):
        self.comprar(5, "30000")
        venta = self.vender(2)

        self.anular(venta, motivo="Se cobró de más")

        venta.refresh_from_db()
        self.assertEqual(venta.estado, Venta.Estado.ANULADA)
        self.assertEqual(venta.motivo_anulacion, "Se cobró de más")
        self.assertEqual(venta.consecutivo, 1)
        self.assertEqual(venta.lineas.count(), 1)

    def test_el_numero_no_se_reutiliza(self):
        """Un hueco o un número repetido impediría afirmar que no falta ninguna venta."""
        self.comprar(10, "30000")
        self.anular(self.vender(1))

        self.assertEqual(self.vender(1).consecutivo, 2)

    def test_no_se_anula_dos_veces(self):
        self.comprar(5, "30000")
        venta = self.vender(1)
        self.anular(venta)

        with self.assertRaises(ValidationError):
            self.anular(venta)

    def test_el_motivo_es_obligatorio(self):
        self.comprar(5, "30000")
        venta = self.vender(1)

        with self.assertRaises(ValidationError):
            self.anular(venta, motivo="   ")

        venta.refresh_from_db()
        self.assertEqual(venta.estado, Venta.Estado.ACTIVA)

    def test_no_se_anula_una_venta_de_otra_jornada(self):
        """
        Una venta de ayer ya entró en un cierre de caja cuadrado, y deshacerla
        descuadraría un día que alguien dio por bueno.
        """
        self.comprar(5, "30000")
        venta = self.vender(2)
        Venta.objects.filter(pk=venta.pk).update(
            fecha=timezone.now() - timedelta(days=2))
        venta.refresh_from_db()

        with self.assertRaises(ValidationError):
            self.anular(venta)

        self.assertEqual(existencias_de(self.ron, self.sede), 3)


class CajaBase(TestCase):
    def setUp(self):
        self.licorera = crear_negocio("Caldas")
        self.sede = Sede.principal_de(self.licorera)
        self.duena = crear_usuario(self.licorera, "duena@caja.com",
                                   Rol.ADMINISTRADOR_LICORERA)
        self.cajero = crear_usuario(self.licorera, "cajero@caja.com", Rol.VENDEDOR)
        self.efectivo = MedioPago.objects.get(nombre=MedioPago.EFECTIVO)
        self.tarjeta = MedioPago.objects.get(nombre=MedioPago.TARJETA)
        self.transferencia = MedioPago.objects.get(nombre=MedioPago.TRANSFERENCIA)
        self.ron = crear_producto(self.licorera, "Ron de caja", precio="50000")
        registrar_entrada(
            licorera=self.licorera, usuario=self.cajero,
            lineas=[{"producto": self.ron, "cantidad": 100,
                     "costo_unitario": Decimal("30000")}])
        mail.outbox = []

    def vender(self, cantidad=1, medio=None, cuando=None):
        venta = registrar_venta(
            licorera=self.licorera, usuario=self.cajero,
            medio_pago=medio or self.efectivo,
            lineas=[{"producto": self.ron, "cantidad": cantidad}])
        if cuando is not None:
            Venta.objects.filter(pk=venta.pk).update(fecha=cuando)
            venta.refresh_from_db()
        return venta

    def cerrar(self, contado, observacion=None):
        """
        Cierra la caja y deja salir el aviso.

        Los correos del módulo se mandan cuando la transacción confirma, para
        que un servidor de correo caído no deshaga la operación. Una prueba
        envuelve todo en una transacción que nunca confirma, así que sin esto
        la bandeja quedaría vacía y la prueba diría que el aviso no se manda
        cuando sí lo hace.
        """
        with self.captureOnCommitCallbacks(execute=True):
            return cerrar_jornada(
                licorera=self.licorera, usuario=self.cajero,
                efectivo_contado=Decimal(contado), observacion=observacion)

    def anular(self, venta, motivo="Devuelta", usuario=None):
        """Anula y deja salir el aviso, por lo mismo que `cerrar`."""
        with self.captureOnCommitCallbacks(execute=True):
            return anular_venta(venta=venta, usuario=usuario or self.duena,
                                motivo=motivo)


class ResumenDeLaJornadaTests(CajaBase):
    def test_los_tres_medios_salen_siempre_aunque_valgan_cero(self):
        """
        Un cierre que escondiera la fila de «tarjeta» porque hoy nadie pagó con
        tarjeta obligaría a mirar dos veces para saber si es cero o si falta.
        """
        self.vender(1)

        resumen = resumen_de(self.licorera, self.sede, jornada_actual())

        self.assertEqual(resumen["efectivo"], Decimal("50000"))
        self.assertEqual(resumen["transferencia"], Decimal("0"))
        self.assertEqual(resumen["tarjeta"], Decimal("0"))

    def test_cada_medio_suma_por_su_lado(self):
        self.vender(2)
        self.vender(1, medio=self.tarjeta)

        resumen = resumen_de(self.licorera, self.sede, jornada_actual())

        self.assertEqual(resumen["efectivo"], Decimal("100000"))
        self.assertEqual(resumen["tarjeta"], Decimal("50000"))
        self.assertEqual(resumen["transacciones"], 2)

    def test_una_venta_anulada_no_es_dinero(self):
        self.vender(1)
        anular_venta(venta=self.vender(1), usuario=self.duena, motivo="Se devolvió")

        resumen = resumen_de(self.licorera, self.sede, jornada_actual())

        self.assertEqual(resumen["efectivo"], Decimal("50000"))
        self.assertEqual(resumen["transacciones"], 1)

    def test_lo_vendido_de_madrugada_es_de_la_noche_anterior(self):
        """
        Lo mismo contado en dinero: la caja de las dos de la mañana pertenece
        a la jornada que se está cerrando, no a la siguiente.
        """
        anoche = jornada_actual() - timedelta(days=1)
        inicio, _ = limites_de(anoche)
        self.vender(1, cuando=inicio + timedelta(hours=15))   # 21:00
        self.vender(2, cuando=inicio + timedelta(hours=20))   # 02:00 del día siguiente

        resumen = resumen_de(self.licorera, self.sede, anoche)

        self.assertEqual(resumen["transacciones"], 2)
        self.assertEqual(resumen["efectivo"], Decimal("150000"))


class CerrarJornadaTests(CajaBase):
    def test_el_cierre_guarda_lo_que_dice_el_sistema_y_lo_contado(self):
        self.vender(2)

        cierre, creado = self.cerrar("100000")

        self.assertTrue(creado)
        self.assertEqual(cierre.total_efectivo, Decimal("100000"))
        self.assertEqual(cierre.efectivo_contado, Decimal("100000"))
        self.assertEqual(cierre.diferencia, Decimal("0"))

    def test_un_faltante_queda_en_negativo(self):
        self.vender(2)

        cierre, _ = self.cerrar("92000")

        self.assertEqual(cierre.diferencia, Decimal("-8000"))
        self.assertTrue(cierre.hay_que_explicar)

    def test_un_sobrante_queda_en_positivo(self):
        self.vender(2)

        self.assertEqual(self.cerrar("105000")[0].diferencia, Decimal("5000"))

    def test_lo_cobrado_por_tarjeta_no_entra_en_la_diferencia(self):
        """
        Solo se compara el efectivo: la tarjeta y la transferencia no pasan por
        el cajón. Una jornada cobrada entera con tarjeta se cuenta con cero en
        la caja y cuadra; restarla haría aparecer un faltante del tamaño de lo
        vendido y mandaría al administrador a buscar un dinero que nunca estuvo
        allí.
        """
        self.vender(2, medio=self.tarjeta)

        cierre, _ = self.cerrar("0")

        self.assertEqual(cierre.total_tarjeta, Decimal("100000"))
        self.assertEqual(cierre.diferencia, Decimal("0"))
        self.assertFalse(cierre.hay_que_explicar)

    def test_lo_cobrado_por_transferencia_tampoco_entra_en_la_diferencia(self):
        """
        Los dos medios que no pasan por el cajón se comprueban por separado:
        una prueba que solo mire la tarjeta deja la transferencia a oscuras.
        """
        self.vender(2, medio=self.transferencia)

        cierre, _ = self.cerrar("0")

        self.assertEqual(cierre.total_transferencia, Decimal("100000"))
        self.assertEqual(cierre.diferencia, Decimal("0"))
        self.assertFalse(cierre.hay_que_explicar)

    def test_con_los_tres_medios_solo_se_cuenta_el_efectivo(self):
        """El caso de verdad: una noche mezclada, donde la cuenta se puede errar."""
        self.vender(1)
        self.vender(2, medio=self.tarjeta)
        self.vender(3, medio=self.transferencia)

        cierre, _ = self.cerrar("50000")

        self.assertEqual(cierre.total_efectivo, Decimal("50000"))
        self.assertEqual(cierre.total_tarjeta, Decimal("100000"))
        self.assertEqual(cierre.total_transferencia, Decimal("150000"))
        self.assertEqual(cierre.diferencia, Decimal("0"))

    def test_rehacer_no_crea_otro_cierre_y_recalcula_entero(self):
        """
        Quien cierra antes de tiempo no se queda sin salida: se vuelve a cerrar
        y los totales se recalculan con toda la jornada, desde la primera
        venta. No hay saldo que venga del cierre anterior.
        """
        self.vender(2)
        self.cerrar("100000")

        self.vender(1)
        cierre, creado = self.cerrar("150000")

        self.assertFalse(creado)
        self.assertEqual(CierreCaja.objects.count(), 1)
        self.assertEqual(cierre.total_efectivo, Decimal("150000"))
        self.assertEqual(cierre.diferencia, Decimal("0"))

    def test_no_se_cierra_una_jornada_que_ya_termino(self):
        with self.assertRaises(ValidationError):
            cerrar_jornada(licorera=self.licorera, usuario=self.cajero,
                           efectivo_contado=Decimal("0"),
                           jornada=jornada_actual() - timedelta(days=1))

    def test_hay_que_contar_el_efectivo(self):
        with self.assertRaises(ValidationError):
            cerrar_jornada(licorera=self.licorera, usuario=self.cajero,
                           efectivo_contado=None)


class CerrarTardeTests(CajaBase):
    """
    Una jornada que nadie cerró se puede cerrar después, y el sistema no finge
    que es lo mismo.
    """

    def ayer(self):
        return jornada_actual() - timedelta(days=1)

    def vender_ayer(self, cantidad=2):
        inicio, _ = limites_de(self.ayer())
        return self.vender(cantidad, cuando=inicio + timedelta(hours=14))

    def test_sin_explicacion_no_se_cierra_tarde(self):
        """
        El cajón de esa noche ya se vació: la cifra que se escriba no es un
        conteo sino una decisión, y tiene que quedar dicho con qué criterio.
        """
        self.vender_ayer()

        with self.assertRaises(ValidationError):
            cerrar_jornada(licorera=self.licorera, usuario=self.duena,
                           efectivo_contado=Decimal("100000"), jornada=self.ayer())

    def test_con_explicacion_si_y_queda_a_nombre_de_quien_lo_hizo(self):
        self.vender_ayer()

        with self.captureOnCommitCallbacks(execute=True):
            cierre, creado = cerrar_jornada(
                licorera=self.licorera, usuario=self.duena,
                efectivo_contado=Decimal("100000"), jornada=self.ayer(),
                observacion="El vendedor no cerró; se asume lo que dice el sistema")

        self.assertTrue(creado)
        self.assertEqual(cierre.fecha, self.ayer())
        self.assertEqual(cierre.usuario, self.duena)

    def test_rehacer_la_jornada_en_curso_no_pide_explicacion(self):
        """Ahí el cajón sigue delante: contar otra vez es contar, no decidir."""
        self.vender(2)

        cierre, _ = self.cerrar("100000")

        self.assertIsNone(cierre.observacion)

    def test_no_se_cierra_una_jornada_que_no_ha_ocurrido(self):
        with self.assertRaises(ValidationError):
            cerrar_jornada(licorera=self.licorera, usuario=self.duena,
                           efectivo_contado=Decimal("1"),
                           jornada=jornada_actual() + timedelta(days=1),
                           observacion="Mañana")


class JornadasSinCerrarTests(CajaBase):
    """RF-VEN-06: una noche que nadie contó no deja fila que mirar."""

    def ayer(self):
        return jornada_actual() - timedelta(days=1)

    def vender_ayer(self, cantidad=2):
        inicio, _ = limites_de(self.ayer())
        return self.vender(cantidad, cuando=inicio + timedelta(hours=14))

    def test_una_jornada_con_ventas_y_sin_cierre_sale_en_la_lista(self):
        self.vender_ayer()

        pendientes = jornadas_sin_cerrar(self.licorera, self.sede)

        self.assertEqual(len(pendientes), 1)
        self.assertEqual(pendientes[0]["fecha"], self.ayer())
        self.assertEqual(pendientes[0]["transacciones"], 1)
        self.assertEqual(pendientes[0]["total"], Decimal("100000"))

    def test_la_jornada_en_curso_no_sale(self):
        """Todavía está a tiempo: avisar sería avisar de algo que no ha pasado."""
        self.vender(1)

        self.assertEqual(jornadas_sin_cerrar(self.licorera, self.sede), [])

    def test_una_jornada_ya_cerrada_no_sale(self):
        self.vender_ayer()
        cerrar_jornada(licorera=self.licorera, usuario=self.duena,
                       efectivo_contado=Decimal("100000"), jornada=self.ayer(),
                       observacion="Cerrada tarde")

        self.assertEqual(jornadas_sin_cerrar(self.licorera, self.sede), [])

    def test_una_jornada_sin_ventas_no_sale(self):
        """El negocio no abrió: no hay caja que contar."""
        self.assertEqual(jornadas_sin_cerrar(self.licorera, self.sede), [])

    def test_los_ultimos_cierres_salen_del_mas_reciente_al_mas_antiguo(self):
        self.vender_ayer()
        cerrar_jornada(licorera=self.licorera, usuario=self.duena,
                       efectivo_contado=Decimal("100000"), jornada=self.ayer(),
                       observacion="Cerrada tarde")
        self.vender(1)
        self.cerrar("50000")

        fechas = [c.fecha for c in ultimos_cierres(self.licorera)]

        self.assertEqual(fechas, [jornada_actual(), self.ayer()])

    def test_la_jornada_que_se_esta_mirando_no_sale_entre_las_anteriores(self):
        """
        La pantalla la enseña arriba, con sus totales de ahora; abajo saldría
        con los que tenía al cerrarse, que no son los mismos si después se
        vendió más. Las dos cifras son correctas y juntas parecen un error.
        """
        self.vender_ayer()
        cerrar_jornada(licorera=self.licorera, usuario=self.duena,
                       efectivo_contado=Decimal("100000"), jornada=self.ayer(),
                       observacion="Cerrada tarde")
        self.vender(1)
        self.cerrar("50000")

        fechas = [c.fecha for c in ultimos_cierres(self.licorera,
                                                   excepto=jornada_actual())]

        self.assertEqual(fechas, [self.ayer()])


class AvisoDeDiferenciaTests(CajaBase):
    def test_un_faltante_avisa_por_correo_al_administrador(self):
        self.vender(2)

        self.cerrar("92000")

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.duena.correo])
        self.assertIn("Faltan", mail.outbox[0].body)

    def test_una_jornada_cuadrada_no_molesta_a_nadie(self):
        """Un correo que llega todos los días deja de leerse."""
        self.vender(2)

        self.cerrar("100000")

        self.assertEqual(mail.outbox, [])

    def test_el_correo_lleva_la_explicacion_que_se_escribio(self):
        """
        Quien cierra puede escribir cualquier cosa, y el administrador tiene que
        poder juzgarla sin entrar al sistema.
        """
        self.vender(2)

        self.cerrar("92000", observacion="Se pagó un domicilio con la caja")

        self.assertIn("Se pagó un domicilio con la caja", mail.outbox[0].body)

    def test_sin_explicacion_el_correo_lo_dice(self):
        self.vender(2)

        self.cerrar("92000")

        self.assertIn("No se escribió ninguna explicación", mail.outbox[0].body)

    def test_el_vendedor_que_cerro_no_recibe_el_aviso(self):
        self.vender(2)

        self.cerrar("92000")

        self.assertNotIn(self.cajero.correo, mail.outbox[0].to)


class AvisoDeAnulacionTests(CajaBase):
    def test_anular_avisa_por_correo_al_administrador(self):
        """
        Una anulación no deja rastro en el cierre, y el historial solo la
        enseña a quien va a buscarla.
        """
        venta = self.vender(2)

        self.anular(venta, "El cliente devolvió todo")

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.duena.correo])
        self.assertIn("#%s" % venta.consecutivo, mail.outbox[0].body)
        self.assertIn("El cliente devolvió todo", mail.outbox[0].body)

    def test_la_venta_guarda_quien_la_anulo_y_cuando(self):
        """
        El motivo sin su autor no sirve para rendir cuentas: el historial
        podría decir por qué se deshizo una venta y no quién la deshizo.
        """
        venta = self.vender(1)

        anular_venta(venta=venta, usuario=self.duena, motivo="Devuelta")

        venta.refresh_from_db()
        self.assertEqual(venta.anulada_por, self.duena)
        self.assertIsNotNone(venta.fecha_anulacion)

    def test_quien_anula_no_es_quien_cobro(self):
        """Anular es del administrador y cobrar del vendedor: son dos datos."""
        venta = self.vender(1)

        anular_venta(venta=venta, usuario=self.duena, motivo="Devuelta")

        venta.refresh_from_db()
        self.assertEqual(venta.usuario, self.cajero)
        self.assertNotEqual(venta.anulada_por, venta.usuario)

    def test_una_venta_activa_no_tiene_quien_la_anulo(self):
        venta = self.vender(1)

        self.assertIsNone(venta.anulada_por)
        self.assertIsNone(venta.fecha_anulacion)

    def test_el_correo_dice_quien_registro_la_venta_y_quien_la_anulo(self):
        """Son dos personas distintas y el correo existe para poder juzgarlo."""
        self.anular(self.vender(1))

        cuerpo = mail.outbox[0].body
        self.assertIn("La registró: %s" % self.cajero.nombre_completo, cuerpo)
        self.assertIn("La anuló: %s" % self.duena.nombre_completo, cuerpo)

    def test_una_venta_que_no_se_anula_no_avisa(self):
        self.vender(2)

        self.assertEqual(mail.outbox, [])

    def test_un_rechazo_no_manda_correo(self):
        """Si la anulación no ocurrió, no hay nada de qué avisar."""
        venta = self.vender(1)
        self.anular(venta)
        mail.outbox = []

        with self.assertRaises(ValidationError):
            self.anular(venta, "Otra vez")

        self.assertEqual(mail.outbox, [])


class ExplicarDiferenciaTests(CajaBase):
    def test_mientras_no_se_explique_la_jornada_sigue_a_la_vista(self):
        self.vender(2)
        self.cerrar("92000")

        self.assertEqual(len(jornadas_sin_explicar(self.licorera)), 1)

    def test_explicarla_la_retira(self):
        self.vender(2)
        cierre, _ = self.cerrar("92000")

        explicar_diferencia(cierre=cierre, texto="Se pagó un domicilio")

        self.assertEqual(len(jornadas_sin_explicar(self.licorera)), 0)

    def test_se_puede_explicar_despues_de_cerrada_la_jornada(self):
        """Es una nota, no una cifra: no mueve ningún total ni la diferencia."""
        self.vender(2)
        cierre, _ = self.cerrar("92000")
        CierreCaja.objects.filter(pk=cierre.pk).update(
            fecha=jornada_actual() - timedelta(days=3))
        cierre.refresh_from_db()

        explicar_diferencia(cierre=cierre, texto="Apareció el billete")

        cierre.refresh_from_db()
        self.assertEqual(cierre.diferencia, Decimal("-8000"))
        self.assertFalse(cierre.hay_que_explicar)

    def test_una_explicacion_vacia_no_vale(self):
        self.vender(2)
        cierre, _ = self.cerrar("92000")

        with self.assertRaises(ValidationError):
            explicar_diferencia(cierre=cierre, texto="   ")

    def test_una_jornada_cuadrada_nunca_esta_a_la_vista(self):
        self.vender(2)
        self.cerrar("100000")

        self.assertEqual(len(jornadas_sin_explicar(self.licorera)), 0)


class HistorialTests(CajaBase):
    def test_el_historial_si_muestra_las_anuladas(self):
        """Una venta que desaparece deja un hueco que nadie puede explicar."""
        self.vender(1)
        anular_venta(venta=self.vender(1), usuario=self.duena, motivo="Devuelta")

        self.assertEqual(filtrar(self.licorera).count(), 2)

    def test_filtra_por_vendedor(self):
        self.vender(1)

        self.assertEqual(filtrar(self.licorera, vendedor=self.cajero).count(), 1)
        self.assertEqual(filtrar(self.licorera, vendedor=self.duena).count(), 0)

    def test_filtra_por_medio_de_pago(self):
        self.vender(1)
        self.vender(1, medio=self.tarjeta)

        self.assertEqual(filtrar(self.licorera, medio_pago=self.tarjeta).count(), 1)

    def test_busca_por_numero_de_venta(self):
        self.vender(1)
        segunda = self.vender(1)

        encontradas = filtrar(self.licorera, buscar=str(segunda.consecutivo))
        self.assertEqual([v.id for v in encontradas], [segunda.id])

    def test_busca_por_nombre_de_producto(self):
        self.vender(1)

        self.assertEqual(filtrar(self.licorera, buscar="caja").count(), 1)
        self.assertEqual(filtrar(self.licorera, buscar="whisky").count(), 0)

    def test_el_rango_de_fechas_va_por_jornadas(self):
        """
        Buscar «el día 18» tiene que traer la venta de las dos de la madrugada
        del 19, porque se vendió en la noche del 18.
        """
        anoche = jornada_actual() - timedelta(days=1)
        inicio, _ = limites_de(anoche)
        self.vender(1, cuando=inicio + timedelta(hours=20))   # 02:00 del día siguiente

        self.assertEqual(filtrar(self.licorera, desde=anoche, hasta=anoche).count(), 1)

    def test_solo_las_ventas_de_la_propia_licorera(self):
        otra = crear_negocio("Copacabana")
        self.vender(1)

        self.assertEqual(filtrar(otra).count(), 0)


class ResumenDelHistorialTests(CajaBase):
    def test_lo_anulado_se_cuenta_aparte_y_no_resta_de_lo_vendido(self):
        """
        Son dos hechos distintos —lo que se vendió y lo que hubo que
        deshacer—, y mezclarlos escondería justo el que conviene mirar.
        """
        self.vender(1)
        self.vender(2)
        anular_venta(venta=self.vender(1), usuario=self.duena, motivo="Devuelta")

        cifras = resumen(filtrar(self.licorera))

        self.assertEqual(cifras["vendido"], Decimal("150000"))
        self.assertEqual(cifras["transacciones"], 2)
        self.assertEqual(cifras["anuladas"], 1)
        self.assertEqual(cifras["valor_anulado"], Decimal("50000"))

    def test_la_venta_promedio_sale_de_las_activas(self):
        self.vender(1)
        self.vender(3)

        self.assertEqual(resumen(filtrar(self.licorera))["promedio"], Decimal("100000"))

    def test_un_periodo_sin_ventas_da_ceros_y_no_se_cae(self):
        """Dividir entre ninguna transacción es el caso de la licorera que abre hoy."""
        cifras = resumen(filtrar(self.licorera))

        self.assertEqual(cifras["vendido"], Decimal("0"))
        self.assertEqual(cifras["promedio"], Decimal("0"))

    def test_el_resumen_respeta_los_filtros_de_la_tabla(self):
        self.vender(1)
        self.vender(1, medio=self.tarjeta)

        cifras = resumen(filtrar(self.licorera, medio_pago=self.tarjeta))

        self.assertEqual(cifras["transacciones"], 1)


class NotaDeLaVentaTests(CajaBase):
    def test_la_nota_se_guarda_con_la_venta(self):
        """El negocio también sirve mesas: «mesa 1, pedido 3» identifica la venta."""
        venta = registrar_venta(
            licorera=self.licorera, usuario=self.cajero, medio_pago=self.efectivo,
            lineas=[{"producto": self.ron, "cantidad": 1}],
            observacion="Mesa 1, pedido 3")

        venta.refresh_from_db()
        self.assertEqual(venta.observacion, "Mesa 1, pedido 3")

    def test_una_venta_de_mostrador_no_lleva_nota(self):
        """Es opcional, y un espacio en blanco no es una nota."""
        venta = registrar_venta(
            licorera=self.licorera, usuario=self.cajero, medio_pago=self.efectivo,
            lineas=[{"producto": self.ron, "cantidad": 1}], observacion="   ")

        self.assertIsNone(venta.observacion)

    def test_el_buscador_del_historial_encuentra_la_nota(self):
        """Una nota que no se puede buscar no sirve para reconocer nada."""
        registrar_venta(
            licorera=self.licorera, usuario=self.cajero, medio_pago=self.efectivo,
            lineas=[{"producto": self.ron, "cantidad": 1}], observacion="Mesa 4")
        self.vender(1)

        self.assertEqual(filtrar(self.licorera, buscar="mesa 4").count(), 1)

    def test_buscar_por_producto_sigue_funcionando(self):
        """La nota se suma al buscador, no lo sustituye."""
        registrar_venta(
            licorera=self.licorera, usuario=self.cajero, medio_pago=self.efectivo,
            lineas=[{"producto": self.ron, "cantidad": 1}], observacion="Mesa 4")

        self.assertEqual(filtrar(self.licorera, buscar="caja").count(), 1)


class SePuedeAnularTests(CajaBase):
    def test_una_venta_de_la_jornada_en_curso_si(self):
        self.assertTrue(se_puede_anular(self.vender(1)))

    def test_una_venta_ya_anulada_no(self):
        venta = self.vender(1)
        anular_venta(venta=venta, usuario=self.duena, motivo="Devuelta")

        self.assertFalse(se_puede_anular(venta))

    def test_una_venta_de_una_jornada_anterior_no(self):
        """Esa venta ya entró en un cierre que alguien dio por bueno."""
        anoche = jornada_actual() - timedelta(days=1)
        inicio, _ = limites_de(anoche)

        self.assertFalse(se_puede_anular(self.vender(1, cuando=inicio + timedelta(hours=14))))


class RotacionTests(CajaBase):
    """RF-INV-08: qué referencias llevan un plazo sin venderse."""

    def catalogo(self):
        return Producto.objects.filter(licorera=self.licorera, activo=True)

    def test_una_referencia_recien_vendida_no_esta_estancada(self):
        self.vender(1)

        estancadas = sin_rotacion(self.catalogo(), self.licorera, 60)

        self.assertNotIn(self.ron, estancadas)

    def test_una_referencia_que_nunca_se_vendio_si(self):
        """Una que nadie ha comprado es el caso más claro de estancada."""
        quieto = crear_producto(self.licorera, "Whisky que nadie pide", precio="200000")

        self.assertIn(quieto, sin_rotacion(self.catalogo(), self.licorera, 60))

    def test_una_venta_vieja_no_la_salva(self):
        self.vender(1, cuando=timezone.now() - timedelta(days=90))

        self.assertIn(self.ron, sin_rotacion(self.catalogo(), self.licorera, 60))

    def test_una_venta_anulada_no_cuenta_como_venta(self):
        """
        Si contara, la referencia que solo aparece en ventas deshechas se
        escondería, y es justo la que se quiere encontrar.
        """
        anular_venta(venta=self.vender(1), usuario=self.duena, motivo="Devuelta")

        self.assertIn(self.ron, sin_rotacion(self.catalogo(), self.licorera, 60))

    def test_el_plazo_cambia_la_respuesta(self):
        self.vender(1, cuando=timezone.now() - timedelta(days=45))

        self.assertIn(self.ron, sin_rotacion(self.catalogo(), self.licorera, 30))
        self.assertNotIn(self.ron, sin_rotacion(self.catalogo(), self.licorera, 60))

    def test_un_plazo_mayor_nunca_devuelve_mas_que_uno_menor(self):
        """
        Las tres listas se contienen unas a otras: lo que lleva noventa días
        quieto lleva también sesenta y treinta. Por eso los tres plazos pueden
        devolver exactamente lo mismo sin que el filtro falle —significa que
        ninguna referencia tiene su ultima venta entre esos dos puntos—.
        """
        self.vender(1, cuando=timezone.now() - timedelta(days=45))
        crear_producto(self.licorera, "Whisky que nadie pide", precio="200000")

        a_30 = set(sin_rotacion(self.catalogo(), self.licorera, 30))
        a_60 = set(sin_rotacion(self.catalogo(), self.licorera, 60))
        a_90 = set(sin_rotacion(self.catalogo(), self.licorera, 90))

        self.assertTrue(a_90 <= a_60 <= a_30)
        self.assertIn(self.ron, a_30)
        self.assertNotIn(self.ron, a_60)

    def test_un_plazo_imposible_no_rompe_la_consulta(self):
        """La pantalla se abre igual y enseña la pregunta que sí sabe contestar."""
        self.assertEqual(dias_validos("45"), DIAS_POR_OMISION)
        self.assertEqual(dias_validos("ayer"), DIAS_POR_OMISION)
        self.assertEqual(dias_validos(None), DIAS_POR_OMISION)
        self.assertEqual(dias_validos("30"), 30)


class UtilidadDelMesTests(CajaBase):
    def test_la_utilidad_descuenta_el_costo_del_lote(self):
        """
        Se vende a 50.000 lo que costó 30.000: la utilidad es la diferencia, y
        el costo sale del kardex y no del catálogo.
        """
        self.vender(2)

        cifras = utilidad_del_mes(self.licorera)

        self.assertEqual(cifras["vendido"], Decimal("100000"))
        self.assertEqual(cifras["costo"], Decimal("60000"))
        self.assertEqual(cifras["utilidad"], Decimal("40000"))

    def test_una_venta_anulada_no_deja_utilidad(self):
        anular_venta(venta=self.vender(2), usuario=self.duena, motivo="Devuelta")

        self.assertEqual(utilidad_del_mes(self.licorera)["utilidad"], Decimal("0"))

    def test_un_mes_sin_ventas_no_se_cae(self):
        self.assertEqual(utilidad_del_mes(self.licorera)["utilidad"], Decimal("0"))


class ApiBase(TestCase):
    """Las direcciones del módulo, recorridas como las recorre la pantalla."""

    def setUp(self):
        cache.clear()
        self.licorera = crear_negocio("Rionegro")
        self.sede = Sede.principal_de(self.licorera)
        self.duena = crear_usuario(self.licorera, "duena@api.com",
                                   Rol.ADMINISTRADOR_LICORERA)
        self.cajero = crear_usuario(self.licorera, "cajero@api.com", Rol.VENDEDOR)
        self.efectivo = MedioPago.objects.get(nombre=MedioPago.EFECTIVO)
        self.ron = crear_producto(self.licorera, "Ron de api", precio="50000")
        registrar_entrada(
            licorera=self.licorera, usuario=self.duena,
            lineas=[{"producto": self.ron, "cantidad": 50,
                     "costo_unitario": Decimal("30000")}])
        mail.outbox = []

    def entrar(self, correo=None):
        respuesta = self.client.post(
            reverse("ingresar"),
            {"correo": correo or self.cajero.correo, "password": CLAVE},
            content_type="application/json")
        return {"HTTP_AUTHORIZATION": "Bearer %s" % respuesta.json()["acceso"]}

    def cobrar(self, cantidad=1, correo=None, **extra):
        cuerpo = {"medio_pago_id": self.efectivo.id,
                  "lineas": [{"producto_id": self.ron.id, "cantidad": cantidad}]}
        cuerpo.update(extra)
        return self.client.post(reverse("venta-list"), cuerpo,
                                content_type="application/json", **self.entrar(correo))


class ApiDeVentaTests(ApiBase):
    def test_el_vendedor_cobra(self):
        """
        Es la primera vez que un permiso reparte en esta dirección: vender es
        del vendedor, y lo que el administrador se reserva es deshacer.
        """
        respuesta = self.cobrar(2)

        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Decimal(respuesta.json()["total"]), Decimal("100000"))
        self.assertEqual(existencias_de(self.ron, self.sede), 48)

    def test_el_precio_no_se_recibe_del_cliente(self):
        """Aceptarlo permitiría cobrar lo que quisiera quien tenga la pantalla."""
        respuesta = self.cobrar(1, lineas=[{"producto_id": self.ron.id,
                                            "cantidad": 1, "precio_unitario": "1"}])

        self.assertEqual(Decimal(respuesta.json()["total"]), Decimal("50000"))

    def test_dos_lineas_del_mismo_producto_se_juntan(self):
        """Pulsar dos veces el mismo producto es «dos unidades», no «dos renglones»."""
        respuesta = self.cobrar(lineas=[{"producto_id": self.ron.id, "cantidad": 1},
                                        {"producto_id": self.ron.id, "cantidad": 2}])

        cuerpo = respuesta.json()
        self.assertEqual(len(cuerpo["lineas"]), 1)
        self.assertEqual(cuerpo["lineas"][0]["cantidad"], 3)

    def test_un_producto_de_otra_licorera_se_rechaza_como_dato_invalido(self):
        ajeno = crear_producto(crear_negocio("Guarne"), "Ajeno", precio="1000")

        respuesta = self.cobrar(lineas=[{"producto_id": ajeno.id, "cantidad": 1}])

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_sin_existencias_responde_cuantas_hay(self):
        respuesta = self.cobrar(80)

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("50", respuesta.json()["detalle"])

    def test_el_comprobante_trae_el_cambio(self):
        respuesta = self.cobrar(1, monto_recibido="60000")

        self.assertEqual(Decimal(respuesta.json()["cambio"]), Decimal("10000"))


class SuscripcionYOperacionesTests(ApiBase):
    """
    RF-SUS-03 visto desde el modulo que lo sufre: una cuenta suspendida deja
    consultar y no deja registrar.

    La regla no vive en estas vistas sino en un permiso compartido, y por eso
    mismo hace falta comprobarla aqui: lo que se verifica no es el permiso, que
    ya tiene sus pruebas, sino que las direcciones de ventas lo lleven puesto.
    Un permiso correcto que nadie engancha no protege nada.
    """

    def suspender(self):
        from suscripciones.models import Suscripcion
        (Suscripcion.objects
         .filter(licorera=self.licorera)
         .update(estado=Suscripcion.Estado.SUSPENDIDA))

    def test_una_cuenta_suspendida_no_puede_cobrar(self):
        self.suspender()

        respuesta = self.cobrar(1)

        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_una_cuenta_suspendida_si_puede_consultar(self):
        """Media frase del requisito es que consultar se pueda siempre."""
        self.cobrar(1)
        self.suspender()

        respuesta = self.client.get(reverse("venta-list"), **self.entrar())

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(respuesta.json()["count"], 1)

    def test_una_cuenta_suspendida_no_puede_anular(self):
        venta = self.cobrar(1).json()
        self.suspender()

        respuesta = self.client.post(
            reverse("venta-anular", args=[venta["id"]]), {"motivo": "Devuelta"},
            content_type="application/json", **self.entrar(self.duena.correo))

        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_una_cuenta_suspendida_no_puede_cerrar_la_caja(self):
        self.cobrar(1)
        self.suspender()

        respuesta = self.client.post(
            reverse("cierre-de-caja"), {"efectivo_contado": "50000"},
            content_type="application/json", **self.entrar())

        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)


class ApiDeAnulacionTests(ApiBase):
    def anular(self, venta_id, correo, motivo="El cliente devolvió la mercancía"):
        return self.client.post(
            reverse("venta-anular", args=[venta_id]), {"motivo": motivo},
            content_type="application/json", **self.entrar(correo))

    def test_el_administrador_anula(self):
        venta = self.cobrar(2).json()

        respuesta = self.anular(venta["id"], self.duena.correo)

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(respuesta.json()["estado"], "anulada")
        self.assertEqual(existencias_de(self.ron, self.sede), 50)

    def test_un_correo_caido_no_deshace_la_anulacion(self):
        """
        Con el aviso dentro de la transacción, un correo caído deshacía la
        anulación entera y la mercancía no volvía al inventario.
        """
        venta = self.cobrar(2).json()

        with override_settings(
                EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
                EMAIL_HOST="127.0.0.1", EMAIL_PORT=1):
            with self.assertLogs("ventas.correo", level="ERROR") as registrado:
                with self.captureOnCommitCallbacks(execute=True):
                    respuesta = self.anular(venta["id"], self.duena.correo)

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(respuesta.json()["estado"], "anulada")
        self.assertEqual(existencias_de(self.ron, self.sede), 50)
        self.assertIn("No se pudo enviar el aviso", registrado.output[0])

    def test_el_vendedor_no_anula_su_propio_cobro(self):
        venta = self.cobrar(2).json()

        respuesta = self.anular(venta["id"], self.cajero.correo)

        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(existencias_de(self.ron, self.sede), 48)

    def test_el_motivo_es_obligatorio(self):
        venta = self.cobrar(1).json()

        respuesta = self.anular(venta["id"], self.duena.correo, motivo="")

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)


class ApiDelHistorialTests(ApiBase):
    def listar(self, **filtros):
        return self.client.get(reverse("venta-list"), filtros, **self.entrar())

    def test_el_vendedor_consulta_el_historial(self):
        self.cobrar(1)

        respuesta = self.listar()

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(respuesta.json()["count"], 1)

    def test_la_lista_no_trae_el_detalle_de_cada_venta(self):
        """Son cientos de filas y nadie las mira hasta que abre una."""
        self.cobrar(1)

        self.assertNotIn("lineas", self.listar().json()["results"][0])

    def test_abrir_una_venta_si_trae_sus_lineas(self):
        venta = self.cobrar(2).json()

        respuesta = self.client.get(reverse("venta-detail", args=[venta["id"]]),
                                    **self.entrar())

        self.assertEqual(len(respuesta.json()["lineas"]), 1)

    def test_el_filtro_de_fechas_funciona_desde_la_direccion(self):
        """
        Las fechas llegan como texto y la consulta las espera como jornadas.
        Sin traducirlas la pantalla no filtra: se rompe.
        """
        self.cobrar(1)
        hoy = jornada_actual()

        respuesta = self.listar(desde=hoy.isoformat(), hasta=hoy.isoformat())

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(respuesta.json()["count"], 1)

    def test_el_filtro_de_fechas_deja_fuera_lo_de_otra_jornada(self):
        """Filtrar y no filtrar no pueden dar lo mismo."""
        self.cobrar(1)
        manana = (jornada_actual() + timedelta(days=1)).isoformat()

        self.assertEqual(self.listar(desde=manana).json()["count"], 0)

    def test_una_fecha_ilegible_se_avisa_y_no_devuelve_todo(self):
        """
        Devolver el historial entero con los filtros puestos en la pantalla
        haría creer a quien mira que está viendo un período.
        """
        self.cobrar(1)

        for valor in ("ayer", "2026-02-31"):
            respuesta = self.listar(desde=valor)

            self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("aaaa-mm-dd", respuesta.json()["detalle"])

    def test_no_se_ven_las_ventas_de_otra_licorera(self):
        self.cobrar(1)
        ajena = crear_negocio("Marinilla")
        intrusa = crear_usuario(ajena, "ajena@api.com", Rol.ADMINISTRADOR_LICORERA)

        respuesta = self.client.get(reverse("venta-list"), **self.entrar(intrusa.correo))

        self.assertEqual(respuesta.json()["count"], 0)


    def test_la_pagina_trae_los_totales_del_periodo(self):
        """
        La tabla y los indicadores salen de la misma consulta: separarlos
        admitiría que llegaran de dos momentos distintos y no concordaran.
        """
        self.cobrar(1)
        self.cobrar(2)

        cuerpo = self.listar().json()

        self.assertEqual(Decimal(cuerpo["resumen"]["vendido"]), Decimal("150000"))
        self.assertEqual(cuerpo["resumen"]["transacciones"], 2)

    def test_los_totales_hablan_del_periodo_y_no_de_la_pagina(self):
        """
        Con veinticinco filas a la vista, un total sacado de ellas hablaría de
        veinticinco ventas mientras el encabezado anuncia el mes entero.
        """
        # Se registran por la operación y no por la API: veintisiete cobros son
        # veintisiete ingresos de sesión, y el límite de intentos los corta.
        for _ in range(27):
            registrar_venta(licorera=self.licorera, usuario=self.cajero,
                            medio_pago=self.efectivo,
                            lineas=[{"producto": self.ron, "cantidad": 1}])

        cuerpo = self.listar().json()

        self.assertEqual(len(cuerpo["results"]), 25)
        self.assertEqual(cuerpo["resumen"]["transacciones"], 27)

    def test_la_nota_viaja_desde_la_pantalla_y_vuelve_en_el_comprobante(self):
        respuesta = self.cobrar(1, observacion="Mesa 2, pedido 1")

        self.assertEqual(respuesta.json()["observacion"], "Mesa 2, pedido 1")

    def test_la_fila_dice_si_la_venta_admite_anulacion(self):
        """La pantalla no sabe a qué hora empieza la jornada: lo pregunta."""
        self.cobrar(1)

        self.assertTrue(self.listar().json()["results"][0]["se_puede_anular"])


    def test_el_comprobante_dice_de_que_negocio_es(self):
        """Es el papel con el que el cliente reclama: tiene que decir ante quién."""
        venta = self.cobrar(1).json()

        self.assertEqual(venta["licorera_nombre"], self.licorera.nombre)

    def test_la_fila_del_historial_dice_a_que_jornada_pertenece(self):
        """
        Es lo que explica que dos ventas del mismo día del calendario no
        ofrezcan lo mismo: la de madrugada es de la noche anterior.
        """
        self.cobrar(1)

        fila = self.client.get(reverse("venta-list"), **self.entrar()).json()["results"][0]

        self.assertEqual(fila["jornada"], jornada_actual().isoformat())


class ApiDelCierreTardioTests(ApiBase):
    def cerrar(self, correo=None, **cuerpo):
        datos = {"efectivo_contado": "92000"}
        datos.update(cuerpo)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(reverse("cierre-de-caja"), datos,
                                    content_type="application/json",
                                    **self.entrar(correo))

    def test_el_vendedor_no_cierra_una_jornada_anterior(self):
        """
        Cerrar su turno sí; decidir la cifra de una noche que ya nadie puede
        contar, no.
        """
        ayer = (jornada_actual() - timedelta(days=1)).isoformat()

        respuesta = self.cerrar(jornada=ayer, observacion="Quedó sin cerrar")

        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_el_administrador_si(self):
        self.cobrar(2)
        ayer = (jornada_actual() - timedelta(days=1)).isoformat()

        respuesta = self.cerrar(self.duena.correo, jornada=ayer,
                                observacion="El vendedor no cerró")

        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(respuesta.json()["fecha"], ayer)

    def test_el_vendedor_sigue_cerrando_su_turno(self):
        self.cobrar(2)

        respuesta = self.cerrar()

        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)


class ApiDelResumenTests(ApiBase):
    def resumen(self, correo=None):
        return self.client.get(reverse("resumen-de-ventas"), **self.entrar(correo))

    def test_el_panel_recibe_lo_vendido_en_la_jornada(self):
        self.cobrar(2)

        cuerpo = self.resumen().json()

        self.assertEqual(Decimal(cuerpo["vendido_en_la_jornada"]), Decimal("100000"))
        self.assertEqual(cuerpo["transacciones_de_la_jornada"], 1)

    def test_el_panel_recibe_la_utilidad_del_mes(self):
        self.cobrar(2)

        self.assertEqual(Decimal(self.resumen().json()["utilidad_del_mes"]),
                         Decimal("40000"))

    def test_el_vendedor_no_recibe_las_jornadas_sin_explicar(self):
        """
        No puede escribir la explicación —esa es media razón de que el aviso
        exista—, de modo que enseñárselo sería ponerle delante algo que no
        puede resolver.
        """
        self.assertEqual(self.resumen().json()["jornadas_sin_explicar"], [])

    def test_el_administrador_si_las_recibe(self):
        self.cobrar(2)
        self.client.post(reverse("cierre-de-caja"), {"efectivo_contado": "92000"},
                         content_type="application/json", **self.entrar())

        cuerpo = self.resumen(self.duena.correo).json()

        self.assertEqual(len(cuerpo["jornadas_sin_explicar"]), 1)
        self.assertEqual(Decimal(cuerpo["jornadas_sin_explicar"][0]["diferencia"]),
                         Decimal("-8000"))


class ApiDelCierreTests(ApiBase):
    def test_se_puede_mirar_una_jornada_anterior(self):
        """
        Es por donde se llega desde el aviso del panel a una caja que cerró
        descuadrada hace días.
        """
        anoche = jornada_actual() - timedelta(days=1)

        respuesta = self.client.get(reverse("cierre-de-caja"),
                                    {"jornada": anoche.isoformat()}, **self.entrar())

        self.assertEqual(respuesta.json()["jornada"], anoche.isoformat())
        self.assertFalse(respuesta.json()["en_curso"])

    def test_la_pantalla_no_repite_abajo_la_jornada_que_ensena_arriba(self):
        self.cobrar()
        self.client.post(reverse("cierre-de-caja"), {"efectivo_contado": "50000"},
                         content_type="application/json", **self.entrar())

        datos = self.client.get(reverse("cierre-de-caja"), **self.entrar()).json()

        self.assertIsNotNone(datos["cierre"])
        self.assertEqual([c["fecha"] for c in datos["anteriores"]], [])

    def test_sin_jornada_en_la_direccion_se_mira_la_de_hoy(self):
        respuesta = self.client.get(reverse("cierre-de-caja"), **self.entrar())

        self.assertEqual(respuesta.json()["jornada"], jornada_actual().isoformat())
        self.assertTrue(respuesta.json()["en_curso"])

    def test_una_fecha_ilegible_no_impide_abrir_la_pantalla(self):
        respuesta = self.client.get(reverse("cierre-de-caja"),
                                    {"jornada": "el martes"}, **self.entrar())

        self.assertEqual(respuesta.json()["jornada"], jornada_actual().isoformat())

    def test_antes_de_cerrar_dice_lo_que_el_sistema_sabe(self):
        self.cobrar(2)

        cuerpo = self.client.get(reverse("cierre-de-caja"), **self.entrar()).json()

        self.assertEqual(Decimal(cuerpo["total_efectivo"]), Decimal("100000"))
        self.assertEqual(cuerpo["transacciones"], 1)
        self.assertIsNone(cuerpo["cierre"])

    def test_cerrar_con_faltante_avisa_por_correo(self):
        self.cobrar(2)

        # El aviso sale al confirmar la transacción, que es lo que impide que
        # un correo caído deje la caja sin cerrar.
        with self.captureOnCommitCallbacks(execute=True):
            respuesta = self.client.post(
                reverse("cierre-de-caja"), {"efectivo_contado": "92000"},
                content_type="application/json", **self.entrar())

        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Decimal(respuesta.json()["diferencia"]), Decimal("-8000"))
        self.assertEqual(mail.outbox[0].to, [self.duena.correo])

    def test_un_correo_caido_no_impide_cerrar_la_caja(self):
        """
        El fallo que lo motivó: con un servidor de correo que no responde, la
        operación entera se deshacía y la pantalla recibía un error del
        servidor que no explicaba nada. Un aviso es la consecuencia de algo
        que ya ocurrió, no parte de ello.
        """
        self.cobrar(2)

        with override_settings(
                EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
                EMAIL_HOST="127.0.0.1", EMAIL_PORT=1):
            # `assertLogs` hace dos cosas a la vez: comprueba que el fallo
            # quedó registrado, que es la otra mitad de la promesa —no se
            # tumba la operación, pero tampoco se calla—, y se queda con el
            # rastro en vez de dejar que lo escupa por consola en cada
            # ejecución de la batería.
            with self.assertLogs("ventas.correo", level="ERROR") as registrado:
                with self.captureOnCommitCallbacks(execute=True):
                    respuesta = self.client.post(
                        reverse("cierre-de-caja"), {"efectivo_contado": "92000"},
                        content_type="application/json", **self.entrar())

        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertTrue(CierreCaja.objects.filter(licorera=self.licorera).exists())
        self.assertIn("No se pudo enviar el aviso", registrado.output[0])

    def test_volver_a_cerrar_actualiza_el_mismo_cierre(self):
        self.cobrar(2)
        self.client.post(reverse("cierre-de-caja"), {"efectivo_contado": "100000"},
                         content_type="application/json", **self.entrar())

        self.cobrar(1)
        respuesta = self.client.post(
            reverse("cierre-de-caja"), {"efectivo_contado": "150000"},
            content_type="application/json", **self.entrar())

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(CierreCaja.objects.count(), 1)

    def test_el_administrador_explica_una_diferencia(self):
        self.cobrar(2)
        cierre = self.client.post(
            reverse("cierre-de-caja"), {"efectivo_contado": "92000"},
            content_type="application/json", **self.entrar()).json()

        respuesta = self.client.patch(
            reverse("explicacion-del-cierre", args=[cierre["id"]]),
            {"observacion": "Se pagó un domicilio"},
            content_type="application/json", **self.entrar(self.duena.correo))

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(len(jornadas_sin_explicar(self.licorera)), 0)

    def test_el_vendedor_no_explica_la_diferencia_que_el_mismo_dejo(self):
        self.cobrar(2)
        cierre = self.client.post(
            reverse("cierre-de-caja"), {"efectivo_contado": "92000"},
            content_type="application/json", **self.entrar()).json()

        respuesta = self.client.patch(
            reverse("explicacion-del-cierre", args=[cierre["id"]]),
            {"observacion": "Nada que ver aquí"},
            content_type="application/json", **self.entrar())

        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_los_medios_de_pago_se_consultan(self):
        respuesta = self.client.get(reverse("medios-de-pago"), **self.entrar())

        self.assertEqual([m["nombre"] for m in respuesta.json()],
                         list(MedioPago.POR_DEFECTO))


class DatosDemoDeVentasTests(TestCase):
    """
    La carga de ventas de demostración (bloque de cierre de VEN).

    No se comprueba venta por venta: eso sería escribir dos veces la misma
    lista. Se comprueba lo que tiene que ser cierto el día de la demostración
    —que el inventario siga cuadrado después de vender, que estén los casos
    que las pantallas necesitan enseñar y que repetir la orden no duplique
    nada—, que es lo mismo que se le pidió al catálogo.
    """

    def cargar(self):
        # El modo de depuración está apagado durante las pruebas, así que la
        # orden pide que se le insista.
        call_command("cargar_datos_demo", "--si-estoy-seguro", stdout=StringIO())

    def licorera_principal(self):
        from suscripciones.models import Licorera
        return Licorera.objects.get(correo__startswith="contacto@")

    def test_quedan_ventas_repartidas_en_varias_jornadas(self):
        """Un historial de un solo día no tiene nada que filtrar."""
        self.cargar()

        ventas = Venta.objects.filter(licorera=self.licorera_principal())
        jornadas = {jornada_de(v.fecha) for v in ventas}

        self.assertGreater(ventas.count(), 20)
        self.assertGreaterEqual(len(jornadas), 7)

    def test_ninguna_existencia_queda_en_negativo(self):
        """
        Lo que de verdad importa: las ventas consumieron lotes de verdad, y si
        el juego de datos pidiera más unidades de las que compró, el inventario
        quedaría diciendo una imposibilidad.
        """
        self.cargar()

        negativos = LoteInventario.objects.filter(
            producto__licorera=self.licorera_principal(),
            cantidad_disponible__lt=0)

        self.assertFalse(negativos.exists())

    def test_cada_existencia_cuadra_con_el_ultimo_saldo_del_kardex(self):
        """
        Las existencias se derivan de los lotes y el saldo es una foto que el
        kardex guardó al escribir cada movimiento. Si después de veinticinco
        ventas las dos cifras siguen coincidiendo en todas las referencias, es
        que nada entró por un atajo.
        """
        self.cargar()
        licorera = self.licorera_principal()
        sede = Sede.principal_de(licorera)

        for producto in Producto.objects.filter(licorera=licorera):
            ultimo = (MovimientoInventario.objects
                      .filter(producto=producto).order_by("id").last())
            if ultimo is None:
                continue
            self.assertEqual(
                existencias_de(producto, sede), ultimo.saldo_resultante,
                "«%s» no cuadra con su kardex" % producto.nombre)

    def test_hay_una_venta_anulada_con_su_autor(self):
        """El historial necesita enseñar el estado anulado, no solo el activo."""
        self.cargar()

        anulada = Venta.objects.filter(
            licorera=self.licorera_principal(), estado=Venta.Estado.ANULADA).first()

        self.assertIsNotNone(anulada)
        self.assertTrue(anulada.motivo_anulacion)
        self.assertIsNotNone(anulada.anulada_por)
        self.assertIsNotNone(anulada.fecha_anulacion)

    def test_hay_ventas_de_madrugada_en_la_jornada_de_la_noche_anterior(self):
        """
        Sin una venta pasada la medianoche, la definición de día del módulo
        está construida y no se ve en ninguna pantalla.
        """
        self.cargar()

        de_madrugada = [
            v for v in Venta.objects.filter(licorera=self.licorera_principal())
            if timezone.localtime(v.fecha).hour < INICIO_DE_JORNADA.hour
        ]

        self.assertTrue(de_madrugada)
        for venta in de_madrugada:
            self.assertEqual(jornada_de(venta.fecha),
                             timezone.localtime(venta.fecha).date() - timedelta(days=1))

    def test_una_caja_quedo_cerrada_con_diferencia_sin_explicar(self):
        """Es lo que mantiene vivo el aviso del panel: sin ella no se ve."""
        self.cargar()
        licorera = self.licorera_principal()

        sin_explicar = list(jornadas_sin_explicar(licorera))

        self.assertEqual(len(sin_explicar), 1)
        self.assertLess(sin_explicar[0].diferencia, 0)

    def test_hay_otra_caja_con_su_diferencia_ya_explicada(self):
        """Los dos estados, para poder comparar el resuelto con el pendiente."""
        self.cargar()

        explicados = CierreCaja.objects.filter(
            licorera=self.licorera_principal()).exclude(observacion=None)

        self.assertEqual(explicados.count(), 1)

    def test_la_jornada_en_curso_queda_abierta(self):
        """
        Quien recorra el sistema tiene que tener una caja que cerrar. Una ya
        cerrada obligaría a rehacerla para ver la pantalla funcionar.
        """
        self.cargar()
        licorera = self.licorera_principal()

        cerrada_hoy = CierreCaja.objects.filter(
            licorera=licorera, fecha=jornada_actual()).exists()

        self.assertFalse(cerrada_hoy)
        self.assertTrue(
            de_la_jornada(licorera, Sede.principal_de(licorera), jornada_actual()).exists(),
            "la jornada en curso quedó sin ninguna venta")

    def test_hay_ventas_con_nota_de_mesa(self):
        """La nota con la que un lico-bar reconoce una venta de mesa."""
        self.cargar()

        con_nota = Venta.objects.filter(
            licorera=self.licorera_principal()).exclude(observacion=None)

        self.assertTrue(con_nota.exists())

    def test_el_segundo_negocio_no_vende(self):
        """
        Un historial vacío enseña el aislamiento mejor que dos llenos: con los
        dos vendiendo habría que mirar dos veces para saber de quién es cada
        cifra.
        """
        self.cargar()
        from suscripciones.models import Licorera
        vecino = Licorera.objects.get(correo__startswith="contacto.vecino@")

        self.assertFalse(Venta.objects.filter(licorera=vecino).exists())

    def test_cargar_dos_veces_no_duplica_las_ventas(self):
        self.cargar()
        cuantas = Venta.objects.count()

        self.cargar()

        self.assertEqual(Venta.objects.count(), cuantas)

    def test_la_carga_no_manda_correos(self):
        """
        Una anulación avisa y un cierre descuadrado también. Cargar datos de
        demostración no es un día de trabajo: con un servidor de correo de
        verdad configurado, la carga escribiría a los administradores por
        ventas inventadas.
        """
        mail.outbox = []

        self.cargar()

        self.assertEqual(mail.outbox, [])

    def test_limpiar_retira_las_ventas_y_los_cierres(self):
        self.cargar()

        call_command("cargar_datos_demo", "--limpiar", "--si-estoy-seguro",
                     stdout=StringIO())

        self.assertFalse(Venta.objects.exists())
        self.assertFalse(CierreCaja.objects.exists())


class AnularFueraDeUnaTransaccionDePruebaTests(TransactionTestCase):
    """
    La anulación, con la base trabajando como trabaja de verdad.

    Las demás pruebas heredan de `TestCase`, que envuelve cada una en una
    transacción y la deshace al terminar. Eso las hace rápidas y esconde una
    clase de fallo entera: dentro de esa transacción prestada, un bloqueo de
    filas funciona aunque la operación haya perdido la suya, de modo que una
    función que en producción se cae con «select_for_update cannot be used
    outside of a transaction» pasa las pruebas en verde.

    Esta hereda de `TransactionTestCase`, que no envuelve nada. Es más lenta y
    por eso hay una sola: la de la operación que lo sufrió.
    """

    def test_anular_funciona_sin_una_transaccion_prestada(self):
        licorera = crear_negocio("Sabaneta")
        duena = crear_usuario(licorera, "duena@sinenvoltura.com",
                              Rol.ADMINISTRADOR_LICORERA)
        cajero = crear_usuario(licorera, "cajero@sinenvoltura.com", Rol.VENDEDOR)
        ron = crear_producto(licorera, "Ron sin envoltura", precio="50000")
        registrar_entrada(
            licorera=licorera, usuario=cajero,
            lineas=[{"producto": ron, "cantidad": 20,
                     "costo_unitario": Decimal("30000")}])
        venta = registrar_venta(
            licorera=licorera, usuario=cajero,
            medio_pago=MedioPago.objects.get(nombre=MedioPago.EFECTIVO),
            lineas=[{"producto": ron, "cantidad": 3}])

        anular_venta(venta=venta, usuario=duena, motivo="Devuelta")

        venta.refresh_from_db()
        self.assertEqual(venta.estado, Venta.Estado.ANULADA)
        self.assertEqual(existencias_de(ron, Sede.principal_de(licorera)), 20)
