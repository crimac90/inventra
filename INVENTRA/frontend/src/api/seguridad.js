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
