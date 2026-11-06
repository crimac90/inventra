# -*- coding: utf-8 -*-
"""
Copia de seguridad de la base de datos de INVENTRA.

QUE HACE
Vuelca la base completa con `mysqldump`, la comprime y la deja fechada en la
carpeta de respaldos. Comprueba que el volcado terminó entero, anota el
resultado en una bitácora y retira los respaldos que sobran.

Por que no es una orden de Django
Un respaldo tiene que poder ejecutarse cuando la aplicación no arranca, que es
justo cuando más falta hace. Este programa solo necesita Python, `mysqldump` y
las credenciales del archivo `.env`; no importa Django ni abre la aplicación.

QUE NO ES
No implementa RF-AUD-03 ni RF-AUD-04, que piden generar y restaurar copias
*desde la aplicación*, con su registro en la tabla `copia_seguridad`. Ese
módulo queda especificado y sin construir. Esto es la operación del servicio:
lo que corre en el servidor sin que nadie lo pida.

Como sabe que el volcado esta entero
`mysqldump` escribe al final la línea «-- Dump completed». Un volcado cortado
—por falta de espacio, por un corte de red o porque el proceso murió— no la
lleva. Un archivo que pesa y no sirve es peor que un archivo que falta, porque
nadie lo mira hasta el día que hay que restaurar.

USO
    python respaldo.py
    python respaldo.py --carpeta /ruta/respaldos --conservar 14
    python respaldo.py --simular

El dato que importa del resultado es el código de salida: 0 si el respaldo
quedó verificado, 1 si no. La tarea programada se apoya en eso.
"""

import argparse
import gzip
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
BACKEND = AQUI.parent

MARCA_DE_FIN = b"Dump completed"
CONSERVAR_POR_DEFECTO = 7


def leer_env(ruta):
    """Las variables del archivo `.env`, sin depender de ninguna librería."""
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
    """Primero el entorno del proceso; si falta algo, el archivo `.env`."""
    del_archivo = leer_env(BACKEND / ".env")

    def dato(clave, defecto=None):
        return os.environ.get(clave) or del_archivo.get(clave) or defecto

    faltan = [c for c in ("DB_NOMBRE", "DB_USUARIO", "DB_CONTRASENA") if not dato(c)]
    if faltan:
        raise SystemExit(
            "Faltan datos de conexión: %s. Se leen del entorno o de "
            "INVENTRA/backend/.env" % ", ".join(faltan))
    return {
        "nombre": dato("DB_NOMBRE"),
        "usuario": dato("DB_USUARIO"),
        "contrasena": dato("DB_CONTRASENA"),
        "host": dato("DB_HOST", "127.0.0.1"),
        "puerto": dato("DB_PUERTO", "3306"),
    }


def ruta_de_mysqldump(indicada):
    """Dónde está `mysqldump`. En Windows no suele estar en la ruta de búsqueda."""
    if indicada:
        return indicada
    encontrado = shutil.which("mysqldump")
    if encontrado:
        return encontrado
    raise SystemExit(
        "No se encontró «mysqldump». Está en la carpeta bin de MySQL; se indica "
        "con --mysqldump o con la variable MYSQLDUMP.")


def legible(bytes_):
    """El tamaño en la unidad que se entiende. «0.0 MB» no dice nada."""
    if bytes_ < 1024:
        return "%d bytes" % bytes_
    if bytes_ < 1048576:
        return "%.1f KB" % (bytes_ / 1024.0)
    return "%.1f MB" % (bytes_ / 1048576.0)


def nombre_libre(carpeta, momento):
    """Un nombre que no pise nada.

    Dos ejecuciones dentro del mismo segundo producían el mismo nombre, y la
    segunda escribía encima de la primera. Una copia que se escribe encima de
    otra no es una copia: es la misma, y el día que haga falta la anterior no
    estará.
    """
    base = "inventra_%s" % momento.strftime("%Y%m%d_%H%M%S")
    destino = carpeta / (base + ".sql.gz")
    repetida = 1
    while destino.exists():
        destino = carpeta / ("%s_%d.sql.gz" % (base, repetida))
        repetida += 1
    return destino


