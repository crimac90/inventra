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
from django.core import mail
from django.core.exceptions import ValidationError

from inventario.existencias import existencias_de
from inventario.models import MovimientoInventario
from inventario.operaciones import registrar_entrada
from inventario.models import Categoria, Producto
from inventario.tests import crear_negocio, crear_usuario
from sedes.models import Sede
from seguridad.models import Rol

from .caja import (cerrar_jornada, explicar_diferencia, jornadas_sin_explicar,
                   resumen_de)
from .consultas import filtrar
from .jornada import INICIO_DE_JORNADA, jornada_actual, jornada_de, limites_de
from .models import CierreCaja, DetalleVenta, MedioPago, Venta
from .operaciones import anular_venta, registrar_venta


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
        return cerrar_jornada(
            licorera=self.licorera, usuario=self.cajero,
            efectivo_contado=Decimal(contado), observacion=observacion)


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
        El caso de D-36 contado en dinero: la caja de las dos de la mañana
        pertenece a la jornada que se está cerrando, no a la siguiente.
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
        Es lo que cierra el hueco de D-37: quien cierra puede escribir
        cualquier cosa, y el administrador tiene que poder juzgarla sin entrar.
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
