# -*- coding: utf-8 -*-
"""
Restauración de una copia de seguridad de INVENTRA.

QUE HACE
Toma un respaldo producido por `respaldo.py` y lo carga en una base de datos.
Antes de escribir nada comprueba que el archivo esté entero, y al terminar
cuenta las filas de las tablas que sostienen la operación, que es la única
forma de saber que la restauración sirvió.

Por que exige confirmacion
Restaurar reemplaza lo que haya en la base de destino. La orden no corre sin
`--si-estoy-seguro`, por la misma razón por la que la carga de datos de
demostración tampoco lo hace: una tecla de más no puede costar la operación de
un negocio.

Por que restaurar en otra base es lo normal, y no la excepcion
La prueba de que un respaldo sirve es restaurarlo. Hacerlo sobre la base viva
para comprobarlo sería destruir lo bueno para averiguar si lo guardado valía,
de modo que `--base` apunta a una base de ensayo y la restauración real sobre
la base de producción es el caso raro, no el corriente.

USO
    python restaurar.py --archivo respaldos/inventra_20261104_0300.sql.gz \\
                        --base inventra_ensayo --si-estoy-seguro
    python restaurar.py --archivo ... --base ... --simular
"""

import argparse
import gzip
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
BACKEND = AQUI.parent

MARCA_DE_FIN = b"Dump completed"

# Las tablas del sistema construido cuyo vacío significaría que la restauración
# no sirvió para nada. No se escriben de memoria a partir del modelo de datos
# diseñado: el modelo especifica veinticuatro tablas y el sistema entregado
# tiene quince, porque cuatro de los ocho módulos quedaron sin construir. Una
# lista copiada del diseño pregunta por tablas que no existen.
NUCLEO = ["licorera", "usuario", "producto", "lote_inventario",
          "movimiento_inventario", "venta", "detalle_venta"]


def leer_env(ruta):
    valores = {}
    if not ruta.is_file():
        return valores
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        valores[clave.strip()] = valor.strip()
    return valores


def credenciales():
    del_archivo = leer_env(BACKEND / ".env")

    def dato(clave, defecto=None):
        return os.environ.get(clave) or del_archivo.get(clave) or defecto

    faltan = [c for c in ("DB_USUARIO", "DB_CONTRASENA") if not dato(c)]
    if faltan:
        raise SystemExit("Faltan datos de conexión: %s" % ", ".join(faltan))
    return {
        "nombre": dato("DB_NOMBRE"),
        "usuario": dato("DB_USUARIO"),
        "contrasena": dato("DB_CONTRASENA"),
        "host": dato("DB_HOST", "127.0.0.1"),
        "puerto": dato("DB_PUERTO", "3306"),
    }


def ruta_de_mysql(indicada):
    if indicada:
        return indicada
    encontrado = shutil.which("mysql")
    if encontrado:
        return encontrado
    raise SystemExit(
        "No se encontró «mysql». Está en la carpeta bin de MySQL; se indica "
        "con --mysql o con la variable MYSQL.")


def legible(bytes_):
    """El tamaño en la unidad que se entiende. «0.0 MB» no dice nada."""
    if bytes_ < 1024:
        return "%d bytes" % bytes_
    if bytes_ < 1048576:
        return "%.1f KB" % (bytes_ / 1024.0)
    return "%.1f MB" % (bytes_ / 1048576.0)


def comprobar_el_archivo(ruta):
    """Que el respaldo esté entero, antes de tocar la base de destino."""
    if not ruta.is_file():
        raise SystemExit("No existe el archivo %s" % ruta)
    ultimo = b""
    with gzip.open(str(ruta), "rb") as entrada:
        for trozo in iter(lambda: entrada.read(1 << 20), b""):
            ultimo = trozo[-200:] if len(trozo) >= 200 else (ultimo + trozo)[-200:]
    if MARCA_DE_FIN not in ultimo:
        raise SystemExit(
            "El respaldo %s no llegó al final: no se restaura. Un volcado "
            "cortado carga tablas a medias y deja la base peor que vacía."
            % ruta.name)
    return ruta.stat().st_size


def descomprimir(origen):
    """Deja el volcado sin comprimir en un archivo temporal y devuelve su ruta.

    Por que un archivo y no el flujo directo
    Pasarle a `mysql` el objeto que devuelve `gzip.open` parece lo natural y es
    una trampa: ese objeto tiene `fileno()`, y lo que devuelve es el descriptor
    del archivo COMPRIMIDO. El proceso hijo no ve la descompresión de Python;
    recibe los bytes en crudo y responde que encontró un carácter nulo donde
    esperaba una orden. El síntoma no se parece en nada a la causa.

    Se descomprime a un temporal, se usa y se borra. El temporal ocupa lo que
    ocupa el volcado sin comprimir, que es el precio de hacerlo sin
    sobresaltos.
    """
    destino = tempfile.NamedTemporaryFile(prefix="inventra_", suffix=".sql",
                                          delete=False)
    try:
        with gzip.open(str(origen), "rb") as comprimido:
            for trozo in iter(lambda: comprimido.read(1 << 20), b""):
                destino.write(trozo)
    finally:
        destino.close()
    return Path(destino.name)


def correr_mysql(programa, cred, base, entrada=None, consulta=None):
    orden = [programa,
             "--host=%s" % cred["host"],
             "--port=%s" % cred["puerto"],
             "--user=%s" % cred["usuario"],
             "--default-character-set=utf8mb4"]
    if consulta:
        orden += ["--batch", "--skip-column-names", "--execute=%s" % consulta]
    if base:
        orden.append(base)
    entorno = dict(os.environ, MYSQL_PWD=cred["contrasena"])
    return subprocess.run(orden, stdin=entrada, env=entorno,
                          capture_output=True)


