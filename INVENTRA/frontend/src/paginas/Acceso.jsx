/*
  Pantalla de inicio de sesion (RF-SEG-02, punto 7.1 del documento de diseno).

  Composicion, campos y textos tomados del prototipo: correo, contrasena,
  casilla «Recordarme», enlace de recuperacion, boton «Ingresar» y acceso al
  registro.
*/

import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import Campo from "../componentes/Campo";
import PanelMarca from "../componentes/PanelMarca";
import { ErrorApi } from "../api/cliente";
import { useSesion } from "../sesion/ContextoSesion";

const VINETAS = [
  { marca: "✓", texto: "Ventas e inventario en tiempo real" },
  { marca: "✓", texto: "Alertas de stock y reportes de utilidad" },
  { marca: "✓", texto: "Soporte local en español" },
];

export default function Acceso() {
  const { entrar } = useSesion();
  const navegar = useNavigate();
  const ubicacion = useLocation();

  /*
    Cuando se llega desde el restablecimiento o desde el cambio de contrasena,
    esa pantalla deja un mensaje de exito en el estado de la navegacion. Se
    muestra aqui para que el usuario sepa que su cambio si se guardo.
  */
  const confirmacion = ubicacion.state?.mensaje;

  const [correo, setCorreo] = useState("");
  const [password, setPassword] = useState("");
  const [recordar, setRecordar] = useState(false);
  const [aviso, setAviso] = useState("");
  const [enviando, setEnviando] = useState(false);

  // El boton principal permanece deshabilitado mientras falte alguno de los dos
  // campos, tal como lo describe el documento de diseno.
  const completo = correo.trim() !== "" && password !== "";

  async function enviar(evento) {
    evento.preventDefault();
    setAviso("");
    setEnviando(true);

    try {
      await entrar({ correo: correo.trim(), password }, recordar);
      navegar("/panel", { replace: true });
    } catch (error) {
      /*
        Un 401 son credenciales incorrectas, una cuenta inactiva o una cuenta
        bloqueada; el backend ya devuelve el texto adecuado y deliberadamente
        generico. Cualquier otro codigo es un problema distinto.
      */
      setAviso(error instanceof ErrorApi ? error.mensaje : "Ocurrio un error inesperado.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="acceso">
      <div className="acceso-caja">
        <PanelMarca
          titular="Controla tu inventario y tus ventas, sin complicarte."
          frase="El punto de venta especializado para licoreras."
          vinetas={VINETAS}
        />

        <form className="formulario" onSubmit={enviar} noValidate>
          <h1>Iniciar sesión</h1>
          <div className="hs">Ingresa a tu cuenta para gestionar tu licorera.</div>

          {confirmacion && !aviso && (
            <div className="aviso ok" role="status">
              {confirmacion}
            </div>
          )}

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

          <Campo
            id="password"
            etiqueta="Contraseña"
            tipo="password"
            marcador="••••••••"
            autoComplete="current-password"
            valor={password}
            onChange={setPassword}
          />

          <div className="rowb">
            <label>
              <input
                type="checkbox"
                checked={recordar}
                onChange={(e) => setRecordar(e.target.checked)}
              />
              Recordarme
            </label>
            <Link className="link" to="/recuperar">
              ¿Olvidaste tu contraseña?
            </Link>
          </div>

          <button className="btn btn-cta full" type="submit" disabled={!completo || enviando}>
            {enviando ? "Ingresando…" : "Ingresar"}
          </button>

          <div className="foot">
            ¿No tienes cuenta?{" "}
            <Link className="link" to="/registro">
              Regístrate
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
}
