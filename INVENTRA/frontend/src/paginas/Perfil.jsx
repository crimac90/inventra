/*
  Perfil propio (RF-SEG-06).

  Dos tarjetas, porque son dos operaciones distintas contra dos direcciones
  distintas de la API: los datos personales se guardan con PATCH en `/perfil/` y
  la contrasena se cambia con POST en `/cambiar-contrasena/`. Separarlas evita el
  formulario gigante en el que el usuario no sabe que esta guardando.

  Lo que NO se puede cambiar desde aqui —correo, rol y estado de la cuenta— se
  muestra igualmente, pero como datos de consulta, con la explicacion de quien si
  puede cambiarlos. Ocultarlos sin mas dejaria al usuario preguntandose donde
  estan.
*/

import { useState } from "react";
import { useNavigate } from "react-router-dom";

import Cabecera from "../componentes/Cabecera";
import Campo from "../componentes/Campo";
import { ErrorApi } from "../api/cliente";
import { actualizarPerfil, cambiarContrasena } from "../api/seguridad";
import { useSesion } from "../sesion/ContextoSesion";

const ROLES = {
  administrador_licorera: "Administrador de licorera",
  vendedor: "Vendedor",
  administrador_inventra: "Administrador de INVENTRA",
};

export default function Perfil() {
  const { usuario, setUsuario, salir } = useSesion();
  const navegar = useNavigate();

  return (
    <div className="pagina">
      <Cabecera />

      <main className="contenido">
        <h1>Mi perfil</h1>
        <div className="hs">Consulta y actualiza tus datos de acceso.</div>

        <DatosPersonales usuario={usuario} setUsuario={setUsuario} />
        <CambioDeContrasena salir={salir} navegar={navegar} />

        <div className="tarjeta">
          <h2>Datos de tu cuenta</h2>
          <div className="hs">
            Estos datos solo los puede modificar el administrador de tu licorera, porque el
            correo es tu identificador de acceso y el rol define lo que puedes hacer.
          </div>

          <dl className="datos">
            <dt>Correo</dt>
            <dd>{usuario.correo}</dd>

            <dt>Rol</dt>
            <dd>{ROLES[usuario.rol] || usuario.rol}</dd>

            <dt>Licorera</dt>
            <dd>{usuario.licorera_nombre || "Sin licorera asignada"}</dd>
          </dl>
        </div>
      </main>
    </div>
  );
}

/* --- Tarjeta 1: nombre y telefono ---------------------------------------- */

function DatosPersonales({ usuario, setUsuario }) {
  const [nombre, setNombre] = useState(usuario.nombre_completo);
  const [telefono, setTelefono] = useState(usuario.telefono || "");
  const [errores, setErrores] = useState({});
  const [aviso, setAviso] = useState(null);
  const [guardando, setGuardando] = useState(false);

  // Sin cambios no hay nada que guardar: el boton se queda quieto.
  const hayCambios =
    nombre !== usuario.nombre_completo || telefono !== (usuario.telefono || "");

  async function enviar(evento) {
    evento.preventDefault();
    setAviso(null);
    setErrores({});
    setGuardando(true);

    try {
      const actualizado = await actualizarPerfil({
        nombre_completo: nombre.trim(),
        telefono: telefono.trim(),
      });
      // La API devuelve el usuario completo: se refresca la sesion para que la
      // cabecera y el panel muestren el nombre nuevo sin recargar la pagina.
      setUsuario(actualizado);
      setAviso({ tipo: "ok", texto: "Datos actualizados." });
    } catch (error) {
      if (error instanceof ErrorApi && error.codigo === 400) {
        setErrores(error.porCampo);
        setAviso({ tipo: "err", texto: "Revisa los datos marcados." });
      } else {
        setAviso({
          tipo: "err",
          texto: error instanceof ErrorApi ? error.mensaje : "Ocurrió un error inesperado.",
        });
      }
    } finally {
      setGuardando(false);
    }
  }

  return (
    <form className="tarjeta" onSubmit={enviar} noValidate>
      <h2>Datos personales</h2>
      <div className="hs">Así te ve el resto de tu equipo dentro del sistema.</div>

      {aviso && (
        <div className={`aviso ${aviso.tipo}`} role={aviso.tipo === "err" ? "alert" : "status"}>
          {aviso.texto}
        </div>
      )}

      <Campo
        id="nombre_completo"
        etiqueta="Nombre y apellido"
        autoComplete="name"
        valor={nombre}
        onChange={setNombre}
        error={errores.nombre_completo}
      />

      <Campo
        id="telefono"
        etiqueta="Teléfono"
        tipo="tel"
        marcador="3001234567"
        autoComplete="tel"
        requerido={false}
        valor={telefono}
        onChange={setTelefono}
        error={errores.telefono}
      />

      <div className="acciones">
        <button className="btn btn-cta" type="submit" disabled={!hayCambios || guardando}>
          {guardando ? "Guardando…" : "Guardar cambios"}
        </button>
      </div>
    </form>
  );
}

