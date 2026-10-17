/*
  Los margenes con los que el sistema propone precios (RF-INV-11).

  Se editan los seis juntos y en una ventana, no en una pantalla: son
  parametros del negocio que se fijan una vez y casi no se vuelven a tocar.
  Darles una pantalla propia seria darles un sitio permanente en el sistema a
  algo que se abre tres veces al ano.

  El sistema PROPONE con estos numeros y no cambia ningun precio: la ventana lo
  dice, porque un porcentaje guardado en un formulario se parece bastante a una
  orden de aplicar.
*/

import { useState } from "react";

import Campo from "./Campo";
import { ErrorApi, mensajeDeError } from "../api/cliente";
import { guardarMargenes } from "../api/inventario";

export default function MargenesPorCategoria({ categorias, onGuardado, onCerrar }) {
  const [valores, setValores] = useState(() =>
    Object.fromEntries(categorias.map((c) => [c.id, String(c.margen_sugerido)])));
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState(null);

  async function enviar(evento) {
    evento.preventDefault();
    setOcupado(true);
    setError(null);
    try {
      const guardadas = await guardarMargenes(
        categorias.map((c) => ({ id: c.id, margen_sugerido: valores[c.id] })));
      onGuardado(guardadas);
    } catch (fallo) {
      setError(fallo instanceof ErrorApi && fallo.codigo === 400
        ? "Revisa los porcentajes: deben ir entre 0 y 500."
        : mensajeDeError(fallo));
    } finally {
      setOcupado(false);
    }
  }

  return (
    <div className="modal-fondo" role="dialog" aria-modal="true"
         aria-label="Márgenes por categoría">
      <form className="modal modal-ancho" onSubmit={enviar} noValidate>
        <h2>Márgenes por categoría</h2>
        <p>
          Con estos porcentajes el sistema propone el precio de venta a partir del
          costo de la última compra. Propone: nunca cambia un precio por su cuenta.
        </p>

        {error && (
          <div className="aviso err" role="alert">
            {error}
          </div>
        )}

        <div className="rejilla-dos">
          {categorias.map((categoria) => (
            <Campo
              key={categoria.id}
              id={`margen-${categoria.id}`}
              etiqueta={`${categoria.nombre} (%)`}
              tipo="number"
              minimo="0"
              valor={valores[categoria.id]}
              onChange={(v) => setValores((previos) => ({ ...previos, [categoria.id]: v }))}
            />
          ))}
        </div>

        <div className="acciones">
          <button className="btn btn-out" type="button" onClick={onCerrar} disabled={ocupado}>
            Cancelar
          </button>
          <button className="btn btn-cta" type="submit" disabled={ocupado}>
            {ocupado ? "Guardando…" : "Guardar márgenes"}
          </button>
        </div>
      </form>
    </div>
  );
}
