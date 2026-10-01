/*
  Llamadas del modulo de suscripciones.

  El estado de la suscripcion lo necesitan varias pantallas —el panel, el aviso
  de prueba y, mas adelante, «Mi suscripcion»—, asi que la llamada vive aqui y
  no dentro de una de ellas.
*/

import { api } from "./cliente";

/*
  Devuelve el plan, el estado, los dias que quedan y si la licorera puede
  registrar operaciones. La direccion no lleva identificador: la licorera se
  toma de la sesion.
*/
export function consultarMiSuscripcion() {
  return api.get("/suscripciones/mi-suscripcion/");
}

export function consultarPlanes() {
  return api.get("/suscripciones/planes/");
}

/*
  Devuelve, para cada modulo del producto, si la licorera lo puede usar hoy,
  si todavia no esta construido o si no entra en su plan. La lista la decide el
  servidor: el plan contratado no es algo que el navegador pueda saber.
*/
export function consultarMisModulos() {
  return api.get("/suscripciones/mis-modulos/");
}

