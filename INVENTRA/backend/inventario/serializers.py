"""Traducción y validación del catálogo (RF-INV-01 a 04)."""

from decimal import Decimal

from rest_framework import serializers

from .existencias import existencias_totales
from .precios import (
    costo_de_la_ultima_compra, costo_promedio, lotes_vivos, sugerir_precio)

from .models import (
    Categoria, EntradaMercancia, LoteInventario, MovimientoInventario, Producto)


class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = ("id", "nombre", "margen_sugerido")


class MargenDeCategoriaSerializer(serializers.Serializer):
    """Una línea de la ventana de márgenes: qué categoría y qué porcentaje."""

    id = serializers.IntegerField()
    margen_sugerido = serializers.DecimalField(
        max_digits=5, decimal_places=2,
        min_value=Decimal("0"), max_value=Decimal("500"))


class MargenesSerializer(serializers.Serializer):
    """
    Los márgenes de las seis categorías, que se guardan de una sola vez.

    Van juntos y no uno por uno porque se editan juntos: quien abre esa ventana
    está repartiendo márgenes entre categorías, y guardar a medias dejaría la
    comparación entre ellas en un estado que nadie pidió.
    """

    margenes = MargenDeCategoriaSerializer(many=True)

    def validate_margenes(self, valor):
        if not valor:
            raise serializers.ValidationError("No hay ningún margen que guardar.")

        licorera = self.context.get("licorera")
        pedidos = [linea["id"] for linea in valor]
        if len(pedidos) != len(set(pedidos)):
            raise serializers.ValidationError("Hay una categoría repetida.")

        propias = set(
            Categoria.objects
            .filter(licorera=licorera, id__in=pedidos)
            .values_list("id", flat=True)
        )
        if set(pedidos) - propias:
            raise serializers.ValidationError("Alguna categoría no es de tu catálogo.")
        return valor


class AlertaDeExistenciasSerializer(serializers.ModelSerializer):
    """
    Una referencia por reponer, tal como la enseña el panel.

    Deliberadamente corto. El panel no necesita costos ni lotes, y el
    serializer del catálogo los trae: enviarlos aquí sería publicar en la
    primera pantalla lo que cada referencia costó, sin que nadie lo haya
    pedido.
    """

    existencias = serializers.IntegerField(source="disponibles", read_only=True)

    class Meta:
        model = Producto
        fields = ("id", "nombre", "existencias", "stock_minimo")


class ProductoSerializer(serializers.ModelSerializer):
    """
    Lo que la pantalla ve de un producto.

    Las existencias no son una columna: se derivan de los lotes. Llegan por el
    contexto, en un diccionario calculado de una sola consulta para toda la
    lista; preguntarlas producto a producto haría una consulta por fila.
    """

    categoria_nombre = serializers.CharField(source="categoria.nombre", read_only=True)
    presentacion_nombre = serializers.CharField(
        source="get_presentacion_display", read_only=True)
    existencias = serializers.SerializerMethodField()
    costo_promedio = serializers.SerializerMethodField()
    costo_ultima_compra = serializers.SerializerMethodField()
    costo_minimo = serializers.SerializerMethodField()
    costo_maximo = serializers.SerializerMethodField()
    lotes_en_existencia = serializers.SerializerMethodField()
    precio_sugerido = serializers.SerializerMethodField()

    class Meta:
        model = Producto
        fields = (
            "id", "nombre", "categoria", "categoria_nombre",
            "presentacion", "presentacion_nombre", "codigo_barras",
            "precio_venta", "tiene_precio", "stock_minimo", "existencias",
            "costo_promedio", "costo_ultima_compra", "costo_minimo", "costo_maximo",
            "lotes_en_existencia", "precio_sugerido", "activo", "fecha_creacion",
        )
        read_only_fields = ("activo", "fecha_creacion")

    def get_existencias(self, producto):
        """
        Cero cuando el producto no tiene lotes, que es lo que significa: una
        referencia registrada de la que todavía no ha entrado mercancía.

        En los listados el dato viene calculado dentro de la consulta, de una
        sola vez para todas las filas. Al devolver un producto suelto —recién
        creado o recién editado— esa columna no está, y entonces sí se pregunta:
        es una consulta más en una operación que ya hizo varias, no una por fila.
        """
        disponibles = getattr(producto, "disponibles", None)
        if disponibles is not None:
            return disponibles
        return existencias_totales(producto)

    def get_costo_promedio(self, producto):
        """
        Lo que costó, en promedio, cada unidad de las que hay en existencia.
        Aprovecha lo que la consulta ya trajo anotado cuando viene de una lista.
        """
        return costo_promedio(
            producto,
            unidades=getattr(producto, "disponibles", None),
            valor=getattr(producto, "valor_existencias", None))

    def get_costo_ultima_compra(self, producto):
        return costo_de_la_ultima_compra(producto)

    def get_costo_minimo(self, producto):
        if hasattr(producto, "costo_minimo"):
            return producto.costo_minimo
        primero = lotes_vivos(producto).order_by("costo_unitario").first()
        return primero.costo_unitario if primero else None

    def get_costo_maximo(self, producto):
        if hasattr(producto, "costo_maximo"):
            return producto.costo_maximo
        ultimo = lotes_vivos(producto).order_by("-costo_unitario").first()
        return ultimo.costo_unitario if ultimo else None

    def get_lotes_en_existencia(self, producto):
        """
        Qué costó cada grupo de unidades que sigue en bodega.

        Lo necesita la pantalla para decir cuántas unidades quedan por encima
        del precio que se está escribiendo. Un promedio reparte, y sin este
        detalle la parte que reparte sería invisible.
        """
        return [
            {"costo_unitario": str(lote.costo_unitario),
             "unidades": lote.cantidad_disponible}
            for lote in producto.lotes.all()
            if lote.cantidad_disponible > 0
        ]

    def get_precio_sugerido(self, producto):
        """
        Lo que el sistema PROPONE, nunca lo que aplica (RF-INV-11).

        Se calcula sobre el promedio de las existencias; sin existencias, sobre
        la última compra, que es lo único que se sabe. Nulo mientras no haya
        ninguna compra: sin costo no hay nada sobre lo que aplicar un margen.
        """
        base = self.get_costo_promedio(producto)
        if base is None:
            base = costo_de_la_ultima_compra(producto)
        return sugerir_precio(base, producto.categoria.margen_sugerido)


