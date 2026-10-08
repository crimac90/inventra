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

from .puesta_en_marcha import preparar_licorera_nueva

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
        # Toda licorera nace con su sede y sus categorías: sin ellas el negocio
        # no podría registrar inventario. Lo que hay que crear vive en un solo
        # sitio, porque son tres las puertas por las que nace una licorera.
        preparar_licorera_nueva(licorera)

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
    estado = serializers.SerializerMethodField()
    estado_texto = serializers.SerializerMethodField()
    es_prueba = serializers.SerializerMethodField()
    fecha_inicio = serializers.DateField()
    fecha_fin = serializers.DateField()
    dias_restantes = serializers.SerializerMethodField()
    dias_para_suspension = serializers.SerializerMethodField()
    avisa_vencimiento = serializers.SerializerMethodField()
    puede_operar = serializers.SerializerMethodField()

    # El estado que sale de aquí es el calculado, no el que tiene guardado la
    # fila (D-25). La columna la pone al día una orden que corre a diario, y si
    # una noche no corriera, el panel diría que la prueba sigue viva el día
    # después de vencer. Lo que se calcula no se queda atrás.
    def get_estado(self, suscripcion):
        return suscripcion.estado_por_fecha()

    def get_estado_texto(self, suscripcion):
        return Suscripcion.Estado(suscripcion.estado_por_fecha()).label

    def get_es_prueba(self, suscripcion):
        return suscripcion.estado_por_fecha() == Suscripcion.Estado.EN_PRUEBA

    def get_dias_para_suspension(self, suscripcion):
        return suscripcion.dias_para_suspension()

    def get_avisa_vencimiento(self, suscripcion):
        """
        Si al panel le toca avisar de que la fecha se acerca.

        Se resuelve en el servidor y no en el navegador para que el umbral viva
        en un solo sitio: estaba escrito a mano en el componente del aviso, y un
        tres repetido en dos lenguajes distintos es un tres que algún día valdrá
        dos en uno de ellos. La regla misma está en el modelo, que es a quien le
        corresponde la pregunta; aquí solo se expone.
        """
        return suscripcion.avisa_vencimiento()

    def get_dias_restantes(self, suscripcion):
        return suscripcion.dias_restantes()

    def get_puede_operar(self, suscripcion):
        return suscripcion.esta_vigente()


class AltaLicoreraSerializer(serializers.Serializer):
    """
    Alta de una licorera por el Administrador INVENTRA (RF-SUS-01, segunda vía).

    Es la otra puerta que decidió D-10. Se diferencia del autoservicio en dos
    cosas, y las dos vienen de que aquí hay un contrato de por medio: el plan y
    la fecha de vencimiento los escribe quien dio de alta, en vez de salir de la
    prueba de quince días.

    La cuenta del dueño nace **sin contraseña utilizable**. La define él, con el
    enlace que se le envía, de modo que el Administrador INVENTRA no llega a
    conocer la clave de un cliente. No es una precaución teórica: es lo único que
    permite sostener después quién pudo entrar a una cuenta.
    """

    nombre_negocio = serializers.CharField(max_length=100)
    nit = serializers.CharField(max_length=20, required=False, allow_blank=True)
    direccion = serializers.CharField(max_length=150, required=False, allow_blank=True)
    telefono = serializers.CharField(max_length=20, required=False, allow_blank=True)

    nombre_completo = serializers.CharField(max_length=100)
    correo = serializers.EmailField(max_length=100)

    plan = serializers.PrimaryKeyRelatedField(queryset=Plan.objects.filter(activo=True))
    fecha_fin = serializers.DateField()

    def validate_correo(self, valor):
        correo = valor.strip().lower()
        if Usuario.objects.filter(correo=correo).exists():
            raise serializers.ValidationError("Ya existe una cuenta registrada con este correo.")
        return correo

    def validate_nit(self, valor):
        nit = (valor or "").strip()
        if nit and Licorera.objects.filter(nit=nit).exists():
            raise serializers.ValidationError("Ya hay una licorera registrada con este NIT.")
        return nit or None

    def validate_fecha_fin(self, valor):
        """La misma regla que al corregir: una fecha escrita a mano no va al pasado."""
        if valor < timezone.localdate():
            raise serializers.ValidationError(
                "La fecha de vencimiento no puede quedar en el pasado.")
        return valor

    @transaction.atomic
    def create(self, datos):
        licorera = Licorera.objects.create(
            nombre=datos["nombre_negocio"],
            nit=datos.get("nit") or None,
            direccion=datos.get("direccion") or "",
            telefono=datos.get("telefono") or "",
            correo=datos["correo"],
        )
        preparar_licorera_nueva(licorera)

        suscripcion = Suscripcion.objects.create(
            licorera=licorera,
            plan=datos["plan"],
            estado=Suscripcion.Estado.ACTIVA,
            fecha_inicio=timezone.localdate(),
            fecha_fin=datos["fecha_fin"],
            precio_pactado=datos["plan"].precio_mensual,
        )

        usuario = Usuario.objects.create_user(
            correo=datos["correo"],
            nombre_completo=datos["nombre_completo"],
            # Sin contraseña: Django la marca como inutilizable y ningún intento
            # de ingreso la acierta hasta que su dueño define una.
            password=None,
            licorera=licorera,
            rol=Rol.objects.get(nombre=Rol.ADMINISTRADOR_LICORERA),
        )

        return {"licorera": licorera, "usuario": usuario, "suscripcion": suscripcion}


