"""Traducción y validación del catálogo (RF-INV-01 a 04)."""

from rest_framework import serializers

from .models import Categoria, Producto


class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = ("id", "nombre")


class ProductoSerializer(serializers.ModelSerializer):
    """
    Lo que la pantalla ve de un producto.

    No lleva existencias: se derivan de los lotes y los lotes son el bloque
    siguiente. Cuando existan, se añaden aquí y en un solo sitio.
    """

    categoria_nombre = serializers.CharField(source="categoria.nombre", read_only=True)
    presentacion_nombre = serializers.CharField(
        source="get_presentacion_display", read_only=True)

    class Meta:
        model = Producto
        fields = (
            "id", "nombre", "categoria", "categoria_nombre",
            "presentacion", "presentacion_nombre", "codigo_barras",
            "precio_venta", "stock_minimo", "activo", "fecha_creacion",
        )
        read_only_fields = ("activo", "fecha_creacion")


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
