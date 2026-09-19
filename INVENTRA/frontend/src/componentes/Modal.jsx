/*
  Ventana de confirmacion (punto 6.6 del documento tecnico de diseno).

  Se usa antes de una accion que el usuario no puede deshacer solo. Tiene tres
  reglas escritas en el documento y que aqui se cumplen: el titulo dice QUE se va
  a hacer, el texto explica la CONSECUENCIA, y el boton de confirmar usa el color
  de peligro de accion mientras el de cancelar queda a la izquierda, con aspecto
  secundario, para que no se pulse por inercia.

  La tecla Escape cierra, como en cualquier ventana del sistema operativo.
*/

import { useEffect } from "react";

export default function Modal({ titulo, mensaje, textoConfirmar, onConfirmar, onCancelar, ocupado }) {
  useEffect(() => {
    function alPulsar(evento) {
      if (evento.key === "Escape") onCancelar();
    }
    document.addEventListener("keydown", alPulsar);
    return () => document.removeEventListener("keydown", alPulsar);
  }, [onCancelar]);

  return (
    <div className="modal-fondo" role="dialog" aria-modal="true" aria-label={titulo}>
      <div className="modal">
        <h2>{titulo}</h2>
        <p>{mensaje}</p>

        <div className="acciones">
          <button className="btn btn-out" type="button" onClick={onCancelar} disabled={ocupado}>
            Cancelar
          </button>
          <button className="btn btn-peligro" type="button" onClick={onConfirmar} disabled={ocupado}>
            {ocupado ? "Un momento…" : textoConfirmar}
          </button>
        </div>
      </div>
    </div>
  );
}
