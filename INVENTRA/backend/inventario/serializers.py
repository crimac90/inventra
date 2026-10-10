"""Traducción y validación del catálogo (RF-INV-01 a 04)."""

from rest_framework import serializers

from .existencias import existencias_totales

from .models import (
    Categoria, EntradaMercancia, LoteInventario, MovimientoInventario, Producto)


class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = ("id", "nombre")


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

    class Meta:
        model = Producto
        fields = (
            "id", "nombre", "categoria", "categoria_nombre",
            "presentacion", "presentacion_nombre", "codigo_barras",
            "precio_venta", "stock_minimo", "existencias", "activo", "fecha_creacion",
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
        if valor <= 0:
            raise serializers.ValidationError("El precio de venta debe ser mayor que cero.")
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
    motivo. El costo de un ajuste hacia arriba no se pregunta (D-32).
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
