/*
  Modo claro y modo oscuro (RNF-07).

  El requisito pide tres cosas: que la interfaz tenga los dos modos, que arranque
  con la preferencia del sistema operativo y que recuerde la eleccion del usuario
  en ese dispositivo.

  QUIEN DECIDE Y QUIEN PINTA
  Este archivo decide y escribe `data-tema` en el elemento <html>; el CSS solo
  mira ese atributo. La alternativa era dejar que el CSS resolviera tambien la
  preferencia del sistema con `prefers-color-scheme`, pero entonces la lista de
  colores tendria que estar dos veces en la hoja y el usuario que elige el modo
  contrario al del sistema obliga a pelear con la especificidad. Con un solo
  atributo, la lista de colores vive una vez y la decision tambien.

  QUE SE GUARDA
  Solo se guarda una eleccion explicita, «claro» u «oscuro». Mientras el usuario
  no elija, no hay nada guardado y manda el sistema operativo, incluso si cambia
  a mitad de sesion. Guardar «sistema» como si fuera un valor mas seria lo mismo
  con un dato de mas.

  EL ALMACENAMIENTO PUEDE FALLAR
  En una ventana privada o con las cookies bloqueadas, `localStorage` lanza al
  leer o al escribir. La interfaz no puede caerse por no poder recordar un color,
  asi que cada acceso va protegido y, si falla, se sigue con el modo del sistema.
*/

const CLAVE = "inventra.tema";
const CONSULTA = "(prefers-color-scheme: dark)";

/** Lo que el usuario eligio, o null si nunca eligio. */
export function leerEleccion() {
  try {
    const valor = window.localStorage.getItem(CLAVE);
    return valor === "claro" || valor === "oscuro" ? valor : null;
  } catch {
    return null;
  }
}

function guardarEleccion(tema) {
  try {
    window.localStorage.setItem(CLAVE, tema);
  } catch {
    /* Sin almacenamiento la eleccion dura lo que dure la pestana. */
  }
}

/** El modo que pide el sistema operativo. */
export function temaDelSistema() {
  return window.matchMedia && window.matchMedia(CONSULTA).matches ? "oscuro" : "claro";
}

/** El modo que se debe estar viendo ahora mismo. */
export function temaVigente() {
  return leerEleccion() || temaDelSistema();
}

/** Escribe el atributo que lee el CSS. */
export function pintar(tema) {
  document.documentElement.setAttribute("data-tema", tema);
}

/** Cambia al modo contrario y lo recuerda. Devuelve el modo que queda. */
export function alternar() {
  const nuevo = temaVigente() === "oscuro" ? "claro" : "oscuro";
  guardarEleccion(nuevo);
  pintar(nuevo);
  return nuevo;
}

/**
 * Avisa cuando cambia la preferencia del sistema, y solo mientras el usuario no
 * haya elegido: a partir de ahi manda su eleccion. Devuelve la funcion que
 * cancela la suscripcion.
 */
export function alCambiarElSistema(aviso) {
  if (!window.matchMedia) return () => {};
  const consulta = window.matchMedia(CONSULTA);
  const manejar = () => {
    if (!leerEleccion()) aviso(temaDelSistema());
  };
  consulta.addEventListener("change", manejar);
  return () => consulta.removeEventListener("change", manejar);
}
