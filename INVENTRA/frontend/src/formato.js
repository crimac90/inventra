/*
  Como se escriben los numeros y las fechas en la interfaz.

  Los importes y las fechas aparecen en casi todas las pantallas de inventario,
  ventas y suscripciones. Definirlos aqui deja un solo sitio donde cambiarlos
  el dia que el formato cambie: que los importes lleven centavos, que las
  fechas se escriban con el mes en letras.
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
  Un porcentaje, sin los ceros que no dicen nada.

  Los margenes se guardan con dos decimales porque la columna los admite, y un
  margen del treinta por ciento llega como «30.00». Escrito asi en una frase
  —«margen de Ron: 30.00%»— parece una cifra calculada con una precision que
  nadie pidio. Se escriben los decimales que de verdad tenga: 30 % o 32,5 %.

  El espacio antes del signo es el que manda la ortografia, y es duro para que
  el numero y el simbolo no se separen al final de una linea.
*/
const PORCENTAJE = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 2 });

export function porcentaje(valor) {
  if (valor == null || valor === "") return "—";
  const numero = Number(valor);
  if (Number.isNaN(numero)) return String(valor);
  return `${PORCENTAJE.format(numero)}\u00A0%`;
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

/*
  Una fecha con hora del servidor, escrita como se lee en Colombia.

  Aqui si se usa `new Date`, al reves que en `fecha`. La diferencia no es de
  gusto: el servidor manda estos momentos con su huso dentro, de modo que
  convertirlos al del navegador es lo correcto y no un error. Lo que no se
  puede convertir es una fecha sin hora, que es el caso de arriba.

  Lleva hora porque en un mismo dia entran varios movimientos de la misma
  referencia, y sin la hora el kardex no deja ver en que orden ocurrieron.
*/
export function fechaHora(texto) {
  if (!texto) return "—";
  const momento = new Date(texto);
  if (Number.isNaN(momento.getTime())) return texto;
  return momento.toLocaleString("es-CO", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
