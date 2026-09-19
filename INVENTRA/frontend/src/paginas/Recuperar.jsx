/*
  Solicitud del enlace de recuperacion (RF-SEG-04, punto 7.3 del documento de
  diseno).

  El prototipo no trae figura de esta pantalla; el documento de diseno la
  describe en texto. Se construye con la misma composicion de dos paneles del
  acceso y el registro, y con los componentes del sistema de diseno, para que no
  desentone con las que si tienen figura.

  La regla que manda aqui: «El mensaje en pantalla es el mismo exista o no la
  cuenta». Por eso, pase lo que pase, se muestra la misma confirmacion.
*/

import { useState } from "react";
import { Link } from "react-router-dom";

import Campo from "../componentes/Campo";
import PanelMarca from "../componentes/PanelMarca";
import { ErrorApi } from "../api/cliente";
import { solicitarRecuperacion } from "../api/seguridad";

const VINETAS = [
  { marca: "1", texto: "Escribe tu correo registrado" },
  { marca: "2", texto: "Abre el enlace que te enviamos" },
  { marca: "3", texto: "Define una contraseña nueva" },
];

export default function Recuperar() {
  const [correo, setCorreo] = useState("");
  const [enviado, setEnviado] = useState(false);
  const [aviso, setAviso] = useState("");
  const [enviando, setEnviando] = useState(false);

  async function enviar(evento) {
    evento.preventDefault();
    setAviso("");
    setEnviando(true);

    try {
      await solicitarRecuperacion(correo.trim());
      setEnviado(true);
    } catch (error) {
      /*
        Aqui solo llegan fallos reales —el servidor caido, o el limite de
        peticiones cuando se active—, nunca «ese correo no existe»: el backend
        responde 200 tanto si la cuenta existe como si no.
      */
      setAviso(error instanceof ErrorApi ? error.mensaje : "Ocurrió un error inesperado.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="acceso">
      <div className="acceso-caja">
        <PanelMarca
          titular="¿Olvidaste tu contraseña?"
          frase="Te enviamos un enlace para definir una nueva."
          vinetas={VINETAS}
        />

        <div className="formulario">
          <h1>Recuperar contraseña</h1>

          {enviado ? (
            <>
              <div className="hs">Revisa tu correo.</div>

              <div className="aviso ok" role="status">
                Si el correo corresponde a una cuenta registrada, enviamos un enlace para
                restablecer la contraseña.
              </div>

              <p style={{ color: "var(--muted)", fontSize: "13px" }}>
                El enlace vence en 30 minutos y solo puede usarse una vez. Si no llega,
                revisa la carpeta de correo no deseado antes de volver a intentarlo.
              </p>

              <div className="foot">
                <Link className="link" to="/acceso">
                  Volver al inicio de sesión
                </Link>
              </div>
            </>
          ) : (
            <form onSubmit={enviar} noValidate>
              <div className="hs">
                Escribe el correo con el que te registraste y te enviaremos un enlace.
              </div>

              {aviso && (
                <div className="aviso err" role="alert">
                  {aviso}
                </div>
              )}

              <Campo
                id="correo"
                etiqueta="Correo electrónico"
                tipo="email"
                marcador="nombre@correo.com"
                autoComplete="email"
                valor={correo}
                onChange={setCorreo}
              />

              <button
                className="btn btn-cta full"
                type="submit"
                disabled={correo.trim() === "" || enviando}
                style={{ marginTop: "6px" }}
              >
                {enviando ? "Enviando…" : "Enviar enlace"}
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
