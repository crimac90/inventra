"""
Genera los scripts SQL del proyecto a partir de las migraciones.

POR QUÉ SE GENERAN Y NO SE ESCRIBEN A MANO
Las tablas reales las crea Django a partir de las migraciones. Un script escrito
a mano desde el MER se queda atrás en cuanto cambia un modelo, y nadie se entera
hasta que alguien lo ejecuta y obtiene una base distinta de la que la aplicación
espera. Generándolo desde la misma fuente, no puede mentir.

QUÉ PRODUCE
    scripts_bd/01_estructura.sql      las tablas, llaves e índices (DDL)
    scripts_bd/02_carga_inicial.sql   los planes y los roles, que el sistema
                                      necesita para funcionar

Son dos archivos y no uno porque responden a preguntas distintas: el primero
crea la base vacía, el segundo la deja utilizable. Al restaurar una copia de
seguridad se usa el primero; al preparar un entorno nuevo, los dos.

POR QUÉ LA CARGA INICIAL SE GENERA APARTE
`sqlmigrate` traduce a SQL las migraciones de estructura, pero los planes y los
roles se cargan con código Python (`RunPython`), no con sentencias SQL, así que
de esas migraciones no sale nada. Se leen las filas de la base y se escriben sus
`INSERT`.

USO
    py manage.py generar_scripts_sql
"""

from datetime import datetime
from io import StringIO
from pathlib import Path

import django
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.operations import RunPython, RunSQL

from seguridad.models import Rol

from suscripciones.models import Plan

# La carpeta está fuera de backend/, al mismo nivel, porque los scripts no son
# del backend: son de la base de datos.
CARPETA = Path(settings.BASE_DIR).parent / "scripts_bd"