def volcar(cred, programa, destino):
    """Escribe el volcado comprimido. Devuelve (bytes, verificado)."""
    orden = [
        programa,
        "--host=%s" % cred["host"],
        "--port=%s" % cred["puerto"],
        "--user=%s" % cred["usuario"],
        # Las rutinas y los disparadores no se usan hoy, pero un respaldo que
        # solo trae tablas deja de ser completo en cuanto alguien añada uno.
        "--routines",
        "--triggers",
        "--events",
        # Una restauración tiene que poder caer sobre una base que ya existe.
        "--add-drop-table",
        # Volcado coherente sin bloquear la operación: InnoDB lo permite.
        "--single-transaction",
        "--quick",
        "--default-character-set=utf8mb4",
        cred["nombre"],
    ]
    # La contraseña viaja por el entorno y no por la línea de órdenes: lo que se
    # escribe en la línea lo ve cualquiera que liste los procesos del servidor.
    entorno = dict(os.environ, MYSQL_PWD=cred["contrasena"])

    with gzip.open(str(destino), "wb") as salida:
        proceso = subprocess.Popen(orden, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, env=entorno)
        ultimo = b""
        for trozo in iter(lambda: proceso.stdout.read(1 << 20), b""):
            salida.write(trozo)
            ultimo = trozo[-200:] if len(trozo) >= 200 else (ultimo + trozo)[-200:]
        error = proceso.stderr.read()
        codigo = proceso.wait()

    if codigo != 0:
        destino.unlink(missing_ok=True)
        raise SystemExit("mysqldump terminó con error %d: %s"
                         % (codigo, error.decode("utf-8", "replace").strip()[:300]))
    return destino.stat().st_size, MARCA_DE_FIN in ultimo


def retirar_sobrantes(carpeta, conservar):
    """Deja los `conservar` respaldos más recientes y nombra los que retira."""
    copias = sorted(carpeta.glob("inventra_*.sql.gz"))
    sobran = copias[:-conservar] if conservar > 0 else []
    for vieja in sobran:
        vieja.unlink()
    return [v.name for v in sobran]


def anotar(carpeta, linea):
    with open(str(carpeta / "respaldos.log"), "a", encoding="utf-8") as bitacora:
        bitacora.write(linea + "\n")


def main():
    lector = argparse.ArgumentParser(description="Copia de seguridad de INVENTRA.")
    lector.add_argument("--carpeta", default=str(BACKEND / "respaldos"),
                        help="dónde se guardan las copias (por defecto, backend/respaldos)")
    lector.add_argument("--conservar", type=int, default=CONSERVAR_POR_DEFECTO,
                        help="cuántas copias se conservan (por defecto, 7)")
    lector.add_argument("--mysqldump", default=os.environ.get("MYSQLDUMP"),
                        help="ruta de mysqldump, si no está en la ruta de búsqueda")
    lector.add_argument("--simular", action="store_true",
                        help="dice qué haría y no escribe nada")
    args = lector.parse_args()

    cred = credenciales()
    carpeta = Path(args.carpeta)
    momento = datetime.now()

    if args.simular:
        programa = shutil.which("mysqldump") or args.mysqldump or "(no encontrado)"
        existentes = sorted(carpeta.glob("inventra_*.sql.gz")) if carpeta.is_dir() else []
        print("Base          : %s en %s:%s" % (cred["nombre"], cred["host"], cred["puerto"]))
        print("Programa      : %s" % programa)
        print("Escribiría    : %s"
              % (nombre_libre(carpeta, momento) if carpeta.is_dir()
                 else carpeta / ("inventra_%s.sql.gz" % momento.strftime("%Y%m%d_%H%M%S"))))
        print("Copias ahora  : %d, se conservarían %d" % (len(existentes), args.conservar))
        if len(existentes) >= args.conservar:
            retirar = existentes[:len(existentes) + 1 - args.conservar]
            print("Retiraría     : %s" % ", ".join(v.name for v in retirar))
        return 0

    carpeta.mkdir(parents=True, exist_ok=True)
    destino = nombre_libre(carpeta, momento)
    nombre = destino.name
    programa = ruta_de_mysqldump(args.mysqldump)
    arranque = time.monotonic()
    tamano, verificado = volcar(cred, programa, destino)
    duracion = time.monotonic() - arranque

    sello = momento.strftime("%Y-%m-%d %H:%M:%S")
    if not verificado:
        # Se le cambia la extensión para que no pueda pasar por un respaldo:
        # con el nombre de siempre, la rotación lo contaría como copia buena y
        # retiraría una que sí servía para hacerle sitio.
        apartado = destino.with_suffix("").with_suffix(".sql.gz.cortado")
        destino.rename(apartado)
        anotar(carpeta, "%s  CORTADO   %s  %d bytes" % (sello, apartado.name, tamano))
        print("El volcado no llegó al final: se conserva como %s para "
              "examinarlo, pero no sirve para restaurar." % apartado.name,
              file=sys.stderr)
        return 1

    # La rotación va después de verificar, y no antes: retirar una copia buena
    # para dejar sitio a un volcado que no sirve es perder las dos.
    retirados = retirar_sobrantes(carpeta, args.conservar)
    anotar(carpeta, "%s  CORRECTO  %s  %d bytes  %.1f s%s"
           % (sello, nombre, tamano, duracion,
              ("  · retirados: " + ", ".join(retirados)) if retirados else ""))
    print("Respaldo verificado: %s (%s) en %.1f segundos"
          % (nombre, legible(tamano), duracion))
    if retirados:
        print("Retirados por antigüedad: %s" % ", ".join(retirados))
    return 0


if __name__ == "__main__":
    sys.exit(main())
