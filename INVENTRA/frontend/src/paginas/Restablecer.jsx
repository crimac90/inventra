/*
  Definicion de la contrasena nueva desde el enlace del correo (RF-SEG-04).

  La direccion de esta pantalla tiene que coincidir EXACTAMENTE con la que arma
  el backend en `seguridad/correo.py`:

      {FRONTEND_URL}/restablecer-contrasena?uid=...&token=...

  Los dos valores viajan en la direccion, no en la pagina, porque quien abre el
  enlace llega desde su gestor de correo sin ningun estado previo. La pantalla los
  lee y se los entrega a la API tal cual; no los interpreta ni los valida, de eso
  se encarga el servidor.
*/

import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import Campo from "../componentes/Campo";
import PanelMarca from "../componentes/PanelMarca";
import { ErrorApi } from "../api/cliente";
import { restablecerContrasena } from "../api/seguridad";

const VINETAS = [
  { marca: "✓", texto: "Mínimo 8 caracteres" },
  { marca: "✓", texto: "Debe combinar letras y números" },
  { marca: "✓", texto: "La contraseña anterior deja de servir" },
];

export default function Restablecer() {
  const [parametros] = useSearchParams();
  const navegar = useNavigate();

  const uid = parametros.get("uid");
  const token = parametros.get("token");

  const [password, setPassword] = useState("");
  const [confirmacion, setConfirmacion] = useState("");
  const [errores, setErrores] = useState({});
  const [aviso, setAviso] = useState("");
  const [enviando, setEnviando] = useState(false);

  // El enlace llegó incompleto: ni siquiera vale la pena molestar al servidor.
  const enlaceIncompleto = !uid || !token;

  const completo = password !== "" && confirmacion !== "";

  async function enviar(evento) {
    evento.preventDefault();
    setAviso("");
    setErrores({});

    /*
      Esta comprobación es solo del navegador: el backend no pide confirmación,
      porque el segundo campo no aporta seguridad, aporta comodidad. Sirve para
      que nadie se quede fuera por una errata que no puede ver.
    */
    if (password !== confirmacion) {
      setErrores({ confirmacion: "Las dos contraseñas no coinciden." });
      return;
    }

    setEnviando(true);
    try {
      await restablecerContrasena({ uid, token, password });
      navegar("/acceso", {
        replace: true,
        state: { mensaje: "Tu contraseña se actualizó. Ya puedes ingresar con la nueva." },
      });
    } catch (error) {
      if (error instanceof ErrorApi && error.codigo === 400) {
        const porCampo = error.porCampo;
        // El error del token no pertenece a ningún campo del formulario: se
        // muestra arriba, con el enlace para pedir uno nuevo.
        if (porCampo.token) setAviso(porCampo.token);
        if (porCampo.password) setErrores({ password: porCampo.password });
        if (!porCampo.token && !porCampo.password) setAviso(error.mensaje);
      } else {
        setAviso(error instanceof ErrorApi ? error.mensaje : "Ocurrió un error inesperado.");
      }
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="acceso">
      <div className="acceso-caja">
        <PanelMarca
          titular="Define tu contraseña nueva."
          frase="Solo tú puedes verla; nadie en INVENTRA la conoce."
          vinetas={VINETAS}
        />

        <div className="formulario">
          <h1>Nueva contraseña</h1>

          {enlaceIncompleto ? (
            <>
              <div className="aviso err" role="alert">
                El enlace no es válido o está incompleto. Solicita uno nuevo.
              </div>
              <div className="foot">
                <Link className="link" to="/recuperar">
                  Solicitar un enlace nuevo
                </Link>
              </div>
            </>
          ) : (
            <form onSubmit={enviar} noValidate>
              <div className="hs">Escríbela dos veces para evitar una errata.</div>

              {aviso && (
                <div className="aviso err" role="alert">
                  {aviso}{" "}
                  <Link className="link" to="/recuperar">
                    Solicitar uno nuevo
                  </Link>
                </div>
              )}

              <Campo
                id="password"
                etiqueta="Contraseña nueva"
                tipo="password"
                marcador="••••••••"
                autoComplete="new-password"
                ayuda="Mínimo 8 caracteres, con letras y números."
                valor={password}
                onChange={(v) => {
                  setPassword(v);
                  setErrores({});
                }}
                error={errores.password}
              />

              <Campo
                id="confirmacion"
                etiqueta="Repite la contraseña"
                tipo="password"
                marcador="••••••••"
                autoComplete="new-password"
                valor={confirmacion}
                onChange={(v) => {
                  setConfirmacion(v);
                  setErrores({});
                }}
                error={errores.confirmacion}
              />

              <button
                className="btn btn-cta full"
                type="submit"
                disabled={!completo || enviando}
                style={{ marginTop: "6px" }}
              >
                {enviando ? "Guardando…" : "Guardar contraseña"}
              </button>

              <div className="foot">
                <Link className="link" to="/acceso">
                  Volver al inicio de sesión
                </Link>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