class LicoreraDelPanelSerializer(serializers.Serializer):
    """
    Una licorera vista desde el panel de la plataforma (RF-SUS-05).

    Lo que sale de aquí es deliberadamente corto: nombre, contacto, plan, estado
    y cuántas cuentas tiene. **Nada de su información comercial** —ni productos,
    ni ventas, ni importes—, que es lo que el requisito prohíbe expresamente. El
    operador de la plataforma administra suscripciones, no negocios ajenos.
    """

    id = serializers.IntegerField()
    nombre = serializers.CharField()
    nit = serializers.CharField(allow_null=True)
    correo = serializers.CharField()
    telefono = serializers.CharField(allow_null=True)
    fecha_registro = serializers.DateTimeField()
    activo = serializers.BooleanField()

    plan = serializers.SerializerMethodField()
    estado = serializers.SerializerMethodField()
    estado_texto = serializers.SerializerMethodField()
    fecha_fin = serializers.SerializerMethodField()
    dias_restantes = serializers.SerializerMethodField()
    puede_operar = serializers.SerializerMethodField()
    usuarios_activos = serializers.SerializerMethodField()

    def _suscripcion(self, licorera):
        # Se calcula una vez por licorera y se guarda: el serializador pregunta
        # siete veces por lo mismo y cada una sería una consulta más.
        if not hasattr(licorera, "_actual"):
            licorera._actual = licorera.suscripcion_actual()
        return licorera._actual

    def get_plan(self, licorera):
        s = self._suscripcion(licorera)
        return s.plan.nombre if s else None

    def get_estado(self, licorera):
        s = self._suscripcion(licorera)
        return s.estado_por_fecha() if s else None

    def get_estado_texto(self, licorera):
        s = self._suscripcion(licorera)
        return Suscripcion.Estado(s.estado_por_fecha()).label if s else "Sin suscripción"

    def get_fecha_fin(self, licorera):
        s = self._suscripcion(licorera)
        return s.fecha_fin if s else None

    def get_dias_restantes(self, licorera):
        s = self._suscripcion(licorera)
        return s.dias_restantes() if s else None

    def get_puede_operar(self, licorera):
        s = self._suscripcion(licorera)
        return bool(s and s.esta_vigente())

    def get_usuarios_activos(self, licorera):
        return licorera.usuarios.filter(activo=True).count()

