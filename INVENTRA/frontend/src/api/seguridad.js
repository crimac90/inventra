/*
  Operaciones del modulo de seguridad.

  Una funcion por direccion de la API. Las pantallas llaman a estas funciones y
  no escriben rutas: si manana una direccion cambia, se corrige aqui y en un solo
  sitio.
*/

import { api, guardarTokens, limpiarTokens } from "./cliente";

export async function ingresar({ correo, password }, recordar) {
  const datos = await api.publico.post("/seguridad/ingresar/", { correo, password });
  guardarTokens(datos, recordar);
  return datos.usuario;
}

export async function registrarLicorera(formulario) {
  const datos = await api.publico.post("/suscripciones/registrar/", formulario);
  // El backend devuelve los tokens al registrar, para entrar directo al panel.
  guardarTokens(datos, false);
  return datos.usuario;
}

export function consultarPerfil() {
  return api.get("/seguridad/perfil/");
}

/* Actualización parcial: solo viajan los campos que el usuario puede cambiarse. */
export function actualizarPerfil(datos) {
  return api.patch("/seguridad/perfil/", datos);
}

export function cambiarContrasena({ contrasena_actual, contrasena_nueva }) {
  return api.post("/seguridad/cambiar-contrasena/", { contrasena_actual, contrasena_nueva });
}

export function consultarPlanes() {
  return api.publico.get("/suscripciones/planes/");
}

export function solicitarRecuperacion(correo) {
  return api.publico.post("/seguridad/recuperar/", { correo });
}

export function restablecerContrasena({ uid, token, password }) {
  return api.publico.post("/seguridad/restablecer/", { uid, token, password });
}

export async function salir() {
  try {
    const refresco =
      localStorage.getItem("inventra.refresco") || sessionStorage.getItem("inventra.refresco");
    if (refresco) await api.post("/seguridad/salir/", { refresco });
  } finally {
    // Aunque el servidor falle, la sesion se cierra en el navegador.
    limpiarTokens();
  }
}

/* ---------------------------------------------------------------------------
   Gestión de usuarios (RF-SEG-01, 05 y 07)
   Todas exigen sesión y rol de administrador; el backend responde 403 si no.
--------------------------------------------------------------------------- */

/*
  La API entrega los listados por páginas de veinticinco. Se devuelve el objeto
  completo, con `count` y `results`, para no perder ese dato: cuando una licorera
  tenga más usuarios que una página habrá que recorrerlas, y conviene que la
  pantalla sepa desde ya cuántos hay en total.
*/
export function listarUsuarios() {
  return api.get("/seguridad/usuarios/");
}

export function consultarRoles() {
  return api.get("/seguridad/roles/");
}

export function crearUsuario(datos) {
  return api.post("/seguridad/usuarios/", datos);
}

export function actualizarUsuario(id, datos) {
  return api.patch(`/seguridad/usuarios/${id}/`, datos);
}

/* Baja lógica: el usuario no se borra, se marca como inactivo. */
export function inactivarUsuario(id) {
  return api.delete(`/seguridad/usuarios/${id}/`);
}

export function reactivarUsuario(id) {
  return api.post(`/seguridad/usuarios/${id}/reactivar/`, {});
}

