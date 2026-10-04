/*
  Llamadas del panel de la plataforma (RF-SUS-05 y RF-SUS-01).

  Van en su propio archivo y no en `suscripciones.js` por la misma razon que las
  vistas estan separadas en el backend: son otra audiencia. Lo de `suscripciones`
  es lo que un negocio consulta sobre si mismo; esto es lo que el operador de
  INVENTRA hace sobre todos.
*/

import { api } from "./cliente";

/* Las licoreras con su plan y su estado, mas las cifras globales. */
export function consultarPlataforma() {
  return api.get("/suscripciones/panel/");
}

/* Alta directa: crea la licorera, su suscripcion y su administrador. */
export function darDeAltaLicorera(datos) {
  return api.post("/suscripciones/panel/licoreras/", datos);
}

/*
  Abre un periodo nuevo: renovar y subir de plan son la misma operacion, y la
  unica diferencia es si el plan cambia (D-26).
*/
export function abrirPeriodo(licorera, plan, fecha_fin) {
  return api.post(`/suscripciones/panel/licoreras/${licorera}/suscripcion/`, { plan, fecha_fin });
}

/* Corrige la fecha de la suscripcion vigente, sin abrir una fila nueva. */
export function corregirVencimiento(licorera, fecha_fin) {
  return api.patch(`/suscripciones/panel/licoreras/${licorera}/suscripcion/`, { fecha_fin });
}
