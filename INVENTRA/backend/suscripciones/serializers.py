"""
Traductores del módulo de suscripciones.

El registro de una licorera es la puerta de entrada del negocio: crea de una sola
vez el cliente, su suscripción en período de prueba y su primer usuario.
"""

from datetime import timedelta

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
        # La prueba corre sobre el plan Pro, no sobre el Básico. Lo decide el
        # manual de usuario, que promete «quince días con todas las funciones
        # disponibles»: con el Básico el negocio no podría crear un segundo
        # usuario durante su propia prueba. Al terminar, quien no contrate pasa a
        # suspendida; quien contrate Básico teniendo dos usuarios lo resuelve la
        # validación del cambio de plan (RF-SUS-02).
        plan_de_prueba = Plan.objects.get(nombre="Pro")
        hoy = timezone.localdate()

        licorera = Licorera.objects.create(
            nombre=datos_validados["nombre_negocio"],
            correo=datos_validados["correo"],
        )

        Suscripcion.objects.create(
            licorera=licorera,
            plan=plan_de_prueba,
            estado=Suscripcion.Estado.EN_PRUEBA,
            fecha_inicio=hoy,
            fecha_fin=hoy + timedelta(days=Suscripcion.DIAS_DE_PRUEBA),
            # Cero, porque la prueba no se cobra. El precio del plan se congela
            # el día que se contrata, en la fila que abra ese contrato.
            precio_pactado=0,
        )

        usuario = Usuario.objects.create_user(
            correo=datos_validados["correo"],
            nombre_completo=datos_validados["nombre_completo"],
            password=datos_validados["password"],
            licorera=licorera,
            rol=Rol.objects.get(nombre=Rol.ADMINISTRADOR_LICORERA),
        )

        return {"licorera": licorera, "usuario": usuario}


class MiSuscripcionSerializer(serializers.Serializer):
    """
    Estado de la suscripción de la licorera de quien consulta (RF-SUS-03).

    No es un ModelSerializer porque lo que el frontend necesita no es la fila:
    es la respuesta a tres preguntas —qué plan tengo, hasta cuándo, y si puedo
    registrar operaciones—. Dos de las tres se calculan.

    `puede_operar` se devuelve ya resuelto y no como una regla que el navegador
    tenga que aplicar: una comprobación de permiso escrita en el frontend se
    puede saltar abriendo las herramientas del navegador. El backend la vuelve a
    hacer en cada operación de escritura; esto es solo para que la interfaz
    muestre lo que corresponde.
    """

    plan = serializers.CharField(source="plan.nombre")
    precio_mensual = serializers.DecimalField(
        source="plan.precio_mensual", max_digits=12, decimal_places=2)
    estado = serializers.CharField()
    estado_texto = serializers.SerializerMethodField()
    es_prueba = serializers.BooleanField()
    fecha_inicio = serializers.DateField()
    fecha_fin = serializers.DateField()
    dias_restantes = serializers.SerializerMethodField()
    puede_operar = serializers.SerializerMethodField()

    def get_estado_texto(self, suscripcion):
        return suscripcion.get_estado_display()

    def get_dias_restantes(self, suscripcion):
        return suscripcion.dias_restantes()

    def get_puede_operar(self, suscripcion):
        return suscripcion.esta_vigente()
