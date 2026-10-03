"""Vistas del módulo de suscripciones."""

import logging

from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from seguridad.correo import enviar_correo_verificacion
from seguridad.permissions import EsAdministradorDeLicorera
from seguridad.serializers import InicioSesionSerializer, UsuarioSerializer

from .cambio_de_plan import CambioNoPermitido, cambiar, motivo_para_no_cambiar
from .models import Plan
from .modulos import estado_de_los_modulos
from .serializers import (
    LicoreraSerializer,
    MiSuscripcionSerializer,
    PlanSerializer,
    RegistroLicoreraSerializer,
)

registro_log = logging.getLogger(__name__)


class PlanesView(ListAPIView):
    """Catálogo de planes disponibles. Es público: se muestra antes de registrarse."""

    permission_classes = [AllowAny]
    serializer_class = PlanSerializer
    pagination_class = None

    def get_queryset(self):
        return Plan.objects.filter(activo=True).order_by("precio_mensual")


class RegistroLicoreraView(APIView):
    """
    Registro de una licorera y su administrador (CU-SUS-01).

    No exige autenticación, porque quien se registra todavía no tiene cuenta. Al
    terminar devuelve los tokens, de modo que el usuario entra directamente al
    panel sin tener que iniciar sesión otra vez.
    """

    permission_classes = [AllowAny]
    # Límite de peticiones por origen (D-11): sin él, esta dirección permite
    # crear cuentas en masa.
    throttle_scope = "registro"

    def post(self, request):
        serializador = RegistroLicoreraSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)
        creado = serializador.save()

        usuario = creado["usuario"]
        tokens = InicioSesionSerializer.get_token(usuario)
        usuario.registrar_ingreso_exitoso()

        # El enlace de confirmación sale aquí y no dentro del serializador: crear
        # la licorera es una operación de base de datos y mandar un correo es una
        # llamada a un servicio de fuera. Si el correo falla, la cuenta ya existe
        # y la persona puede pedir otro enlace desde su perfil; lo que no puede
        # pasar es que un servicio caído impida registrarse (D-10).
        try:
            enviar_correo_verificacion(usuario)
        except Exception:
            registro_log.exception("No se pudo enviar el correo de verificación")

        return Response(
            {
                "licorera": LicoreraSerializer(creado["licorera"]).data,
                "usuario": UsuarioSerializer(usuario).data,
                "acceso": str(tokens.access_token),
                "refresco": str(tokens),
            },
            status=status.HTTP_201_CREATED,
        )


class MiSuscripcionView(APIView):
    """
    Suscripción vigente de la licorera de quien consulta (RF-SUS-03).

    No recibe ningún identificador: la licorera se toma del usuario de la
    petición. Es el mismo criterio que el perfil, y por la misma razón: si el
    identificador viniera en la dirección, habría que comprobar en cada llamada
    que es el suyo, y bastaría olvidarlo una vez para que un negocio viera la
    suscripción de otro.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        licorera = request.user.licorera
        if licorera is None:
            # El Administrador INVENTRA no pertenece a ninguna licorera.
            return Response({"detalle": "Tu cuenta no pertenece a una licorera."},
                            status=status.HTTP_404_NOT_FOUND)

        # La **actual**, no la vigente. Una cuenta suspendida sigue teniendo un
        # plan contratado, y esta es la pantalla donde tiene que verlo: si no,
        # el negocio no sabe ni qué está a punto de pagar. Que no pueda
        # registrar lo dice `puede_operar`, que es otra pregunta.
        suscripcion = licorera.suscripcion_actual()
        if suscripcion is None:
            # Sin suscripción se responde 200 y no un error: no tenerla es una
            # situación normal del negocio, no un fallo de la petición.
            #
            # La respuesta lleva LAS MISMAS CLAVES que cuando sí la hay, con
            # valores vacíos. Antes devolvía tres y el navegador tenía que
            # adivinar las demás: de ahí salió un «quedan undefined días» en
            # pantalla. Las claves se sacan del propio serializador, así que no
            # pueden quedarse atrás cuando se añada un campo.
            vacia = {campo: None for campo in MiSuscripcionSerializer().fields}
            vacia.update({"estado_texto": "Sin suscripción",
                          "es_prueba": False,
                          "avisa_vencimiento": False,
                          "puede_operar": False})
            return Response(vacia)

        return Response(MiSuscripcionSerializer(suscripcion).data)


class MisModulosView(APIView):
    """
    Qué módulos puede usar hoy la licorera de quien consulta (RF-SUS-04).

    El menú lateral tenía la lista escrita a mano, con la marca «Pronto» puesta
    a ojo. Esa lista no puede vivir en el navegador: el plan contratado lo sabe
    el servidor, y una licorera con plan Básico no debe leer que Sedes llegará
    «Pronto» cuando para ella no va a llegar.

    El plan sale de la suscripción **actual** y no de la vigente: una cuenta
    suspendida sigue teniendo un plan contratado, y su menú tiene que seguir
    diciendo la verdad sobre lo que ese plan incluye. Lo que no puede hacer
    mientras está suspendida —registrar— lo corta el permiso de escritura, que
    es otra cosa.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        licorera = request.user.licorera
        plan = None
        if licorera is not None:
            suscripcion = licorera.suscripcion_actual()
            plan = suscripcion.plan if suscripcion else None
        return Response({"modulos": estado_de_los_modulos(plan)})


