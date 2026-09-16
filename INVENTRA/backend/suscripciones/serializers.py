"""
Traductores del módulo de suscripciones.

El registro de una licorera es la puerta de entrada del negocio: crea de una sola
vez el cliente, su suscripción al plan Básico y su primer usuario.
"""

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as ErrorDeValidacion
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from seguridad.models import Rol, Usuario

from .models import Licorera, Plan, Suscripcion


class PlanSerializer(serializers.ModelSerializer):
    """Datos del plan que se muestran al elegir o comparar."""

    class Meta:
        model = Plan
        fields = [
            "id", "nombre", "precio_mensual", "maximo_sedes", "maximo_usuarios",
            "permite_facturacion", "permite_reportes_avanzados",
        ]


class LicoreraSerializer(serializers.ModelSerializer):
    """Datos del negocio."""

    class Meta:
        model = Licorera
        fields = ["id", "nombre", "nit", "direccion", "telefono", "correo", "fecha_registro", "activo"]
        read_only_fields = ["fecha_registro", "activo"]


class RegistroLicoreraSerializer(serializers.Serializer):
    """
    Registro de una licorera nueva (CU-SUS-01 y RF-SEG-01).

    Recibe los cuatro datos del formulario de registro y crea tres cosas en una
    sola operación: la licorera, su suscripción al plan Básico y el usuario
    administrador del negocio.
    """

    nombre_negocio = serializers.CharField(max_length=100)
    nombre_completo = serializers.CharField(max_length=100)
    correo = serializers.EmailField(max_length=100)
    password = serializers.CharField(write_only=True)

    def validate_correo(self, valor):
        """El correo identifica al usuario en toda la plataforma, así que es único."""
        correo = valor.strip().lower()
        if Usuario.objects.filter(correo=correo).exists():
            raise serializers.ValidationError("Ya existe una cuenta registrada con este correo.")
        return correo

    def validate_password(self, valor):
        """Aplica la política de contraseñas configurada en el proyecto."""
        try:
            validate_password(valor)
        except ErrorDeValidacion as error:
            raise serializers.ValidationError(list(error.messages))
        return valor

    @transaction.atomic
    def create(self, datos_validados):
        """
        Crea el negocio, su suscripción y su administrador.

        Va dentro de una transacción: si cualquiera de los tres pasos falla, no
        queda nada a medias en la base de datos. Una licorera sin usuario, o un
        usuario sin licorera, serían registros inservibles.
        """
        plan_basico = Plan.objects.get(nombre="Básico")

        licorera = Licorera.objects.create(
            nombre=datos_validados["nombre_negocio"],
            correo=datos_validados["correo"],
        )

        Suscripcion.objects.create(
            licorera=licorera,
            plan=plan_basico,
            estado=Suscripcion.Estado.ACTIVA,
            fecha_inicio=timezone.localdate(),
            precio_pactado=plan_basico.precio_mensual,
        )

        usuario = Usuario.objects.create_user(
            correo=datos_validados["correo"],
            nombre_completo=datos_validados["nombre_completo"],
            password=datos_validados["password"],
            licorera=licorera,
            rol=Rol.objects.get(nombre=Rol.ADMINISTRADOR_LICORERA),
        )

        return {"licorera": licorera, "usuario": usuario}
