"""
Traducción de entrada y salida del módulo de ventas.

El criterio de qué se recibe y qué no es el mismo de INV: **el precio no se
recibe**. Quien vende dice qué producto y cuántas unidades; a cómo se vende lo
dice el catálogo en ese instante. Aceptarlo del cliente permitiría cobrar lo
que quisiera quien tuviera la pantalla delante.
"""

from rest_framework import serializers

from inventario.models import Producto

from .models import CierreCaja, DetalleVenta, MedioPago, Venta


class MedioPagoSerializer(serializers.ModelSerializer):
    class Meta:
        model = MedioPago
        fields = ("id", "nombre")


class LineaSerializer(serializers.Serializer):
    """Una línea de lo que se está cobrando."""

    producto_id = serializers.IntegerField()
    cantidad = serializers.IntegerField(min_value=1)


class VentaCrearSerializer(serializers.Serializer):
    """Lo que llega del punto de venta al cobrar (RF-VEN-01 y RF-VEN-02)."""

    medio_pago_id = serializers.IntegerField()
    monto_recibido = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True)
    lineas = LineaSerializer(many=True, allow_empty=False)

    def validate_lineas(self, lineas):
        """
        Dos líneas del mismo producto se juntan en una.

        Es lo que espera quien vende —pulsar dos veces el mismo producto es
        «dos unidades», no «dos renglones»— y además evita dos consumos
        separados del PEPS para una sola compra.
        """
        juntas = {}
        for linea in lineas:
            juntas[linea["producto_id"]] = (
                juntas.get(linea["producto_id"], 0) + linea["cantidad"])
        return [{"producto_id": pk, "cantidad": cantidad}
                for pk, cantidad in juntas.items()]

    def productos(self, licorera):
        """
        Resuelve los identificadores contra el catálogo de ESTA licorera.

        El filtro por licorera va aquí y no solo en la operación: así un
        identificador ajeno se rechaza como un dato inválido, que es lo que
        es, en vez de llegar al fondo y salir como un error del sistema.
        """
        pedidos = [linea["producto_id"] for linea in self.validated_data["lineas"]]
        catalogo = {p.id: p for p in Producto.objects.filter(
            licorera=licorera, id__in=pedidos)}

        faltan = [str(pk) for pk in pedidos if pk not in catalogo]
        if faltan:
            raise serializers.ValidationError(
                {"lineas": "No existe en tu catálogo el producto %s." % ", ".join(faltan)})

        return [{"producto": catalogo[linea["producto_id"]], "cantidad": linea["cantidad"]}
                for linea in self.validated_data["lineas"]]


class AnulacionSerializer(serializers.Serializer):
    motivo = serializers.CharField(max_length=255, allow_blank=False, trim_whitespace=True)


class LineaDeVentaSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source="producto.nombre", read_only=True)

    class Meta:
        model = DetalleVenta
        fields = ("id", "producto", "producto_nombre", "cantidad",
                  "precio_unitario", "subtotal")


class VentaSerializer(serializers.ModelSerializer):
    """Una venta tal como la enseñan el comprobante y el historial."""

    lineas = LineaDeVentaSerializer(many=True, read_only=True)
    medio_pago_nombre = serializers.CharField(source="medio_pago.nombre", read_only=True)
    vendedor = serializers.CharField(source="usuario.nombre_completo", read_only=True)
    cambio = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Venta
        fields = ("id", "consecutivo", "fecha", "total", "medio_pago",
                  "medio_pago_nombre", "monto_recibido", "cambio", "estado",
                  "motivo_anulacion", "vendedor", "lineas")


class VentaDeLaListaSerializer(serializers.ModelSerializer):
    """
    El historial no trae las líneas de cada venta.

    Son cientos de filas y nadie las mira hasta que abre una: traerlas todas
    sería pedir a la base el detalle completo de un mes para enseñar una tabla.
    """

    medio_pago_nombre = serializers.CharField(source="medio_pago.nombre", read_only=True)
    vendedor = serializers.CharField(source="usuario.nombre_completo", read_only=True)

    class Meta:
        model = Venta
        fields = ("id", "consecutivo", "fecha", "total", "medio_pago_nombre",
                  "estado", "motivo_anulacion", "vendedor")


class CierreCrearSerializer(serializers.Serializer):
    efectivo_contado = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=0)
    observacion = serializers.CharField(
        max_length=255, required=False, allow_blank=True, allow_null=True)


class ExplicacionSerializer(serializers.Serializer):
    observacion = serializers.CharField(max_length=255, allow_blank=False,
                                        trim_whitespace=True)


class CierreSerializer(serializers.ModelSerializer):
    sede_nombre = serializers.CharField(source="sede.nombre", read_only=True)
    usuario_nombre = serializers.CharField(source="usuario.nombre_completo", read_only=True)
    total_vendido = serializers.DecimalField(max_digits=12, decimal_places=2,
                                             read_only=True)

    class Meta:
        model = CierreCaja
        fields = ("id", "fecha", "sede", "sede_nombre", "total_efectivo",
                  "total_transferencia", "total_tarjeta", "total_vendido",
                  "efectivo_contado", "diferencia", "observacion", "usuario_nombre")