class Command(BaseCommand):
    help = "Genera scripts_bd/01_estructura.sql y 02_carga_inicial.sql desde las migraciones."

    def add_arguments(self, parser):
        parser.add_argument(
            "--carpeta",
            help="Dónde escribir los archivos. Por defecto, la carpeta scripts_bd del proyecto.",
        )

    def handle(self, *args, **opciones):
        carpeta = Path(opciones["carpeta"]) if opciones["carpeta"] else CARPETA
        carpeta.mkdir(parents=True, exist_ok=True)

        estructura = carpeta / "01_estructura.sql"
        carga = carpeta / "02_carga_inicial.sql"

        estructura.write_text(self.generar_estructura(), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"  escrito {estructura.name}"))

        carga.write_text(self.generar_carga_inicial(), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"  escrito {carga.name}"))

        self.stdout.write("")
        self.stdout.write(f"  Carpeta: {carpeta}")

    # -- Estructura --------------------------------------------------------

    def orden_de_migraciones(self):
        """
        Devuelve las migraciones en el mismo orden en que las aplicaría
        `migrate`. El orden importa: una tabla con llave foránea no se puede
        crear antes que la tabla a la que apunta.
        """
        # Se guarda el cargador: hace falta después para poder mirar las
        # operaciones de cada migración, no solo su nombre.
        self.cargador = MigrationLoader(connection)
        cargador = self.cargador
        ordenadas = []

        for hoja in sorted(cargador.graph.leaf_nodes()):
            for nodo in cargador.graph.forwards_plan(hoja):
                if nodo not in ordenadas:
                    ordenadas.append(nodo)

        return ordenadas

    def generar_estructura(self):
        lineas = [self.cabecera("Estructura de la base de datos (DDL)")]
        lineas.append(
            "-- Generado a partir de las migraciones de Django. No se edita a mano:\n"
            "-- se cambia el modelo, se crea la migración y se vuelve a generar.\n"
        )

        for app, nombre in self.orden_de_migraciones():
            salida = StringIO()
            try:
                call_command("sqlmigrate", app, nombre, stdout=salida, no_color=True)
            except Exception as error:   # noqa: BLE001
                lineas.append(f"-- [{app}.{nombre}] no se pudo traducir: {error}\n")
                continue

            sql = salida.getvalue().strip()

            # Las migraciones de datos no producen sentencias, pero `sqlmigrate`
            # SIEMPRE devuelve algo: un encabezado de comentarios con el nombre
            # de cada operación. En MySQL, además, no hay BEGIN/COMMIT alrededor
            # —las sentencias de estructura no se pueden deshacer— así que la
            # primera línea es literalmente «--». Por eso no basta con mirar el
            # principio: hay que quitar los comentarios y ver si queda algo.
            if not self.tiene_sentencias(sql):
                lineas.append(f"-- {app}.{nombre}: {self.motivo_sin_sentencias(app, nombre)}\n")
                continue

            lineas.append(f"\n-- ----------------------------------------------------------")
            lineas.append(f"-- {app}.{nombre}")
            lineas.append("-- ----------------------------------------------------------")
            lineas.append(sql)
            lineas.append("")

        return "\n".join(lineas) + "\n"

    # -- Carga inicial -----------------------------------------------------

    def generar_carga_inicial(self):
        lineas = [self.cabecera("Carga inicial de datos")]
        lineas.append(
            "-- Los roles y los planes no son datos de ejemplo: sin ellos el sistema no\n"
            "-- funciona, porque no se puede registrar a nadie. Por eso viajan con la\n"
            "-- estructura. Las cuentas de prueba NO están aquí: se cargan aparte, con\n"
            "-- el comando cargar_datos_demo, para no crearlas nunca sin querer.\n"
        )

        lineas.append("\n-- Roles del sistema")
        for rol in Rol.objects.order_by("id"):
            lineas.append(
                "INSERT INTO rol (id, nombre, descripcion) VALUES "
                f"({rol.id}, {self.texto(rol.nombre)}, {self.texto(rol.descripcion)});"
            )

        lineas.append("\n-- Planes de suscripción")
        for plan in Plan.objects.order_by("id"):
            lineas.append(
                "INSERT INTO plan (id, nombre, precio_mensual, maximo_sedes, maximo_usuarios, "
                "permite_facturacion, permite_reportes_avanzados, activo) VALUES "
                f"({plan.id}, {self.texto(plan.nombre)}, {plan.precio_mensual}, "
                f"{self.numero(plan.maximo_sedes)}, {self.numero(plan.maximo_usuarios)}, "
                f"{int(plan.permite_facturacion)}, {int(plan.permite_reportes_avanzados)}, "
                f"{int(plan.activo)});"
            )

        return "\n".join(lineas) + "\n"

    # -- Utilidades --------------------------------------------------------

    def cabecera(self, titulo):
        return (
            "-- ============================================================\n"
            "--  INVENTRA — Inventario y ventas para licoreras\n"
            f"--  {titulo}\n"
            "-- ============================================================\n"
            f"--  Generado el {datetime.now():%Y-%m-%d} con "
            f"py manage.py generar_scripts_sql\n"
            f"--  Django {django.get_version()} · motor "
            f"{connection.vendor} · base «{connection.settings_dict['NAME']}»\n"
            "-- ============================================================\n"
        )

    def motivo_sin_sentencias(self, app, nombre):
        """
        Por qué esta migración no produjo una sola sentencia.

        El script llamaba «migración de datos» a todas las que salían vacías.
        Era cierto de `0002_datos_planes`, que carga filas con RunPython, y
        falso de `0004_alter_suscripcion_fecha_fin`, que es de estructura y cuyo
        único cambio —un `help_text`— no llega a la base.

        El primer intento de arreglo escribía, para todas las demás, que cambian
        atributos del modelo. También afirmaba de más: `auth.0006` y
        `token_blacklist.0011` no tienen ni una operación —solo declaran un
        orden de dependencias—, y las de `auth` sobre el usuario salen vacías
        por un motivo distinto, que este proyecto usa modelo de usuario propio y
        Django las deja sin efecto.

        De ahí la forma final: tres casos que el script SÍ puede distinguir
        mirando las operaciones, y para el resto el hecho desnudo —qué
        operaciones tiene— sin aventurar la causa. Un entregable generado puede
        decir poco; lo que no puede es decir algo que no sea verdad.
        """
        migracion = self.cargador.disk_migrations.get((app, nombre))
        if migracion is None:
            return "no produjo sentencias"

        operaciones = list(migracion.operations)
        if not operaciones:
            return "sin operaciones; solo declara un orden de dependencias"
        if any(isinstance(op, (RunPython, RunSQL)) for op in operaciones):
            return "migración de datos, sin estructura"

        nombres = sorted({type(op).__name__ for op in operaciones})
        return ("no produjo sentencias en este proyecto; sus operaciones (%s) no "
                "llegan a la base" % ", ".join(nombres))

    @staticmethod
    def tiene_sentencias(sql):
        """¿Queda algo cuando se quitan los comentarios y las líneas vacías?"""
        return any(
            linea.strip() and not linea.strip().startswith("--")
            for linea in sql.splitlines()
        )

    @staticmethod
    def texto(valor):
        """Entrecomilla un texto para SQL, duplicando las comillas de dentro."""
        if valor is None:
            return "NULL"
        return "'" + str(valor).replace("'", "''") + "'"

    @staticmethod
    def numero(valor):
        return "NULL" if valor is None else str(valor)
