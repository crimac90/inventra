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
from inventario.tests import crear_negocio, crear_usuario
from sedes.models import Sede
from seguridad.models import Rol

from .jornada import INICIO_DE_JORNADA, jornada_actual, jornada_de, limites_de
from .models import CierreCaja, MedioPago, Venta


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
