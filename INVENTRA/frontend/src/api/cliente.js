/*
  Cliente de la API.

  Todo lo que la interfaz le pide al backend pasa por aqui. Concentrarlo en un
  solo archivo tiene tres ventajas: la direccion base se escribe una vez, el
  token se agrega automaticamente sin que cada pantalla tenga que acordarse, y
  los errores llegan siempre con la misma forma.

  No se usa ninguna libreria: `fetch` viene incluido en el navegador.
*/

const BASE = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000/api";

// Claves con las que se guardan los tokens en el navegador.
const CLAVE_ACCESO = "inventra.acceso";
const CLAVE_REFRESCO = "inventra.refresco";

/*
  Donde se guardan los tokens.

  Si el usuario marco «Recordarme» se usa localStorage, que sobrevive al cierre
  del navegador. Si no la marco se usa sessionStorage, que se borra al cerrar la
  pestana. Esa casilla, entonces, no es decorativa: decide cuanto dura la sesion.

  Nota de seguridad que conviene tener clara: guardar el token en el navegador lo
  deja al alcance del codigo que corra en la pagina, asi que un ataque de tipo
  XSS podria leerlo. La alternativa —una cookie marcada httpOnly— exige que el
  backend la emita y complica el consumo desde otro dominio. Para el alcance de
  este proyecto se documenta el compromiso y se mitiga por el otro lado: tokens
  de acceso de vida corta y refresco rotatorio con lista negra.
*/
export function guardarTokens({ acceso, refresco }, recordar) {
  const destino = recordar ? localStorage : sessionStorage;
  limpiarTokens();
  destino.setItem(CLAVE_ACCESO, acceso);
  if (refresco) destino.setItem(CLAVE_REFRESCO, refresco);
}

export function limpiarTokens() {
  for (const a of [localStorage, sessionStorage]) {
    a.removeItem(CLAVE_ACCESO);
    a.removeItem(CLAVE_REFRESCO);
  }
}

export function tokenDeAcceso() {
  return localStorage.getItem(CLAVE_ACCESO) || sessionStorage.getItem(CLAVE_ACCESO);
}

function tokenDeRefresco() {
  return localStorage.getItem(CLAVE_REFRESCO) || sessionStorage.getItem(CLAVE_REFRESCO);
}

/*
  Error de la API.

  Lleva el codigo de respuesta y los datos que devolvio el servidor, de modo que
  la pantalla pueda decidir: un 400 se reparte por campos del formulario, un 401
  muestra el aviso de credenciales, un 409 el del limite del plan.
*/
export class ErrorApi extends Error {
  constructor(codigo, datos) {
    super(`La peticion respondio ${codigo}`);
    this.name = "ErrorApi";
    this.codigo = codigo;
    this.datos = datos || {};
  }

  /* Texto listo para mostrar cuando el error no pertenece a un campo. */
  get mensaje() {
    const d = this.datos;
    if (typeof d === "string") return d;
    if (d.detalle) return d.detalle;
    if (d.detail) return d.detail;
    if (Array.isArray(d.non_field_errors)) return d.non_field_errors.join(" ");
    if (this.codigo === 0) {
      return "No se pudo conectar con el servidor. Comprueba que este en ejecucion.";
    }
    return "Ocurrio un error inesperado. Intenta de nuevo.";
  }

  /* Errores por campo, para pintarlos debajo de cada input. */
  get porCampo() {
    const salida = {};
    if (this.datos && typeof this.datos === "object") {
      for (const [campo, valor] of Object.entries(this.datos)) {
        if (campo === "detalle" || campo === "detail") continue;
        salida[campo] = Array.isArray(valor) ? valor.join(" ") : String(valor);
      }
    }
    return salida;
  }
}

async function ejecutar(ruta, opciones, conToken) {
  const cabeceras = { "Content-Type": "application/json", ...(opciones.headers || {}) };

  if (conToken) {
    const token = tokenDeAcceso();
    if (token) cabeceras.Authorization = `Bearer ${token}`;
  }

  let respuesta;
  try {
    respuesta = await fetch(`${BASE}${ruta}`, { ...opciones, headers: cabeceras });
  } catch {
    // Ni siquiera hubo respuesta: el servidor esta apagado o no hay red.
    throw new ErrorApi(0, {});
  }

  // 204 significa «correcto, sin contenido»: no hay JSON que leer.
  const cuerpo = respuesta.status === 204 ? null : await respuesta.json().catch(() => null);

  if (!respuesta.ok) throw new ErrorApi(respuesta.status, cuerpo);
  return cuerpo;
}

/*
  Renueva el token de acceso con el de refresco.

  El backend rota el refresco en cada renovacion y deja el anterior en la lista
  negra, asi que hay que guardar el nuevo. Toda la API usa los mismos nombres,
  `acceso` y `refresco`, incluida esta direccion.
*/
async function renovar() {
  const refresco = tokenDeRefresco();
  if (!refresco) return false;

  try {
    const datos = await ejecutar(
      "/seguridad/renovar/",
      { method: "POST", body: JSON.stringify({ refresco }) },
      false,
    );
    const nuevoAcceso = datos.acceso;
    const nuevoRefresco = datos.refresco || refresco;
    if (!nuevoAcceso) return false;

    const destino = localStorage.getItem(CLAVE_REFRESCO) !== null ? localStorage : sessionStorage;
    destino.setItem(CLAVE_ACCESO, nuevoAcceso);
    destino.setItem(CLAVE_REFRESCO, nuevoRefresco);
    return true;
  } catch {
    return false;
  }
}

/*
  Peticion autenticada.

  Si el servidor responde 401 se intenta renovar una sola vez y se repite la
  peticion. Un segundo 401 significa que la sesion ya no sirve: se limpian los
  tokens y el error sube para que la aplicacion mande al usuario al acceso.
*/
async function conSesion(ruta, opciones) {
  try {
    return await ejecutar(ruta, opciones, true);
  } catch (error) {
    if (error instanceof ErrorApi && error.codigo === 401 && (await renovar())) {
      return await ejecutar(ruta, opciones, true);
    }
    if (error instanceof ErrorApi && error.codigo === 401) limpiarTokens();
    throw error;
  }
}

/* Atajos, para que las pantallas se lean como lo que hacen. */
export const api = {
  publico: {
    get: (ruta) => ejecutar(ruta, { method: "GET" }, false),
    post: (ruta, cuerpo) => ejecutar(ruta, { method: "POST", body: JSON.stringify(cuerpo) }, false),
  },
  get: (ruta) => conSesion(ruta, { method: "GET" }),
  post: (ruta, cuerpo) => conSesion(ruta, { method: "POST", body: JSON.stringify(cuerpo) }),
  patch: (ruta, cuerpo) => conSesion(ruta, { method: "PATCH", body: JSON.stringify(cuerpo) }),
  delete: (ruta) => conSesion(ruta, { method: "DELETE" }),
};
