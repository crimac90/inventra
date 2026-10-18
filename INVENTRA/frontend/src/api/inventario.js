/*
  Operaciones del modulo de inventario.

  Una funcion por direccion de la API. Las pantallas llaman a estas funciones y
  no escriben rutas: si manana una direccion cambia, se corrige aqui y en un
  solo sitio.
*/

import { api } from "./cliente";

/*
  Construye la cadena de consulta a partir de los filtros que vengan con valor.

  Se usa `URLSearchParams` y no se pegan los valores a mano porque alguien va a
  buscar «Aguila» con tilde, o un nombre con espacios, y eso pegado en una
  direccion la rompe. Los filtros vacios no se mandan: una direccion con
  `?buscar=` dentro no dice la verdad sobre lo que se esta pidiendo.
*/
function consulta(filtros) {
  const partes = new URLSearchParams();
  for (const [clave, valor] of Object.entries(filtros || {})) {
    if (valor !== undefined && valor !== null && String(valor).trim() !== "") {
      partes.append(clave, String(valor).trim());
    }
  }
  const texto = partes.toString();
  return texto ? `?${texto}` : "";
}

/* --- Catalogo (RF-INV-01 a 04) ------------------------------------------ */

/*
  Se devuelve el objeto completo, con `count` y `results`, y no solo la lista:
  cuando una licorera tenga mas productos que una pagina hara falta saber
  cuantos hay en total para poder recorrerlas.
*/
export function listarProductos(filtros) {
  return api.get(`/inventario/productos/${consulta(filtros)}`);
}

/* Una sola referencia, para la pantalla de kardex, que llega por direccion. */
export function consultarProducto(id) {
  return api.get(`/inventario/productos/${id}/`);
}

export function crearProducto(datos) {
  return api.post("/inventario/productos/", datos);
}

export function actualizarProducto(id, datos) {
  return api.patch(`/inventario/productos/${id}/`, datos);
}

/* Baja logica: el producto no se borra, deja de ofrecerse en la venta. */
export function inactivarProducto(id) {
  return api.delete(`/inventario/productos/${id}/`);
}

/* Vuelve a poner en el catalogo una referencia descontinuada. */
export function reactivarProducto(id) {
  return api.post(`/inventario/productos/${id}/reactivar/`, {});
}

/*
  Las categorias se siembran al registrar la licorera. No se crean, no se
  borran y no se renombran; lo unico ajustable es su margen.
*/
export function consultarCategorias() {
  return api.get("/inventario/categorias/");
}

/* Los seis margenes viajan juntos porque se editan juntos (RF-INV-11). */
export function guardarMargenes(margenes) {
  return api.put("/inventario/categorias/margenes/", { margenes });
}

/* --- Existencias (RF-INV-05, 06 y 07) ----------------------------------- */

export function registrarEntrada(datos) {
  return api.post("/inventario/entradas/", datos);
}

export function listarEntradas() {
  return api.get("/inventario/entradas/");
}

export function ajustarExistencias(id, { cantidad, motivo }) {
  return api.post(`/inventario/productos/${id}/ajustar/`, { cantidad, motivo });
}

/*
  Lo que el panel ensena del inventario: cuantas referencias activas hay y
  cuales estan en o por debajo de su minimo. Los dos datos llegan juntos
  porque se pintan juntos.
*/
export function consultarResumen() {
  return api.get("/inventario/resumen/");
}

/* --- Kardex (RF-INV-09) -------------------------------------------------- */

/*
  El kardex llega paginado, como todas las listas. Se pide una pagina a la vez
  porque una referencia con dos anos de movimientos tiene miles de lineas, y
  traerlas todas para mostrar las primeras veinticinco no lo arregla: lo
  esconde.
*/
export function consultarKardex(id, pagina) {
  return api.get(`/inventario/productos/${id}/kardex/${consulta({ page: pagina })}`);
}
