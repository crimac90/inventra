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

/*
  Cambia el plan de la licorera de la sesion. Solo sirve para bajar: subir
  implica cobrar y lo ejecuta el Administrador INVENTRA desde su panel (D-23).
  El servidor responde 409 con el motivo cuando el cambio no procede.
*/
export function cambiarDePlan(plan) {
  return api.post("/suscripciones/cambiar-plan/", { plan });
}

/*
  Que pasaria con cada plan, sin hacer nada. Lo usa la pantalla para decir antes
  de pulsar si el cambio procede y, si no, por que. El veredicto sale de la
  misma comprobacion que ejecuta el cambio real, asi que no pueden discrepar.
*/
export function consultarCambiosDePlan() {
  return api.get("/suscripciones/cambiar-plan/");
}

