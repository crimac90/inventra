/*
  Cuando un precio de venta no cubre lo que costo la mercancia.

  La pregunta es la misma en tres sitios —el formulario del producto, la lista
  del catalogo y el punto de venta— y la respuesta tiene que ser la misma en
  los tres. Repartida, cada pantalla acabaria eligiendo su propia base de
  comparacion y el sistema diria que una referencia pierde dinero en una
  pantalla y gana en otra.

  LA BASE ES LO QUE COSTO LO QUE HAY, no la ultima compra. Un lote de oferta
  de diez unidades no representa unas existencias de ciento treinta, y
  compararse contra el deja pasar perdidas reales. Sin existencias no hay
  promedio que calcular y lo unico que se sabe es la ultima compra, que es lo
  que se usa entonces.

  NO BLOQUEA NADA. Vender por debajo del costo es una decision del negocio
  —una liquidacion, una referencia que no rota, un favor a un cliente— y el
  sistema no esta para prohibirla, sino para que nadie la tome sin saberlo.
*/

function numero(valor) {
  return valor == null || valor === "" ? null : Number(valor);
}

/*
  El costo con el que se compara una referencia, o `null` si nunca se ha
  comprado. Recibe el producto tal como lo publica el servidor.
*/
export function costoDeReferencia(producto) {
  if (!producto) return null;
  const promedio = numero(producto.costo_promedio);
  if (promedio !== null && promedio > 0) return promedio;
  const ultimo = numero(producto.costo_ultima_compra);
  return ultimo !== null && ultimo > 0 ? ultimo : null;
}

/*
  Si el precio de venta de una referencia queda por debajo de lo que costo.
  Con un precio sin poner, o sin ninguna compra detras, no hay nada que
  comparar y la respuesta es que no.
*/
export function pierdeDinero(producto, precio) {
  const costo = costoDeReferencia(producto);
  const venta = numero(precio === undefined ? producto && producto.precio_venta : precio);
  if (costo === null || venta === null || venta <= 0) return false;
  return venta < costo;
}

/*
  La centena a la que se redondea una propuesta. Un precio de 41.637 no existe
  en un mostrador donde no hay monedas para la diferencia.
*/
const CENTENA = 100;

/*
  El precio que se PROPONE para un costo y un margen (RF-INV-11).

  Repite el calculo que el servidor hace al publicar `precio_sugerido`, y lo
  repite porque hay un momento en que el servidor no puede hacerlo: en la
  entrada de mercancia el costo se esta escribiendo y todavia no ha llegado a
  ninguna parte. Preguntarlo en cada tecla seria una consulta por pulsacion
  para un numero que es una multiplicacion.

  Se redondea HACIA ARRIBA, como alla: redondear hacia abajo entrega un precio
  por debajo del margen que se acaba de decidir.
*/
export function sugerirPrecio(costo, margen) {
  const base = numero(costo);
  const porcentaje = numero(margen);
  if (base === null || base <= 0 || porcentaje === null) return null;
  return Math.ceil((base * (1 + porcentaje / 100)) / CENTENA) * CENTENA;
}

/*
  Lo que costara en promedio cada unidad DESPUES de recibir un lote nuevo.

  Es el numero sobre el que hay que decidir el precio al recibir una compra, y
  no el promedio de hoy: en cuanto el lote entra, el costo de las existencias
  es otro. Sin existencias previas el promedio nuevo es el costo que llega.
*/
export function costoPromedioCon(producto, cantidad, costo) {
  const entran = numero(cantidad);
  const nuevo = numero(costo);
  if (entran === null || nuevo === null || entran <= 0 || nuevo < 0) return null;

  const unidades = numero(producto && producto.existencias) || 0;
  const promedio = numero(producto && producto.costo_promedio);
  if (unidades <= 0 || promedio === null) return nuevo;
  return (unidades * promedio + entran * nuevo) / (unidades + entran);
}

/*
  El margen que de verdad deja un precio sobre un costo, en porcentaje.

  Hace falta porque un precio que cubre el costo no dice nada por si solo: lo
  que el negocio decidio fue un porcentaje, y es el porcentaje el que se queda
  por el camino cuando la mercancia sube y el precio no.
*/
export function margenDe(costo, precio) {
  const base = numero(costo);
  const venta = numero(precio);
  if (base === null || base <= 0 || venta === null || venta <= 0) return null;
  return ((venta - base) / base) * 100;
}

/*
  Si una referencia ya no deja el margen que su categoria pide.

  No es lo mismo que perder dinero: el precio cubre el costo, pero la
  mercancia subio y el porcentaje que el negocio decidio se quedo por el
  camino. Se compara contra `precio_sugerido`, que el servidor calcula sobre el
  costo promedio de las existencias con el margen de la categoria; aqui no se
  recalcula nada, para que el catalogo y el formulario no puedan discrepar.

  Si ademas pierde dinero, esta funcion dice que no: lo mas grave manda, y dos
  etiquetas sobre la misma fila se leen como dos problemas distintos.
*/
export function sinMargen(producto) {
  if (!producto || pierdeDinero(producto)) return false;
  const sugerido = numero(producto.precio_sugerido);
  const precio = numero(producto.precio_venta);
  if (sugerido === null || precio === null || precio <= 0) return false;
  return precio < sugerido;
}
