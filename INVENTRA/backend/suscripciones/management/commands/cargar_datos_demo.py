"""
Carga el juego de datos de demostración del proyecto.

POR QUÉ ES UN COMANDO Y NO UNA MIGRACIÓN
Los planes y los roles sí se cargan con migraciones, porque son datos que el
sistema necesita para funcionar: sin ellos no se puede registrar a nadie. Estas
cuentas son otra cosa. Sus contraseñas están publicadas en el archivo de
despliegue, así que una migración las crearía también en el servidor publicado,
el día que se despliegue, sin que nadie lo pidiera. Una puerta conocida abierta
en producción.

Por eso son un comando: se ejecuta cuando alguien quiere, en el equipo que
quiere, y queda constancia de que fue una decisión y no un efecto secundario.

USO
    py manage.py cargar_datos_demo
    py manage.py cargar_datos_demo --limpiar     (borra lo que cargó)
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from seguridad.models import Rol, Usuario

from suscripciones.models import Licorera, Plan, Suscripcion

CONTRASENA = "Inventra2026"

# Marca que identifica todo lo que crea este comando, para poder retirarlo
# después sin tocar nada más.
DOMINIO = "@demo.inventra.co"

NEGOCIOS = [
    {
        "nombre": "Licorera La Esquina",
        "correo": f"contacto{DOMINIO}",
        "plan": "Pro",
        "usuarios": [
            ("Ana Gómez Restrepo", f"admin{DOMINIO}", Rol.ADMINISTRADOR_LICORERA, "3001112233"),
            ("Carlos Ruiz Mejía", f"vendedor{DOMINIO}", Rol.VENDEDOR, "3004445566"),
        ],
    },
    {
        # Existe para dos cosas: comprobar el aislamiento entre negocios y ver
        # el tope de usuarios del plan Básico.
        "nombre": "Licorera El Vecino",
        "correo": f"contacto.vecino{DOMINIO}",
        "plan": "B",
        "usuarios": [
            ("Marta Díaz Salas", f"vecino{DOMINIO}", Rol.ADMINISTRADOR_LICORERA, "3007778899"),
        ],
    },
]

SUPERADMINISTRADOR = ("Operador INVENTRA", f"plataforma{DOMINIO}")


class Command(BaseCommand):
    help = "Carga (o retira) el juego de cuentas de demostración."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limpiar",
            action="store_true",
            help="Borra las cuentas de demostración en lugar de crearlas.",
        )
        parser.add_argument(
            "--si-estoy-seguro",
            action="store_true",
            help="Necesario para ejecutarlo fuera del modo de depuración.",
        )

    def handle(self, *args, **opciones):
        # Red de seguridad: en un servidor publicado, DEBUG está en False. Ahí
        # el comando se niega a correr salvo que se le insista a propósito.
        if not settings.DEBUG and not opciones["si_estoy_seguro"]:
            raise CommandError(
                "Este comando crea cuentas con contraseñas publicadas y el proyecto no está "
                "en modo de depuración. Si de verdad quieres cargarlas aquí, repite el "
                "comando con --si-estoy-seguro."
            )

        if opciones["limpiar"]:
            self.limpiar()
        else:
            self.cargar()

    @transaction.atomic
    def cargar(self):
        """
        Crea las cuentas. Se puede repetir sin miedo: si algo ya existe, se
        respeta y no se duplica.
        """
        for datos in NEGOCIOS:
            # Se busca por prefijo para no depender de la tilde de «Básico».
            plan = Plan.objects.get(nombre__startswith=datos["plan"])

            licorera, creada = Licorera.objects.get_or_create(
                correo=datos["correo"], defaults={"nombre": datos["nombre"]}
            )
            self.anunciar("licorera", licorera.nombre, creada)

            if not licorera.suscripciones.exists():
                Suscripcion.objects.create(
                    licorera=licorera,
                    plan=plan,
                    estado=Suscripcion.Estado.ACTIVA,
                    fecha_inicio=timezone.localdate(),
                    precio_pactado=plan.precio_mensual,
                )
                self.anunciar("suscripción", f"{licorera.nombre} → plan {plan.nombre}", True)

            for nombre, correo, rol, telefono in datos["usuarios"]:
                self.crear_usuario(nombre, correo, rol, licorera, telefono)

        # El operador de la plataforma no pertenece a ninguna licorera.
        nombre, correo = SUPERADMINISTRADOR
        self.crear_usuario(nombre, correo, Rol.ADMINISTRADOR_INVENTRA, None, None)

        self.resumen()

    def crear_usuario(self, nombre, correo, nombre_rol, licorera, telefono):
        if Usuario.objects.filter(correo=correo).exists():
            self.anunciar("usuario", correo, False)
            return

        Usuario.objects.create_user(
            correo=correo,
            nombre_completo=nombre,
            password=CONTRASENA,
            rol=Rol.objects.get(nombre=nombre_rol),
            licorera=licorera,
            telefono=telefono,
        )
        self.anunciar("usuario", correo, True)

    @transaction.atomic
    def limpiar(self):
        """
        Retira lo cargado. El orden NO es opcional: las llaves foráneas de
        `usuario` y `suscripcion` hacia `licorera` están declaradas con PROTECT,
        así que la base se niega a borrar una licorera con filas colgando. Hay
        que ir de las hojas a la raíz.
        """
        usuarios = Usuario.objects.filter(correo__endswith=DOMINIO).delete()[0]
        suscripciones = Suscripcion.objects.filter(
            licorera__correo__endswith=DOMINIO
        ).delete()[0]
        licoreras = Licorera.objects.filter(correo__endswith=DOMINIO).delete()[0]

        self.stdout.write(
            self.style.WARNING(
                f"Retirado: {usuarios} usuario(s), {suscripciones} suscripción(es), "
                f"{licoreras} licorera(s)."
            )
        )

    def anunciar(self, tipo, nombre, creado):
        if creado:
            self.stdout.write(self.style.SUCCESS(f"  creado   {tipo}: {nombre}"))
        else:
            self.stdout.write(f"  ya existe {tipo}: {nombre}")

    def resumen(self):
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Cuentas de demostración disponibles:"))
        self.stdout.write("")
        filas = [
            ("Administrador de licorera", f"admin{DOMINIO}", "Licorera La Esquina (Pro)"),
            ("Vendedor", f"vendedor{DOMINIO}", "Licorera La Esquina (Pro)"),
            ("Administrador de licorera", f"vecino{DOMINIO}", "Licorera El Vecino (Básico)"),
            ("Administrador de INVENTRA", f"plataforma{DOMINIO}", "sin licorera"),
        ]
        for rol, correo, donde in filas:
            self.stdout.write(f"  {rol:<28} {correo:<34} {donde}")
        self.stdout.write("")
        self.stdout.write(f"  Contraseña de todas: {CONTRASENA}")
        self.stdout.write("")
