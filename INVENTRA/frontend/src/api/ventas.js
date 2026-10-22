/*
  Las direcciones del modulo de ventas (VEN).

  El precio no viaja en la peticion: se mandan producto y cantidad, y a cuanto
  se vende lo dice el catalogo en el servidor. Si el precio se recibiera del
  navegador, quien tuviera la pantalla delante podria cobrar lo que quisiera.
*/

import { api } from "./cliente";

export function consultarMediosDePago() {
  return api.get("/ventas/medios-de-pago/");
}

/* Cobra la venta. `lineas` es [{ producto_id, cantidad }]. */
export function cobrar({ medioPagoId, montoRecibido, observacion, lineas }) {
  return api.post("/ventas/", {
    medio_pago_id: medioPagoId,
    monto_recibido: montoRecibido,
    observacion: observacion,
    lineas: lineas,
  });
}

/* --- Historial (RF-VEN-05) ------------------------------------------------ */

export function listarVentas(filtros = {}) {
  const parametros = new URLSearchParams();
  Object.entries(filtros).forEach(([clave, valor]) => {
    if (valor !== undefined && valor !== null && valor !== "") {
      parametros.append(clave, valor);
    }
  });
  const cola = parametros.toString();
  return api.get("/ventas/" + (cola ? `?${cola}` : ""));
}

export function consultarVenta(id) {
  return api.get(`/ventas/${id}/`);
}

export function anularVenta(id, motivo) {
  return api.post(`/ventas/${id}/anular/`, { motivo });
}

/* --- Cierre de caja (RF-VEN-06) ------------------------------------------- */

/* Lo que el sistema sabe de la jornada en curso, y su cierre si ya se hizo. */
export function consultarCierre() {
  return api.get("/ventas/cierre/");
}

export function cerrarJornada({ efectivoContado, observacion }) {
  return api.post("/ventas/cierre/", {
    efectivo_contado: efectivoContado,
    observacion: observacion,
  });
}

export function explicarDiferencia(id, observacion) {
  return api.patch(`/ventas/cierre/${id}/explicacion/`, { observacion });
}
