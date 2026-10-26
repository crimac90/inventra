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

  Se dibuja de dos maneras, y la diferencia no es de gusto. En la caja aparece
  sobre la pantalla, debajo del carrito, porque es el final de lo que se
  acababa de hacer y la vista sigue siendo la caja. En el historial se abre en
  una ventana: alli se llega buscando una venta entre muchas, y dejar el papel
  colgado al pie de la tabla obliga a desplazarse para encontrarlo y a
  desplazarse otra vez para seguir.

  `onCerrar` es opcional en la caja —cierra el comprobante y deja la pantalla
  lista para la venta siguiente— y obligado en la ventana, que si no no tendria
  salida.
*/

import { useEffect } from "react";

import { moneda } from "../formato";
import { plural } from "../texto";

export default function Comprobante({ venta, onCerrar, enVentana = false }) {
  // La tecla Escape cierra, como en cualquier ventana del sistema operativo y
  // como ya hace la de confirmacion.
  useEffect(() => {
    if (!enVentana || !onCerrar) return undefined;
    function alPulsar(evento) {
      if (evento.key === "Escape") onCerrar();
    }
    document.addEventListener("keydown", alPulsar);
    return () => document.removeEventListener("keydown", alPulsar);
  }, [enVentana, onCerrar]);

  const entregado = venta.monto_recibido === null || venta.monto_recibido === undefined
    ? null : Number(venta.monto_recibido);

  const papel = (
    <div className="tarjeta">
      <h2>Comprobante</h2>
      <div className="comprobante">
        <div className="centro">
          <b>{venta.licorera_nombre}</b>
          {venta.licorera_nit && <div>NIT {venta.licorera_nit}</div>}
        </div>
        <hr />
        <div className="centro">
          <b>Venta #{venta.consecutivo}</b>
          <div>{new Date(venta.fecha).toLocaleString("es-CO")}</div>
          <div>Atendió: {venta.vendedor}</div>
          {venta.observacion && <div><b>{venta.observacion}</b></div>}
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
            {/*
              El boton hace lo mismo en los dos sitios y no dice lo mismo,
              porque lo que ocurre al pulsarlo es distinto: en la caja retira
              el papel y deja la pantalla lista para cobrar otra vez; en el
              historial solo cierra la ventana y devuelve a la tabla.
            */}
            {enVentana ? "Cerrar" : "Nueva venta"}
          </button>
        )}
      </div>
    </div>
  );

  /*
    La clase `hoja` marca lo que va al papel y va SIEMPRE en el elemento de
    mas afuera, sea la tarjeta o la ventana: la hoja de impresion esconde lo
    que cuelga del contenido y no la lleva, de modo que ponerla dentro de la
    ventana dejaria fuera al comprobante entero.
  */
  if (!enVentana) return <div className="hoja">{papel}</div>;

  return (
    <div className="modal-fondo hoja" role="dialog" aria-modal="true"
         aria-label={`Comprobante de la venta ${venta.consecutivo}`}>
      {papel}
    </div>
  );
}
