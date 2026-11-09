/*
  Pantalla de registro de la licorera (CU-SUS-01, punto 7.2 del documento de
  diseno).

  Cuatro campos: nombre del negocio, nombre y apellido, correo y contrasena. Al
  completarlo, el backend crea en una sola operacion la licorera, su suscripcion
  al plan Basico y el usuario administrador, y devuelve los tokens; por eso el
  usuario entra directo al panel sin volver a iniciar sesion.
*/

import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import Campo from "../componentes/Campo";
import PanelMarca from "../componentes/PanelMarca";
import { ErrorApi, avisoDeFormulario, mensajeDeError } from "../api/cliente";
import { registrarLicorera } from "../api/seguridad";
import { useSesion } from "../sesion/ContextoSesion";

const VINETAS = [
  { marca: "1", texto: "Registra tu negocio" },
  { marca: "2", texto: "Carga tus productos" },
  { marca: "3", texto: "Empieza a vender" },
];

const INICIAL = {
  nombre_negocio: "",
  nombre_completo: "",
  correo: "",
  password: "",
};

export default function Registro() {
  const { setUsuario } = useSesion();
  const navegar = useNavigate();

  const [datos, setDatos] = useState(INICIAL);
  const [acepta, setAcepta] = useState(false);
  const [verPolitica, setVerPolitica] = useState(false);
  const [errores, setErrores] = useState({});
  const [aviso, setAviso] = useState("");
  const [enviando, setEnviando] = useState(false);

  function cambiar(campo) {
    return (valor) => {
      setDatos((previo) => ({ ...previo, [campo]: valor }));
      // Al corregir un campo, su error desaparece: el usuario no debe quedarse
      // mirando un mensaje que ya no aplica.
      setErrores((previo) => ({ ...previo, [campo]: undefined }));
    };
  }

  const completo = Object.values(datos).every((v) => v.trim() !== "") && acepta;

  async function enviar(evento) {
    evento.preventDefault();
    setAviso("");
    setErrores({});
    setEnviando(true);

    try {
      const usuario = await registrarLicorera({
        ...datos,
        nombre_negocio: datos.nombre_negocio.trim(),
        nombre_completo: datos.nombre_completo.trim(),
        correo: datos.correo.trim(),
        acepta_tratamiento_datos: acepta,
      });
      setUsuario(usuario);
      navegar("/panel", { replace: true });
    } catch (error) {
      if (error instanceof ErrorApi && error.codigo === 400) {
        /*
          El 400 significa que los datos no pasaron la validacion, y el backend
          dice exactamente cual: correo repetido, contrasena que no cumple la
          politica. Se reparten los mensajes por campo.
        */
        const porCampo = error.porCampo;
        setErrores(porCampo);
        setAviso(avisoDeFormulario(error, porCampo));
      } else {
        setAviso(mensajeDeError(error));
      }
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="acceso">
      <div className="acceso-caja">
        <PanelMarca
          titular="Crea tu cuenta en minutos."
          frase="Empieza con el plan Básico y crece cuando quieras."
          vinetas={VINETAS}
        />

        <form className="formulario" onSubmit={enviar} noValidate>
          <h1>Crear cuenta</h1>
          <div className="hs">Registra tu licorera y tu usuario administrador.</div>

          {aviso && (
            <div className="aviso err" role="alert">
              {aviso}
            </div>
          )}

          <Campo
            id="nombre_negocio"
            etiqueta="Nombre del negocio"
            marcador="Licorera La Esquina"
            autoComplete="organization"
            valor={datos.nombre_negocio}
            onChange={cambiar("nombre_negocio")}
            error={errores.nombre_negocio}
          />

          <Campo
            id="nombre_completo"
            etiqueta="Nombre y apellido"
            marcador="Cristian Macías"
            autoComplete="name"
            valor={datos.nombre_completo}
            onChange={cambiar("nombre_completo")}
            error={errores.nombre_completo}
          />

          <Campo
            id="correo"
            etiqueta="Correo electrónico"
            tipo="email"
            marcador="nombre@correo.com"
            autoComplete="email"
            valor={datos.correo}
            onChange={cambiar("correo")}
            error={errores.correo}
          />

          <Campo
            id="password"
            etiqueta="Contraseña"
            tipo="password"
            marcador="••••••••"
            autoComplete="new-password"
            ayuda="Mínimo 8 caracteres, con letras y números."
            valor={datos.password}
            onChange={cambiar("password")}
            error={errores.password}
          />

          {/*
            La aceptacion del tratamiento de datos (Ley 1581 de 2012). El texto
            se muestra aqui y no detras de un enlace a otra pagina: quien se
            registra tiene que poder leerlo sin abandonar el formulario que
            esta llenando.
          */}
          <label className="casilla">
            <input
              type="checkbox"
              checked={acepta}
              onChange={(e) => setAcepta(e.target.checked)}
            />
            <span>
              Autorizo el tratamiento de mis datos personales conforme a la{" "}
              <button
                type="button"
                className="link"
                onClick={() => setVerPolitica((v) => !v)}
              >
                política de tratamiento de datos
              </button>
              .
            </span>
          </label>

          {verPolitica && (
            <div className="politica">
              <p>
                INVENTRA es responsable del tratamiento de los datos que registras
                aquí: el nombre de tu negocio, tu nombre y tu correo electrónico.
              </p>
              <p>
                Se usan únicamente para crear y mantener tu cuenta, darte acceso
                al sistema y enviarte los avisos propios del servicio, como la
                confirmación del correo o la recuperación de la contraseña. No se
                ceden a terceros ni se usan con fines publicitarios.
              </p>
              <p>
                Puedes conocer, actualizar, rectificar o suprimir tus datos, y
                revocar esta autorización, escribiendo a la dirección de contacto
                de INVENTRA. Al suprimirlos se cierra la cuenta, porque sin ellos
                el servicio no se puede prestar.
              </p>
            </div>
          )}

          <button
            className="btn btn-cta full"
            type="submit"
            disabled={!completo || enviando}
            style={{ marginTop: "6px" }}
          >
            {enviando ? "Creando la cuenta…" : "Crear cuenta"}
          </button>

          <div className="foot">
            ¿Ya tienes cuenta?{" "}
            <Link className="link" to="/acceso">
              Inicia sesión
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
}
