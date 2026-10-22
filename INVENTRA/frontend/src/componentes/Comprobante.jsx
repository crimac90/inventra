/*
  El comprobante de una venta (RF-VEN-03).

  Vive en un componente propio y no dentro del punto de venta porque lo piden
  dos sitios: la caja al cobrar y el historial cuando el cliente vuelve a los
  diez segundos diciendo que si lo queria. Si estuviera dentro de la pantalla
  de cobro, el historial tendria que dibujarlo otra vez y los dos papeles
  acabarian pareciendose en vez de ser el mismo.

  Al imprimir sale solo el: la clase `hoja` marca lo que va al papel y la
  hoja de impresion retira el resto, de modo que lo que se ve es lo que sale. No es una factura electronica —eso es FAC—: es el
  documento con el que el negocio entrega la compra.

  `onCerrar` es opcional. En la caja cierra el comprobante y deja la pantalla
  lista para la venta siguiente; en el historial no hay nada que cerrar.
*/

import { moneda } from "../formato";
import { plural } from "../texto";

export default function Comprobante({ venta, onCerrar }) {
  const entregado = venta.monto_recibido === null || venta.monto_recibido === undefined
    ? null : Number(venta.monto_recibido);

  return (
    <div className="tarjeta hoja">
      <h2>Comprobante</h2>
      <div className="comprobante">
        <div className="centro">
          <b>Venta #{venta.consecutivo}</b>
          <div>{new Date(venta.fecha).toLocaleString("es-CO")}</div>
          <div>Atendió: {venta.vendedor}</div>
        </div>
        <hr />
        {venta.lineas.map((linea) => (
          <div className="fila" key={linea.id}>
            <span>{linea.cantidad} {linea.producto_nombre}</span>
            <span>{moneda(Number(linea.subtotal))}</span>
          </div>
        ))}
        <hr />
        <div className="fila"><b>TOTAL</b><b>{moneda(Number(venta.total))}</b></div>
        <div className="fila">
          <span>{venta.medio_pago_nombre}</span>
          <span>{moneda(entregado === null ? Number(venta.total) : entregado)}</span>
        </div>
        {entregado !== null && (
          <div className="fila">
            <span>Cambio</span>
            <span>{moneda(entregado - Number(venta.total))}</span>
          </div>
        )}
        <hr />
        <div className="centro">
          {plural(venta.lineas.length, "referencia")} · Gracias por su compra
        </div>
      </div>
      <div className="acciones">
        <button className="btn btn-out btn-pequeno" type="button"
                onClick={() => window.print()}>
          Imprimir
        </button>
        {onCerrar && (
          <button className="btn btn-cta btn-pequeno" type="button" onClick={onCerrar}>
            Nueva venta
          </button>
        )}
      </div>
    </div>
  );
}
