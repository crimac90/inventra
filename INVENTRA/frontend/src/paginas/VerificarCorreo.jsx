/*
  Confirmacion del correo desde el enlace del mensaje (D-10).

  La direccion de esta pantalla tiene que coincidir EXACTAMENTE con la que arma
  el backend en `seguridad/correo.py`:

      {FRONTEND_URL}/verificar-correo?token=...

  A diferencia del restablecimiento, aqui no hay formulario: la persona ya hizo
  todo lo que tenia que hacer al pulsar el enlace. La pantalla llama a la API en
  cuanto se monta y solo informa del resultado. Por eso el estado se llama
  «situacion» y no tiene campos.
*/

import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import PanelMarca from "../componentes/PanelMarca";
import { ErrorApi } from "../api/cliente";
import { verificarCorreo } from "../api/seguridad";

const VINETAS = [
  { marca: "✓", texto: "Confirma que el correo es tuyo" },
  { marca: "✓", texto: "Es a donde llega el enlace si olvidas la contraseña" },
  { marca: "✓", texto: "Se hace una sola vez" },
];

export default function VerificarCorreo() {
  const [situacion, setSituacion] = useState("comprobando");
  const [mensaje, setMensaje] = useState("");

  /*
    En desarrollo React monta cada componente dos veces para detectar efectos mal
    escritos. Sin esta guarda, la pantalla llamaria dos veces a la API y el
    segundo intento sobraria. No cambia el resultado —confirmar dos veces es
    inofensivo— pero envia una peticion de mas contra un limite por origen.
  */
  const yaSeLlamo = useRef(false);

  useEffect(() => {
    if (yaSeLlamo.current) return;
    yaSeLlamo.current = true;

    const token = new URLSearchParams(window.location.search).get("token");
    if (!token) {
      setSituacion("error");
      setMensaje("El enlace llegó incompleto. Pide uno nuevo desde tu perfil.");
      return;
    }

    verificarCorreo(token)
      .then((datos) => {
        setSituacion("listo");
        setMensaje(datos?.detalle || "Tu correo quedó confirmado.");
      })
      .catch((error) => {
        setSituacion("error");
        setMensaje(
          error instanceof ErrorApi && error.datos?.token
            ? [].concat(error.datos.token)[0]
            : "No pudimos confirmar el correo. Inténtalo de nuevo más tarde.",
        );
      });
  }, []);

  return (
    <div className="acceso">
      <div className="acceso-caja">
        <PanelMarca
          titular="Confirma tu correo."
          frase="Un paso y queda listo."
          vinetas={VINETAS}
        />

        <div className="formulario">
          <h1>Confirmación del correo</h1>

          {situacion === "comprobando" && (
            <div className="hs" role="status">
              Comprobando el enlace…
            </div>
          )}

          {situacion === "listo" && (
            <div className="aviso ok" role="status">
              {mensaje}
            </div>
          )}

          {situacion === "error" && (
            <div className="aviso err" role="alert">
              {mensaje}
            </div>
          )}

          <Link className="btn btn-cta full" to="/acceso" style={{ marginTop: 6 }}>
            Ir a INVENTRA
          </Link>
        </div>
      </div>
    </div>
  );
}
