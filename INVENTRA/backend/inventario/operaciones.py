"""
Las operaciones que mueven inventario, fuera de las vistas.

Mismo criterio que `cambio_de_plan.py` en SUS: lo que mueve existencias no vive
en una vista, porque lo van a disparar la pantalla, la carga de datos de prueba
y —más adelante— el punto de venta. Una vista traduce peticiones; esto es la
regla del negocio.
"""

from django.core.exceptions import ValidationError
from django.db import transaction

from sedes.models import Sede

from .kardex import registrar_movimiento
from .models import EntradaMercancia, LoteInventario, MovimientoInventario
from .peps import consumir


@transaction.atomic
def registrar_entrada(*, licorera, usuario, lineas, proveedor=None, observacion=None,
                      sede=None):
    """
    Registra la llegada de mercancía (RF-INV-05).

    `lineas` es una lista de diccionarios con `producto`, `cantidad` y
    `costo_unitario`. Cada línea crea **un lote con su costo congelado** y su
    movimiento en el kardex.

    Va entera en una transacción: una entrada que creara dos lotes de tres, o
    los lotes sin su movimiento, dejaría el inventario diciendo una cosa y el
    kardex otra, que es el único desacuerdo que este módulo no puede permitirse.

    La sede se pregunta en vez de suponerse (D-31). Hoy la respuesta es siempre
    la sede principal, porque SED no está construido; el día que haya varias,
    cambia esta línea y no las diez que la llaman.
    """
    if not lineas:
        raise ValidationError("La entrada no tiene ninguna línea.")

    if sede is None:
        sede = Sede.principal_de(licorera)
    if sede is None:
        raise ValidationError("La licorera no tiene ninguna sede donde recibir la mercancía.")

    entrada = EntradaMercancia.objects.create(
        licorera=licorera, sede=sede, usuario=usuario,
        proveedor=(proveedor or "").strip() or None,
        observacion=(observacion or "").strip() or None,
    )

    for linea in lineas:
        producto = linea["producto"]
        cantidad = int(linea["cantidad"])
        costo = linea["costo_unitario"]

        if producto.licorera_id != licorera.id:
            # No debería llegar hasta aquí —el serializador limita el catálogo—,
            # pero esta función también la llaman la carga de datos y, mañana,
            # lo que venga: la regla del aislamiento se comprueba donde vive la
            # operación y no solo donde se escribe el formulario.
            raise ValidationError("Ese producto no pertenece a esta licorera.")
        if cantidad <= 0:
            raise ValidationError("La cantidad de cada línea debe ser mayor que cero.")
        if costo is None or costo < 0:
            raise ValidationError("El costo unitario no puede ser negativo.")

        lote = LoteInventario.objects.create(
            producto=producto, sede=sede,
            origen=LoteInventario.Origen.COMPRA, entrada=entrada,
            cantidad_inicial=cantidad, cantidad_disponible=cantidad,
            costo_unitario=costo,
        )
        registrar_movimiento(
            producto=producto, sede=sede,
            tipo=MovimientoInventario.Tipo.ENTRADA,
            cantidad=cantidad, usuario=usuario, lote=lote,
            costo_unitario=costo,
            documento_tipo=MovimientoInventario.Documento.ENTRADA,
            documento_id=entrada.id,
        )

    return entrada


@transaction.atomic
def ajustar_existencias(*, producto, usuario, cantidad, motivo, sede=None):
    """
    Corrige las existencias por merma, rotura o conteo físico (RF-INV-06).

    `cantidad` es la diferencia: positiva si en el conteo sobraron unidades,
    negativa si faltaron. El motivo es obligatorio —lo exige el requisito y lo
    vuelve a exigir el kardex— porque una existencia que cambió y nadie sabe
    explicar es exactamente lo que un inventario sirve para evitar.

    Las dos direcciones no son simétricas:

    - **Hacia abajo** se consumen lotes por antigüedad, igual que una venta:
      las unidades que se perdieron son las más viejas, y hay que saber cuánto
      costaron para que la pérdida valga lo que valió.
    - **Hacia arriba** nace un lote nuevo. Como el MER exige que todo lote
      tenga costo y el formulario de ajuste no pregunta ninguno (D-32), se toma
      el del último lote de esa referencia: unas unidades que aparecen en un
      conteo son mercancía que ya se compró, y su costo más probable es el de
      la compra más reciente. Si nunca hubo una compra, el ajuste se rechaza:
      lo que corresponde ahí es registrar la entrada con su costo real.
    """
    if cantidad == 0:
        raise ValidationError("El ajuste no cambia nada: la diferencia es cero.")
    if not (motivo or "").strip():
        raise ValidationError("Escribe el motivo del ajuste.")

    if sede is None:
        sede = Sede.principal_de(producto.licorera)
    if sede is None:
        raise ValidationError("La licorera no tiene ninguna sede que ajustar.")

    if cantidad < 0:
        consumir(
            producto=producto, sede=sede, cantidad=-cantidad,
            tipo=MovimientoInventario.Tipo.AJUSTE_NEGATIVO,
            usuario=usuario,
            documento_tipo=MovimientoInventario.Documento.AJUSTE,
            # El ajuste no tiene documento propio: el movimiento ES el
            # documento, así que se apunta a sí mismo con el identificador del
            # producto, que es lo que permite agrupar sus líneas al leerlo.
            documento_id=producto.id,
            motivo=motivo,
        )
        return

    ultimo = (
        LoteInventario.objects
        .filter(producto=producto, sede=sede)
        .order_by("-fecha_ingreso", "-id")
        .first()
    )
    if ultimo is None:
        raise ValidationError(
            "«%s» no tiene ninguna entrada registrada, así que no hay un costo con el "
            "que valorar las unidades encontradas. Regístralas como entrada de mercancía."
            % producto.nombre)

    lote = LoteInventario.objects.create(
        producto=producto, sede=sede,
        origen=LoteInventario.Origen.AJUSTE_POSITIVO,
        cantidad_inicial=cantidad, cantidad_disponible=cantidad,
        costo_unitario=ultimo.costo_unitario,
    )
    registrar_movimiento(
        producto=producto, sede=sede,
        tipo=MovimientoInventario.Tipo.AJUSTE_POSITIVO,
        cantidad=cantidad, usuario=usuario, lote=lote,
        costo_unitario=lote.costo_unitario,
        documento_tipo=MovimientoInventario.Documento.AJUSTE,
        documento_id=producto.id,
        motivo=motivo,
    )