class ProductoGuardarSerializer(serializers.ModelSerializer):
    """
    El formulario de crear y editar (apartado 8.4 del documento de diseño).

    La licorera NO es un campo del formulario: sale de la sesión de quien pide.
    Si viajara en la petición, cualquiera podría registrar productos en el
    catálogo de otro negocio cambiando un número.
    """

    class Meta:
        model = Producto
        fields = ("nombre", "categoria", "presentacion", "codigo_barras",
                  "precio_venta", "stock_minimo")
        # El precio no se pide al registrar la referencia: en ese momento nadie
        # sabe todavía cuánto costó la mercancía, y un precio inventado es lo
        # que lleva a vender por debajo del costo. Se fija al recibir el primer
        # lote. El campo sigue aquí porque editarlo después sí es del
        # administrador (RF-INV-03).
        extra_kwargs = {"precio_venta": {"required": False}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # La categoría solo puede ser una de las de la propia licorera. Se
        # limita aquí y no en la vista porque es una regla del dato, y así vale
        # igual al crear y al editar.
        licorera = self.context.get("licorera")
        if licorera is not None:
            self.fields["categoria"].queryset = Categoria.objects.filter(
                licorera=licorera, activo=True)

    def validate_precio_venta(self, valor):
        """
        El cero se admite y significa «todavía sin precio»; lo negativo, no.

        Antes el cero se rechazaba, porque el formulario de creación pedía el
        precio y dejarlo en cero solo podía ser un descuido. Ahora el precio
        llega con la primera entrada de mercancía, de modo que entre la
        creación y esa entrada la referencia vive en cero a propósito.
        """
        if valor is not None and valor < 0:
            raise serializers.ValidationError("El precio de venta no puede ser negativo.")
        return valor

    def validate_codigo_barras(self, valor):
        """
        Vacío y «sin código» son lo mismo, y se guardan como lo mismo.

        Sin esto, dos productos sin código chocarían contra la restricción de
        unicidad, porque la cadena vacía sí es igual a otra cadena vacía y el
        nulo no es igual a nada.
        """
        codigo = (valor or "").strip()
        if not codigo:
            return None

        licorera = self.context.get("licorera")
        repetido = Producto.objects.filter(licorera=licorera, codigo_barras=codigo)
        if self.instance is not None:
            repetido = repetido.exclude(pk=self.instance.pk)
        if repetido.exists():
            raise serializers.ValidationError(
                "Ya hay un producto registrado con este código de barras.")
        return codigo

    def create(self, datos):
        return Producto.objects.create(licorera=self.context["licorera"], **datos)


class LineaDeEntradaSerializer(serializers.Serializer):
    """Una línea de la entrada, que será un lote con su costo propio."""

    producto = serializers.PrimaryKeyRelatedField(queryset=Producto.objects.all())
    cantidad = serializers.IntegerField(min_value=1)
    costo_unitario = serializers.DecimalField(max_digits=12, decimal_places=2,
                                              min_value=0)
    # El precio de venta de la referencia, que esta pantalla fija cuando la
    # referencia todavía no lo tiene. No es un dato del lote: el lote congela
    # su costo, y el precio es del producto. Viaja en la línea porque es aquí
    # donde se conoce el costo sobre el que se calcula.
    precio_venta = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=0, required=False)

    def validate_producto(self, valor):
        """
        Solo productos activos de la propia licorera: recibir mercancía de una
        referencia descontinuada es casi siempre un error, y de otra licorera es
        imposible.

        La comprobación va aquí y NO limitando el `queryset` del campo en el
        constructor, que es como está resuelto en el formulario de producto. La
        diferencia es que este serializador es un hijo dentro de otro: cuando se
        construye todavía no está enganchado a su padre, de modo que en ese
        momento `self.context` está vacío y el filtro habría dejado el catálogo
        en cero. Al validar sí está, porque el contexto se busca subiendo hasta
        el serializador raíz.
        """
        licorera = self.context.get("licorera")
        if licorera is not None and valor.licorera_id != licorera.id:
            raise serializers.ValidationError("Ese producto no es de tu catálogo.")
        if not valor.activo:
            raise serializers.ValidationError(
                "«%s» está inactivo: reactívalo antes de recibir mercancía." % valor.nombre)
        return valor

    def validate(self, datos):
        """
        Una referencia sin precio no sale de esta pantalla sin uno.

        Es el momento en que el precio se puede calcular: ya se sabe lo que
        costó. Dejarlo para después significa mercancía en bodega que el punto
        de venta no puede ofrecer, y nadie se entera hasta que un cliente la
        pide. Un precio en cero no vale como respuesta.
        """
        producto = datos.get("producto")
        precio = datos.get("precio_venta")

        if producto is not None and not producto.tiene_precio:
            if precio is None or precio <= 0:
                raise serializers.ValidationError({
                    "precio_venta":
                        "«%s» todavía no tiene precio de venta: ponlo aquí para "
                        "que se pueda vender." % producto.nombre,
                })
        return datos


