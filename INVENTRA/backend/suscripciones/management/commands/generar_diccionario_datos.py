"""
Genera el diccionario de datos del sistema CONSTRUIDO, leyendo los modelos.

POR QUÉ EXISTE ESTE ARCHIVO SI YA HAY UN MER
El MER es el documento de DISEÑO: describe las veinticuatro entidades del
sistema completo tal como se pensaron antes de programar, y se entregó con su
revisión 1. Este anexo describe lo que hay CONSTRUIDO, y se genera desde los
propios modelos, así que no puede contradecir a la base de datos.

Tener los dos separados resuelve un problema real: durante la construcción
aparecen desviaciones respecto al diseño —unas impuestas por el marco de
trabajo, otras por decisiones tomadas por el camino—. Retocar el documento de
diseño en cada una lo convertiría en un documento sin fecha ni autoría clara.
Así, el MER dice lo que se diseñó, el anexo dice lo que se hizo, y las
diferencias quedan explicadas en los dos sitios.

USO
    py manage.py generar_diccionario_datos
"""

from datetime import datetime
from pathlib import Path

import django
from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection

# Las aplicaciones del proyecto, en el orden en que conviene leerlas.
APLICACIONES = ["suscripciones", "seguridad"]

DESTINO = (
    Path(settings.BASE_DIR).parent.parent
    / "docs"
    / "diseno"
    / "INVENTRA_Diccionario_Datos_Construido.md"
)

PREAMBULO = """
## Cómo leer este documento

Cada tabla del sistema construido, con el tipo **real** de cada columna en MySQL. Se genera
desde los modelos con `py manage.py generar_diccionario_datos`, así que no puede contradecir
a la base de datos.

El modelo entidad-relación del proyecto (`INVENTRA_MER_MR_Diccionario.docx`) sigue siendo el
documento de diseño y no se modifica: describe las veinticuatro entidades del sistema
completo tal como se concibieron. Este anexo describe lo que hay construido hasta la fecha.

## Dos convenciones del marco de trabajo

Hay dos diferencias sistemáticas entre los tipos del diseño y los de la base construida. No
son descuidos; conviene saber explicarlas.

**Las llaves primarias y foráneas son `bigint`, no `int unsigned`.** Es el tipo que Django
aplica por defecto a los identificadores automáticos, para no agotar el rango en tablas que
crecen sin parar —el kardex y las ventas lo hacen—. Una llave foránea copia el tipo de la
llave a la que apunta, así que la convención se propaga. Se adoptó tal cual: bajarlo a
`int unsigned` exigiría una migración de alteración en cada tabla y en cada módulo nuevo, y
no ganaría nada medible para el tamaño de negocio al que apunta INVENTRA.

**Las columnas de lista cerrada son `varchar`, no `ENUM`.** Django no genera `ENUM` en
ningún caso, y es deliberado: alterar un `ENUM` en MySQL obliga a reescribir la tabla
completa y no es portable entre motores. Lo que hace es guardar el valor como texto y
comprobar la lista de valores válidos en la aplicación, lo que da el mismo resultado para el
usuario y permite añadir un estado nuevo con una migración trivial. Los valores admitidos de
cada una de estas columnas se indican en su descripción.
"""


class Command(BaseCommand):
    help = "Genera el diccionario de datos del sistema construido, desde los modelos."

    def add_arguments(self, parser):
        parser.add_argument("--destino", help="Ruta del archivo a escribir.")

    def handle(self, *args, **opciones):
        destino = Path(opciones["destino"]) if opciones["destino"] else DESTINO
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(self.documento(), encoding="utf-8")

        self.stdout.write(self.style.SUCCESS(f"  escrito {destino.name}"))
        self.stdout.write(f"  {destino}")

    # ----------------------------------------------------------------------

    def documento(self):
        partes = [
            "# INVENTRA — Diccionario de datos del sistema construido",
            "",
            f"> Generado el {datetime.now():%Y-%m-%d} con "
            f"`py manage.py generar_diccionario_datos`  ",
            f"> Django {django.get_version()} · motor {connection.vendor} · "
            f"base «{connection.settings_dict['NAME']}»  ",
            "> **No se edita a mano:** se cambia el modelo y se vuelve a generar.",
            "",
            PREAMBULO.strip(),
            "",
        ]

        for etiqueta in APLICACIONES:
            configuracion = apps.get_app_config(etiqueta)
            partes.append("---")
            partes.append("")
            partes.append(f"## Módulo {etiqueta.upper()[:3]} — {configuracion.verbose_name}")
            partes.append("")

            for modelo in sorted(configuracion.get_models(), key=lambda m: m._meta.db_table):
                partes.extend(self.tabla(modelo))

        return "\n".join(partes) + "\n"

    def tabla(self, modelo):
        meta = modelo._meta
        lineas = [f"### Tabla: `{meta.db_table}`", ""]

        # La descripción sale del docstring del modelo: su primera frase.
        if modelo.__doc__:
            resumen = " ".join(modelo.__doc__.split())
            lineas.append(resumen.split(".")[0].strip() + ".")
            lineas.append("")

        lineas.append("| Columna | Tipo (MySQL) | Nulo | Llave | Descripción |")
        lineas.append("|---|---|---|---|---|")

        for campo in meta.get_fields():
            # Las relaciones inversas no son columnas de esta tabla.
            if not getattr(campo, "concrete", False):
                continue
            lineas.append(self.fila(campo))

        lineas.append("")
        return lineas

    def fila(self, campo):
        columna = campo.db_column or campo.get_attname_column()[1]

        try:
            tipo = campo.db_type(connection) or "—"
        except Exception:   # noqa: BLE001
            tipo = "—"

        if campo.primary_key:
            llave = "PK"
        elif campo.many_to_one or campo.one_to_one:
            llave = f"FK → `{campo.related_model._meta.db_table}`"
        elif campo.unique:
            llave = "UQ"
        else:
            llave = "—"

        descripcion = (campo.help_text or "").strip()
        if not descripcion:
            descripcion = str(campo.verbose_name).capitalize()

        # Si la columna tiene lista cerrada, se enumeran los valores admitidos:
        # es la información que el ENUM del diseño daba en el propio tipo.
        if getattr(campo, "choices", None):
            valores = ", ".join(f"`{valor}`" for valor, _ in campo.choices)
            descripcion = f"{descripcion} Valores admitidos: {valores}."

        return (
            f"| `{columna}` | {tipo} | {'Sí' if campo.null else 'No'} | {llave} | "
            f"{descripcion} |"
        )
