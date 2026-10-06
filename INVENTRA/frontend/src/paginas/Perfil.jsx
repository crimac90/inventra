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

  LA EXCEPCION DEL CORREO (D-29). Mientras la cuenta siga pendiente de confirmar,
  su titular SI puede corregir la direccion desde aqui. No es una concesion: quien
  se registra por autoservicio es el unico administrador de su licorera, de modo
  que si escribio mal su correo no hay nadie por encima que se lo arregle y la
  cuenta queda muerta —no puede confirmar, y sin confirmar no puede registrar—.
  En cuanto queda confirmada, la puerta se cierra y el servidor responde 409.
*/

import { useState } from "react";
import { useNavigate } from "react-router-dom";

import Disposicion from "../componentes/Disposicion";
import Campo from "../componentes/Campo";
import { ErrorApi, mensajeDeError } from "../api/cliente";
import {
  actualizarPerfil,
  cambiarContrasena,
  consultarPerfil,
  corregirCorreo,
} from "../api/seguridad";
import { ETIQUETA_DE_ROL } from "../sesion/roles";
import { useSesion } from "../sesion/ContextoSesion";

export default function Perfil() {
  const { usuario, setUsuario, salir } = useSesion();
  const navegar = useNavigate();
  const pendiente = !usuario.correo_verificado;

  return (
    <Disposicion titulo="Mi perfil">
      <h1>Mi perfil</h1>
      <div className="hs">Consulta y actualiza tus datos de acceso.</div>

      <DatosPersonales usuario={usuario} setUsuario={setUsuario} />
      <CambioDeContrasena salir={salir} navegar={navegar} />

      <div className="tarjeta">
        <h2>Datos de tu cuenta</h2>
        <div className="hs">
          {pendiente
            ? "El rol y la licorera los asigna quien administra tu licorera. El correo todavía puedes corregirlo tú, porque aún no está confirmado."
            : "Estos datos solo los puede modificar el administrador de tu licorera, porque el correo es tu identificador de acceso y el rol define lo que puedes hacer."}
        </div>

        <dl className="datos">
          <dt>Correo</dt>
          <dd>
            {usuario.correo}
            {/* Misma etiqueta y mismo patron que la marca «Tú» de la lista de
                usuarios, para no inventar una forma nueva de decir lo mismo. */}
            {pendiente && (
              <span className="tag" style={{ marginLeft: 8 }}>
                Sin confirmar
              </span>
            )}
          </dd>

          <dt>Rol</dt>
          <dd>{ETIQUETA_DE_ROL[usuario.rol] || usuario.rol}</dd>

          <dt>Licorera</dt>
          <dd>{usuario.licorera_nombre || "Sin licorera asignada"}</dd>
        </dl>

        {pendiente && <CorreccionDelCorreo usuario={usuario} setUsuario={setUsuario} />}
      </div>
    </Disposicion>
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
          texto: mensajeDeError(error),
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
        setAviso(mensajeDeError(error));
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

/* --- Correccion del correo mientras la cuenta siga pendiente (D-29) ------- */

function CorreccionDelCorreo({ usuario, setUsuario }) {
  const [correo, setCorreo] = useState(usuario.correo);
  const [error, setError] = useState("");
  const [aviso, setAviso] = useState("");
  const [guardando, setGuardando] = useState(false);

  // Mandar la misma direccion no arregla nada y el servidor lo rechaza: el
  // boton se queda quieto hasta que haya un cambio real.
  const hayCambio = correo.trim() !== "" && correo.trim() !== usuario.correo;

  async function enviar(evento) {
    evento.preventDefault();
    setError("");
    setAviso("");
    setGuardando(true);

    try {
      const respuesta = await corregirCorreo(correo.trim());
      /*
        El servidor responde con el aviso y no con el usuario, asi que se vuelve
        a pedir el perfil: la sesion tiene que quedarse con la direccion nueva, o
        la franja de arriba seguiria nombrando la vieja. Son dos peticiones para
        una operacion que se hace una vez en la vida de la cuenta.
      */
      setUsuario(await consultarPerfil());
      setAviso(respuesta?.detalle || "Correo actualizado. Te enviamos el enlace nuevo.");
    } catch (fallo) {
      if (fallo instanceof ErrorApi && fallo.codigo === 400) {
        setError(fallo.porCampo.correo || fallo.mensaje);
      } else {
        setError(mensajeDeError(fallo));
      }
    } finally {
      setGuardando(false);
    }
  }

  return (
    <form onSubmit={enviar} noValidate style={{ marginTop: "18px" }}>
      <h3>¿Escribiste mal tu correo?</h3>
      <div className="hs">
        Corrígelo y te enviamos el enlace de confirmación a la dirección nueva. Podrás hacerlo
        hasta que confirmes; después tendrá que cambiarlo quien administra tu licorera.
      </div>

      {aviso && (
        <div className="aviso ok" role="status">
          {aviso}
        </div>
      )}

      <Campo
        id="correo_corregido"
        etiqueta="Correo electrónico"
        tipo="email"
        autoComplete="email"
        valor={correo}
        onChange={(v) => {
          setCorreo(v);
          setError("");
        }}
        error={error}
      />

      <div className="acciones">
        <button className="btn btn-cta" type="submit" disabled={!hayCambio || guardando}>
          {guardando ? "Guardando…" : "Guardar y reenviar el enlace"}
        </button>
      </div>
    </form>
  );
}
