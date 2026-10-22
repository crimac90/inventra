/*
  La venta a medio hacer sobrevive a salir de la pantalla.

  Un vendedor con diez referencias en el carro puede necesitar mirar el
  inventario, o pulsar sin querer otra opcion del menu; sin esto, lo que se
  pierde no es su trabajo sino el del cliente, que tendria que repetir su
  compra. Se guarda en el navegador, igual que la preferencia de modo oscuro,
  y se recupera al volver.

  Solo se guardan las lineas. El medio de pago y el efectivo recibido no,
  porque son del momento de cobrar y no de armar la venta.

  El precio guardado es el que se vio, no el que se cobra: si alguien lo
  cambia en el catalogo mientras tanto, la linea recuperada ensena el viejo
  hasta que se cobra, y el servidor pone el suyo, que es el unico que vale. Es
  un desajuste de segundos frente a perder la venta entera.

  Se guarda por cuenta de usuario, porque dos personas que se turnan la misma
  caja no pueden heredarse el carro la una a la otra.
*/

const PREFIJO = "inventra.venta.";

function clave(usuario) {
  return PREFIJO + (usuario && usuario.id ? usuario.id : "anonimo");
}

export function leerVenta(usuario) {
  try {
    const guardado = localStorage.getItem(clave(usuario));
    if (!guardado) return [];
    const lineas = JSON.parse(guardado);
    return Array.isArray(lineas) ? lineas : [];
  } catch (error) {
    // Un dato corrupto no puede impedir vender: se empieza en blanco.
    return [];
  }
}

export function guardarVenta(usuario, lineas) {
  try {
    if (!lineas.length) {
      localStorage.removeItem(clave(usuario));
      return;
    }
    localStorage.setItem(clave(usuario), JSON.stringify(lineas));
  } catch (error) {
    // Sin espacio o con el almacenamiento bloqueado se sigue vendiendo: lo
    // que se pierde es la red de seguridad, no la venta.
  }
}

export function olvidarVenta(usuario) {
  try {
    localStorage.removeItem(clave(usuario));
  } catch (error) {
    /* nada que hacer */
  }
}
