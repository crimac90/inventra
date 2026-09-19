/*
  Gestion de los usuarios de la licorera (RF-SEG-01, 05 y 07).

  Es la primera pantalla del proyecto que hace las cuatro operaciones sobre un
  recurso —listar, crear, editar y dar de baja—, asi que el patron que se use
  aqui es el que van a seguir productos, ventas y sedes. De ahi que valga la pena
  entenderla bien.

  Tres ideas la gobiernan:

  1. La lista vive en el estado de la pantalla y se refresca desde el servidor
     despues de cada cambio. No se «parchea» a mano la fila modificada: se vuelve
     a pedir. Es una peticion mas, pero garantiza que lo que se ve es lo que hay.
  2. El formulario es el mismo para crear y para editar; lo que cambia es si
     lleva contrasena y a que direccion se envia.
  3. Cada codigo de respuesta se traduce a algo que el usuario entienda: el 400
     se reparte por campos, el 409 explica el limite del plan y ofrece la salida.
*/

import { useCallback, useEffect, useState } from "react";

import Campo from "../componentes/Campo";
import CampoSeleccion from "../componentes/CampoSeleccion";
import Disposicion from "../componentes/Disposicion";
import Modal from "../componentes/Modal";
import { ErrorApi } from "../api/cliente";
import {
  actualizarUsuario,
  consultarRoles,
  crearUsuario,
  inactivarUsuario,
  listarUsuarios,
  reactivarUsuario,
} from "../api/seguridad";
import { useSesion } from "../sesion/ContextoSesion";

const NOMBRES_DE_ROL = {
  administrador_licorera: "Administrador",
  vendedor: "Vendedor",
  administrador_inventra: "Administrador de INVENTRA",
};

const FORMULARIO_VACIO = {
  nombre_completo: "",
  correo: "",
  telefono: "",
  rol: "",
  password: "",
};

