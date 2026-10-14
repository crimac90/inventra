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

/* Las categorias se siembran al registrar la licorera y no se gestionan. */
export function consultarCategorias() {
  return api.get("/inventario/categorias/");
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

/* Referencias en o por debajo de su minimo, para el aviso del panel. */
export function consultarAlertas() {
  return api.get("/inventario/alertas/");
}

/* --- Kardex (RF-INV-09) -------------------------------------------------- */

export function consultarKardex(id) {
  return api.get(`/inventario/productos/${id}/kardex/`);
}