def comprobar_el_destino(programa, cred, base):
    """Que la base de destino exista y se pueda escribir en ella.

    El programa NO la crea. La cuenta con la que corre la aplicación no tiene
    permiso para crear bases de datos, y es deliberado: una cuenta que puede
    crear bases también puede borrarlas, y la aplicación no necesita ninguna de
    las dos cosas. Crear la base de ensayo es un acto de quien administra el
    motor, se hace una vez y se concede el permiso justo sobre ella.
    """
    r = correr_mysql(programa, cred, base, consulta="SELECT 1")
    if r.returncode == 0:
        return
    detalle = r.stderr.decode("utf-8", "replace").strip()
    raise SystemExit(
        "No se puede escribir en la base «%s»: %s\n\n"
        "Si todavía no existe, quien administra MySQL la crea una vez con:\n\n"
        "    CREATE DATABASE `%s` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n"
        "    GRANT ALL PRIVILEGES ON `%s`.* TO '%s'@'%s';\n"
        "    FLUSH PRIVILEGES;\n"
        % (base, detalle[:200], base, base, cred["usuario"], cred["host"]))


def main():
    lector = argparse.ArgumentParser(description="Restauración de un respaldo de INVENTRA.")
    lector.add_argument("--archivo", required=True, help="respaldo .sql.gz a restaurar")
    lector.add_argument("--base", required=True, help="base de datos de destino")
    lector.add_argument("--mysql", default=os.environ.get("MYSQL"),
                        help="ruta de mysql, si no está en la ruta de búsqueda")
    lector.add_argument("--si-estoy-seguro", action="store_true", dest="seguro",
                        help="confirma que la base de destino se puede reemplazar")
    lector.add_argument("--simular", action="store_true",
                        help="comprueba el archivo y dice qué haría, sin escribir")
    args = lector.parse_args()

    cred = credenciales()
    archivo = Path(args.archivo)
    tamano = comprobar_el_archivo(archivo)
    print("Respaldo íntegro: %s (%s)" % (archivo.name, legible(tamano)))

    if args.simular:
        comprobar_el_destino(ruta_de_mysql(args.mysql), cred, args.base)
        print("Restauraría sobre la base «%s» en %s:%s"
              % (args.base, cred["host"], cred["puerto"]))
        print("Después contaría las filas de cada tabla de la base, y exigiría\n        que no estén vacías las del núcleo: %s" % ", ".join(NUCLEO))
        return 0

    if not args.seguro:
        raise SystemExit(
            "Restaurar reemplaza el contenido de «%s». Si es lo que quieres, "
            "repite la orden con --si-estoy-seguro." % args.base)

    programa = ruta_de_mysql(args.mysql)
    comprobar_el_destino(programa, cred, args.base)

    plano = descomprimir(archivo)
    try:
        with open(str(plano), "rb") as entrada:
            r = correr_mysql(programa, cred, args.base, entrada=entrada)
    finally:
        plano.unlink(missing_ok=True)
    if r.returncode != 0:
        raise SystemExit("La restauración falló: %s"
                         % r.stderr.decode("utf-8", "replace").strip()[:300])

    # Las tablas se preguntan a la base restaurada y no a una lista escrita
    # aquí: el recuento tiene que describir lo que hay, no lo que se esperaba.
    r = correr_mysql(programa, cred, args.base, consulta=(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE' "
        "ORDER BY table_name"))
    if r.returncode != 0:
        print("Restaurado, pero no se pudo leer la lista de tablas: %s"
              % r.stderr.decode("utf-8", "replace").strip()[:200], file=sys.stderr)
        return 1
    tablas = [x.strip() for x in r.stdout.decode("utf-8", "replace").splitlines() if x.strip()]
    if not tablas:
        print("La base «%s» quedó sin tablas: la restauración no sirvió."
              % args.base, file=sys.stderr)
        return 1

    consulta = " UNION ALL ".join(
        "SELECT '%s', COUNT(*) FROM `%s`" % (x, x) for x in tablas)
    r = correr_mysql(programa, cred, args.base, consulta=consulta)
    if r.returncode != 0:
        print("Restaurado, pero no se pudieron contar las filas: %s"
              % r.stderr.decode("utf-8", "replace").strip()[:200], file=sys.stderr)
        return 1

    cuentas = {}
    for linea in r.stdout.decode("utf-8", "replace").strip().splitlines():
        tabla, _, cuantas = linea.partition("\t")
        cuentas[tabla] = cuantas.strip()

    print("Restaurado sobre «%s»: %d tablas." % (args.base, len(tablas)))
    for tabla in tablas:
        marca = " *" if tabla in NUCLEO else ""
        print("  %-26s %8s%s" % (tabla, cuentas.get(tabla, "?"), marca))
    print("  (* tablas del núcleo de la operación)")

    ausentes = [x for x in NUCLEO if x not in cuentas]
    vacias = [x for x in NUCLEO if cuentas.get(x) == "0"]
    if ausentes:
        print("Faltan tablas del núcleo: %s" % ", ".join(ausentes), file=sys.stderr)
    if vacias:
        print("Tablas del núcleo vacías: %s" % ", ".join(vacias), file=sys.stderr)
    return 1 if (ausentes or vacias) else 0


if __name__ == "__main__":
    sys.exit(main())