export default function Usuarios() {
  const { usuario: yo } = useSesion();

  const [usuarios, setUsuarios] = useState([]);
  const [roles, setRoles] = useState([]);
  const [cargando, setCargando] = useState(true);
  const [aviso, setAviso] = useState(null);

  // Cuando vale null no hay formulario abierto. Con un objeto vacío se está
  // creando; con un usuario dentro, editándolo.
  const [editando, setEditando] = useState(null);
  const [porInactivar, setPorInactivar] = useState(null);
  const [ocupado, setOcupado] = useState(false);

  /*
    `useCallback` conserva la misma función entre redibujados. Hace falta porque
    el efecto de abajo la tiene como dependencia: si fuera una función nueva en
    cada redibujado, el efecto se dispararía sin parar.
  */
  const refrescar = useCallback(async () => {
    const datos = await listarUsuarios();
    setUsuarios(datos.results || []);
  }, []);

  useEffect(() => {
    let vigente = true;

    Promise.all([listarUsuarios(), consultarRoles()])
      .then(([listado, catalogo]) => {
        if (!vigente) return;
        setUsuarios(listado.results || []);
        // El administrador de INVENTRA no es asignable dentro de una licorera:
        // el backend ya lo excluye, aquí solo se muestra lo que llega.
        setRoles(catalogo);
      })
      .catch((error) => {
        if (vigente) setAviso({ tipo: "err", texto: textoDeError(error) });
      })
      .finally(() => {
        if (vigente) setCargando(false);
      });

    return () => {
      vigente = false;
    };
  }, []);

  async function guardar(datos) {
    setOcupado(true);
    try {
      if (editando.id) {
        // Al editar no viaja la contraseña: tiene su propio procedimiento.
        const { password, ...resto } = datos;
        await actualizarUsuario(editando.id, resto);
        setAviso({ tipo: "ok", texto: "Usuario actualizado." });
      } else {
        await crearUsuario(datos);
        setAviso({ tipo: "ok", texto: "Usuario creado." });
      }
      await refrescar();
      setEditando(null);
      return {};
    } catch (error) {
      if (error instanceof ErrorApi && error.codigo === 400) {
        setAviso({ tipo: "err", texto: "Revisa los datos marcados." });
        return error.porCampo;
      }
      setAviso({ tipo: "err", texto: textoDeError(error) });
      return {};
    } finally {
      setOcupado(false);
    }
  }

  async function confirmarInactivacion() {
    setOcupado(true);
    try {
      await inactivarUsuario(porInactivar.id);
      await refrescar();
      setAviso({ tipo: "ok", texto: `${porInactivar.nombre_completo} quedó inactivo.` });
      setPorInactivar(null);
    } catch (error) {
      setAviso({ tipo: "err", texto: textoDeError(error) });
      setPorInactivar(null);
    } finally {
      setOcupado(false);
    }
  }

  async function reactivar(fila) {
    setOcupado(true);
    try {
      await reactivarUsuario(fila.id);
      await refrescar();
      setAviso({ tipo: "ok", texto: `${fila.nombre_completo} volvió a estar activo.` });
    } catch (error) {
      setAviso({ tipo: "err", texto: textoDeError(error) });
    } finally {
      setOcupado(false);
    }
  }

  const activos = usuarios.filter((u) => u.activo).length;

  return (
    <Disposicion titulo="Usuarios">
      <div className="barra-herramientas">
        <div>
          <h1>Usuarios de la licorera</h1>
          <div className="hs" style={{ margin: "6px 0 0" }}>
            {activos} {activos === 1 ? "cuenta activa" : "cuentas activas"} de {usuarios.length}{" "}
            registradas.
          </div>
        </div>

        {!editando && (
          <button className="btn btn-cta" type="button" onClick={() => setEditando({})}>
            Agregar usuario
          </button>
        )}
      </div>

      {aviso && (
        <div
          className={`aviso ${aviso.tipo}`}
          role={aviso.tipo === "err" ? "alert" : "status"}
        >
          {aviso.texto}
        </div>
      )}

      {editando && (
        <Formulario
          inicial={editando}
          roles={roles}
          ocupado={ocupado}
          onGuardar={guardar}
          onCancelar={() => setEditando(null)}
        />
      )}

      <div className="tabla-caja">
        {cargando ? (
          <div className="vacio">Cargando…</div>
        ) : usuarios.length === 0 ? (
          <div className="vacio">Todavía no hay usuarios registrados.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Correo</th>
                <th>Rol</th>
                <th>Estado</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {usuarios.map((fila) => (
                <tr key={fila.id}>
                  <td>
                    {fila.nombre_completo}
                    {fila.id === yo.id && <span className="tag" style={{ marginLeft: 8 }}>Tú</span>}
                  </td>
                  <td>{fila.correo}</td>
                  <td>{NOMBRES_DE_ROL[fila.rol] || fila.rol}</td>
                  <td>
                    <span className={`estado ${fila.activo ? "activo" : "inactivo"}`}>
                      {fila.activo ? "Activo" : "Inactivo"}
                    </span>
                  </td>
                  <td className="acciones-fila">
                    <button
                      className="btn btn-out btn-pequeno"
                      type="button"
                      onClick={() => setEditando(fila)}
                      disabled={ocupado}
                    >
                      Editar
                    </button>

                    {fila.activo ? (
                      /*
                        Nadie puede inactivarse a sí mismo: el backend lo impide
                        con un 400 y aquí el botón ni siquiera aparece, para no
                        ofrecer una acción que se va a rechazar.
                      */
                      fila.id !== yo.id && (
                        <button
                          className="btn btn-out btn-pequeno"
                          type="button"
                          onClick={() => setPorInactivar(fila)}
                          disabled={ocupado}
                        >
                          Inactivar
                        </button>
                      )
                    ) : (
                      <button
                        className="btn btn-out btn-pequeno"
                        type="button"
                        onClick={() => reactivar(fila)}
                        disabled={ocupado}
                      >
                        Reactivar
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {porInactivar && (
        <Modal
          titulo="Inactivar usuario"
          mensaje={`${porInactivar.nombre_completo} dejará de poder entrar al sistema. Sus ventas y movimientos se conservan, y la cuenta se puede reactivar después.`}
          textoConfirmar="Inactivar"
          ocupado={ocupado}
          onConfirmar={confirmarInactivacion}
          onCancelar={() => setPorInactivar(null)}
        />
      )}
    </Disposicion>
  );
}

/* --- Formulario, compartido por el alta y la edicion ---------------------- */

function Formulario({ inicial, roles, ocupado, onGuardar, onCancelar }) {
  const esNuevo = !inicial.id;

  const [datos, setDatos] = useState({
    ...FORMULARIO_VACIO,
    nombre_completo: inicial.nombre_completo || "",
    correo: inicial.correo || "",
    telefono: inicial.telefono || "",
    rol: String(inicial.rol_id || roles.find((r) => r.nombre === inicial.rol)?.id || roles[0]?.id || ""),
  });
  const [errores, setErrores] = useState({});

  function cambiar(campo) {
    return (valor) => {
      setDatos((previo) => ({ ...previo, [campo]: valor }));
      setErrores((previo) => ({ ...previo, [campo]: undefined }));
    };
  }

  const completo =
    datos.nombre_completo.trim() !== "" &&
    datos.correo.trim() !== "" &&
    datos.rol !== "" &&
    (!esNuevo || datos.password !== "");

  async function enviar(evento) {
    evento.preventDefault();
    const devueltos = await onGuardar({
      nombre_completo: datos.nombre_completo.trim(),
      correo: datos.correo.trim(),
      telefono: datos.telefono.trim(),
      rol: Number(datos.rol),
      password: datos.password,
    });
    setErrores(devueltos || {});
  }

  return (
    <form className="tarjeta" onSubmit={enviar} noValidate>
      <h2>{esNuevo ? "Agregar usuario" : `Editar a ${inicial.nombre_completo}`}</h2>
      <div className="hs">
        {esNuevo
          ? "La cuenta queda asociada a tu licorera automáticamente."
          : "La contraseña no se edita aquí: cada usuario la cambia desde su perfil, o la restablece por correo."}
      </div>

      <Campo
        id="nombre_completo"
        etiqueta="Nombre y apellido"
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
        id="telefono"
        etiqueta="Teléfono"
        tipo="tel"
        marcador="3001234567"
        requerido={false}
        valor={datos.telefono}
        onChange={cambiar("telefono")}
        error={errores.telefono}
      />

      <CampoSeleccion
        id="rol"
        etiqueta="Rol"
        valor={datos.rol}
        onChange={cambiar("rol")}
        error={errores.rol}
        opciones={roles.map((r) => ({
          valor: String(r.id),
          texto: NOMBRES_DE_ROL[r.nombre] || r.nombre,
        }))}
      />

      {esNuevo && (
        <Campo
          id="password"
          etiqueta="Contraseña inicial"
          tipo="password"
          marcador="••••••••"
          autoComplete="new-password"
          ayuda="Mínimo 8 caracteres, con letras y números. El usuario podrá cambiarla desde su perfil."
          valor={datos.password}
          onChange={cambiar("password")}
          error={errores.password}
        />
      )}

      <div className="acciones">
        <button className="btn btn-cta" type="submit" disabled={!completo || ocupado}>
          {ocupado ? "Guardando…" : esNuevo ? "Crear usuario" : "Guardar cambios"}
        </button>
        <button className="btn btn-out" type="button" onClick={onCancelar} disabled={ocupado}>
          Cancelar
        </button>
      </div>
    </form>
  );
}

/* --- Traduccion de los errores de la API --------------------------------- */

function textoDeError(error) {
  if (!(error instanceof ErrorApi)) return "Ocurrió un error inesperado.";

  // 409: el plan contratado no admite más usuarios. El backend manda el texto
  // con el nombre del plan y su tope, así que se muestra tal cual.
  if (error.codigo === 409) return error.mensaje;

  if (error.codigo === 403) {
    return "Esta acción solo la puede realizar el administrador de la licorera.";
  }

  if (error.codigo === 404) {
    return "Ese usuario ya no existe.";
  }

  return error.mensaje;
}
