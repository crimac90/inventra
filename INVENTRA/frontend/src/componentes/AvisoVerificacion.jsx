/*
  Aviso de correo sin confirmar (D-10, ampliado por D-29).

  El ingreso NO se bloquea: se entra con este aviso a la vista. Bloquear dejaria
  la cuenta inservible si el mensaje no llega, y dejaria fuera precisamente a
  quien escribio mal su direccion, que es quien mas necesita entrar para
  corregirla.

  LO QUE CAMBIO CON D-29: mientras el correo siga pendiente la cuenta consulta y
  no registra, asi que esta franja ya no recuerda un tramite: anuncia un limite.
  El texto lo dice, porque una persona que no sabe por que se le rechaza algo
  busca el fallo donde no esta. Y ofrece las dos salidas que existen: reenviar el
  enlace, si la direccion es correcta, o corregirla en «Mi perfil», si no lo es.

  Desaparece sola en cuanto el correo queda confirmado, porque el dato viene del
  usuario de la sesion.
*/

import { useState } from "react";
import { Link } from "react-router-dom";

import { ErrorApi } from "../api/cliente";
import { reenviarVerificacion } from "../api/seguridad";
import { DESTINO_DEL_CORREO } from "../sesion/permisos";
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
        Confirma tu correo para empezar a registrar información. Te enviamos un enlace a{" "}
        <b>{usuario.correo}</b>; mientras tanto puedes consultar todo, pero no registrar nada.
      </span>
      {resultado ? (
        <b>{resultado}</b>
      ) : (
        <>
          <button type="button" className="link" onClick={reenviar} disabled={enviando}>
            {enviando ? "Enviando…" : "Reenviar el enlace"}
          </button>
          {/* La otra salida, y la que nadie mas puede dar a quien se registro
              solo: si la direccion esta mal escrita, el enlace no va a llegar
              por mucho que se reenvie. */}
          <Link to={DESTINO_DEL_CORREO}>¿La dirección está mal?</Link>
        </>
      )}
    </div>
  );
}
