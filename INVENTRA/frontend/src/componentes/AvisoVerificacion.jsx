/*
  Aviso de correo sin confirmar (D-10).

  La decision fue NO bloquear el ingreso de una cuenta sin verificar: se entra y
  se trabaja con normalidad, con este aviso a la vista. Bloquear dejaria la
  cuenta inservible si el mensaje no llega, y eso es peor que un correo sin
  confirmar. El manual de usuario lo promete asi, de modo que la franja tiene
  que existir.

  Desaparece sola en cuanto el correo queda confirmado, porque el dato viene del
  usuario de la sesion.
*/

import { useState } from "react";

import { ErrorApi } from "../api/cliente";
import { reenviarVerificacion } from "../api/seguridad";
import { useSesion } from "../sesion/ContextoSesion";

export default function AvisoVerificacion() {
  const { usuario } = useSesion();
  const [enviando, setEnviando] = useState(false);
  const [resultado, setResultado] = useState("");

  if (!usuario || usuario.correo_verificado) return null;

  async function reenviar() {
    setEnviando(true);
    try {
      const datos = await reenviarVerificacion();
      setResultado(datos?.detalle || "Te enviamos un enlace nuevo.");
    } catch (error) {
      /*
        El servidor ya explica el caso más probable —«tu correo ya está
        confirmado», cuando se confirmó en otra pestaña y esta todavía no se ha
        recargado—, así que se muestra su mensaje en vez de uno genérico. Decir
        «inténtalo más tarde» cuando no hay nada que reintentar manda a la
        persona a esperar por nada.
      */
      setResultado(
        error instanceof ErrorApi && error.datos?.detalle
          ? error.datos.detalle
          : "No pudimos enviar el enlace. Inténtalo de nuevo en unos minutos.",
      );
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="aviso advertencia verificacion" role="status">
      <span>
        Falta confirmar tu correo. Te enviamos un enlace a <b>{usuario.correo}</b>; es la
        dirección a la que llegaría el enlace si algún día olvidas tu contraseña.
      </span>
      {resultado ? (
        <b>{resultado}</b>
      ) : (
        <button type="button" className="link" onClick={reenviar} disabled={enviando}>
          {enviando ? "Enviando…" : "Reenviar el enlace"}
        </button>
      )}
    </div>
  );
}
