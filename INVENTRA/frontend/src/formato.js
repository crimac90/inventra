/*
  Como se escriben los numeros y las fechas en la interfaz.

  POR QUE EXISTE ESTE ARCHIVO
  El formateador de pesos y la funcion de fecha estaban escritos DOS VECES,
  identicos, en «Mi suscripcion» y en «Plataforma»: cada pantalla resolvio por
  su cuenta algo que no es suyo. Es la misma forma de error que ya aparecio con
  el plural de los mensajes y con las variantes de boton —una regla resuelta
  dentro del primer caso que la necesita— y aqui el coste futuro es el que
  manda: inventario y ventas muestran importes y fechas en casi todas sus
  pantallas, de modo que sin un sitio comun no habria dos copias sino seis.

  El dia que cambie el formato —que los importes lleven centavos, que las
  fechas se escriban con el mes en letras— se cambia aqui y en ningun otro
  sitio.
*/

const PESOS = new Intl.NumberFormat("es-CO", {
  style: "currency",
  currency: "COP",
  maximumFractionDigits: 0,
});

/* Un importe en pesos colombianos, sin centavos. */
export function moneda(valor) {
  if (valor == null) return "—";
  return PESOS.format(valor);
}

/*
  Una fecha del servidor (AAAA-MM-DD) escrita como se lee en Colombia.

  No se usa `new Date(texto)` a proposito: con una fecha sin hora el navegador
  la interpreta en UTC y al pasarla al huso local puede retroceder un dia, de
  modo que un vencimiento del 1 se mostraria como 31. Partir el texto no tiene
  ese problema porque no convierte nada.
*/
export function fecha(texto) {
  if (!texto) return "—";
  const [anio, mes, dia] = texto.split("-");
  return `${dia}/${mes}/${anio}`;
}