class EntradaCrearSerializer(serializers.Serializer):
    """
    El formulario de la entrada de mercancía (RF-INV-05).

    Ni la licorera ni la sede ni el usuario son campos: salen de la sesión.
    """

    proveedor = serializers.CharField(max_length=100, required=False, allow_blank=True)
    observacion = serializers.CharField(max_length=255, required=False, allow_blank=True)
    lineas = LineaDeEntradaSerializer(many=True)

    def validate_lineas(self, valor):
        if not valor:
            raise serializers.ValidationError("Agrega al menos un producto.")

        vistos = [linea["producto"].id for linea in valor]
        if len(vistos) != len(set(vistos)):
            # Dos líneas del mismo producto en una entrada crearían dos lotes
            # con el mismo momento de ingreso, y el orden de consumo entre ellos
            # quedaría decidido por el desempate y no por una razón. Casi
            # siempre es un descuido al escribir el formulario.
            raise serializers.ValidationError(
                "Hay un producto repetido: súmalo en una sola línea.")
        return valor


class LoteSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source="producto.nombre", read_only=True)

    class Meta:
        model = LoteInventario
        fields = ("id", "producto", "producto_nombre", "cantidad_inicial",
                  "cantidad_disponible", "costo_unitario", "fecha_ingreso")


class EntradaSerializer(serializers.ModelSerializer):
    lotes = LoteSerializer(many=True, read_only=True)
    usuario_nombre = serializers.CharField(source="usuario.nombre_completo", read_only=True)

    class Meta:
        model = EntradaMercancia
        fields = ("id", "proveedor", "observacion", "fecha",
                  "usuario", "usuario_nombre", "lotes")


class MovimientoSerializer(serializers.ModelSerializer):
    """
    Una línea del kardex (RF-INV-09).

    Lleva el saldo tal como se guardó el día del movimiento, no uno recalculado:
    el kardex tiene que poder leerse como quedó, aunque después cambie cualquier
    otra cosa.
    """

    tipo_nombre = serializers.CharField(source="get_tipo_display", read_only=True)
    usuario_nombre = serializers.CharField(source="usuario.nombre_completo", read_only=True)

    class Meta:
        model = MovimientoInventario
        fields = ("id", "fecha", "tipo", "tipo_nombre", "cantidad", "costo_unitario",
                  "documento_tipo", "documento_id", "usuario", "usuario_nombre",
                  "motivo", "saldo_resultante")


class AjusteSerializer(serializers.Serializer):
    """
    El formulario del ajuste de existencias (RF-INV-06).

    Dos campos y nada más, que es lo que pide el requisito: la diferencia y el
    motivo. El costo de un ajuste hacia arriba no se pregunta.
    """

    cantidad = serializers.IntegerField(
        help_text="Diferencia: positiva si sobraron unidades, negativa si faltaron.")
    motivo = serializers.CharField(max_length=255)

    def validate_cantidad(self, valor):
        if valor == 0:
            raise serializers.ValidationError(
                "El ajuste no cambia nada: la diferencia es cero.")
        return valor

    def validate_motivo(self, valor):
        if not valor.strip():
            raise serializers.ValidationError("Escribe el motivo del ajuste.")
        return valor.strip()