/* --- Tarjeta 2: cambio de contrasena -------------------------------------- */

function CambioDeContrasena({ salir, navegar }) {
  const [actual, setActual] = useState("");
  const [nueva, setNueva] = useState("");
  const [confirmacion, setConfirmacion] = useState("");
  const [errores, setErrores] = useState({});
  const [aviso, setAviso] = useState("");
  const [guardando, setGuardando] = useState(false);

  const completo = actual !== "" && nueva !== "" && confirmacion !== "";

  async function enviar(evento) {
    evento.preventDefault();
    setAviso("");
    setErrores({});

    if (nueva !== confirmacion) {
      setErrores({ confirmacion: "Las dos contraseñas no coinciden." });
      return;
    }

    setGuardando(true);
    try {
      await cambiarContrasena({ contrasena_actual: actual, contrasena_nueva: nueva });

      /*
        Cambiada la contraseña, se cierra la sesión y se vuelve al acceso. El
        token seguiría siendo válido, así que esto no es una obligación técnica:
        es lo que el usuario espera, y obliga a comprobar de inmediato que la
        contraseña nueva funciona. También invalida la sesión en este navegador,
        que es lo deseable si el cambio se hizo porque alguien más la conocía.
      */
      await salir();
      navegar("/acceso", {
        replace: true,
        state: { mensaje: "Tu contraseña se actualizó. Ingresa con la nueva." },
      });
    } catch (error) {
      if (error instanceof ErrorApi && error.codigo === 400) {
        const porCampo = error.porCampo;
        setErrores({
          contrasena_actual: porCampo.contrasena_actual,
          nueva: porCampo.contrasena_nueva,
        });
        if (!porCampo.contrasena_actual && !porCampo.contrasena_nueva) setAviso(error.mensaje);
      } else {
        setAviso(error instanceof ErrorApi ? error.mensaje : "Ocurrió un error inesperado.");
      }
    } finally {
      setGuardando(false);
    }
  }

  return (
    <form className="tarjeta" onSubmit={enviar} noValidate>
      <h2>Contraseña</h2>
      <div className="hs">
        Se pide la contraseña actual aunque tengas la sesión abierta: así nadie que encuentre
        tu equipo desatendido puede quedarse con la cuenta.
      </div>

      {aviso && (
        <div className="aviso err" role="alert">
          {aviso}
        </div>
      )}

      <Campo
        id="contrasena_actual"
        etiqueta="Contraseña actual"
        tipo="password"
        marcador="••••••••"
        autoComplete="current-password"
        valor={actual}
        onChange={(v) => {
          setActual(v);
          setErrores({});
        }}
        error={errores.contrasena_actual}
      />

      <Campo
        id="contrasena_nueva"
        etiqueta="Contraseña nueva"
        tipo="password"
        marcador="••••••••"
        autoComplete="new-password"
        ayuda="Mínimo 8 caracteres, con letras y números."
        valor={nueva}
        onChange={(v) => {
          setNueva(v);
          setErrores({});
        }}
        error={errores.nueva}
      />

      <Campo
        id="confirmacion_nueva"
        etiqueta="Repite la contraseña nueva"
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

      <div className="acciones">
        <button className="btn btn-cta" type="submit" disabled={!completo || guardando}>
          {guardando ? "Cambiando…" : "Cambiar contraseña"}
        </button>
        <span style={{ color: "var(--muted)", fontSize: "13px" }}>
          Se cerrará la sesión al terminar.
        </span>
      </div>
    </form>
  );
}