class CambiarPlanView(APIView):
    """
    Cambio de plan pedido por el negocio (RF-SUS-02, decisión D-23).

    Solo baja de plan. Subir implica cobrar, y eso lo ejecuta el Administrador
    INVENTRA desde su panel: el servicio es el mismo, lo que cambia es quién
    lo dispara.

    NO LLEVA EL PERMISO DE ESCRITURA, Y ES A PROPÓSITO. Una licorera suspendida
    no puede registrar operaciones, pero sí tiene que poder pasarse al plan que
    va a pagar: es el camino que D-25 describe para volver —bajar de plan,
    pagar, y que INVENTRA renueve la fecha—. Cerrarlo dejaría a esa licorera sin
    salida dentro de la aplicación.
    """

    permission_classes = [EsAdministradorDeLicorera]

    def get(self, request):
        """
        Qué pasaría con cada plan, sin hacer nada todavía.

        La pantalla lo usa para decir **antes** de pulsar si el cambio procede y,
        si no, por qué: «el plan Básico admite un usuario y tienes tres activos».
        Ofrecer un botón que se va a rechazar hace trabajar al negocio para nada,
        que es el mismo defecto que ya se corrigió en la gestión de usuarios.

        El veredicto sale de la misma función que usa el POST, así que la vista
        previa y el rechazo no pueden decir cosas distintas.
        """
        licorera = request.user.licorera
        actual = licorera.suscripcion_actual()

        planes = []
        for plan in Plan.objects.filter(activo=True).order_by("precio_mensual"):
            motivo = motivo_para_no_cambiar(licorera, plan)
            planes.append({
                "plan": plan.id,
                "nombre": plan.nombre,
                "es_el_actual": actual is not None and actual.plan_id == plan.id,
                "se_puede": motivo is None,
                "motivo": None if motivo is None else motivo[1],
            })
        return Response({"planes": planes})

    def post(self, request):
        licorera = request.user.licorera
        destino = Plan.objects.filter(id=request.data.get("plan")).first()
        if destino is None:
            return Response({"detalle": "Elige un plan."},
                            status=status.HTTP_400_BAD_REQUEST)

        motivo = motivo_para_no_cambiar(licorera, destino)
        if motivo is not None:
            # El código distingue dos rechazos: 403 cuando la operación no le
            # corresponde al negocio —subir lo activa INVENTRA— y 409 cuando sí
            # le corresponde pero su estado no la admite, que es algo que puede
            # arreglar inactivando lo que sobra.
            return Response({"detalle": motivo[1]}, status=motivo[0])

        try:
            nueva = cambiar(licorera, destino)
        except CambioNoPermitido as tardio:
            # No deberia llegar aqui: lo que `cambiar()` comprueba acaba de
            # comprobarse arriba. Se deja por si algo cambia entre las dos
            # —otra pestaña creando un usuario, por ejemplo—: ante esa carrera,
            # mejor un 409 explicado que un error del servidor.
            return Response({"detalle": str(tardio)}, status=status.HTTP_409_CONFLICT)

        return Response(MiSuscripcionSerializer(nueva).data)

