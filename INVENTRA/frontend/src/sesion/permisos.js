/*
  Lo que la interfaz sabe sobre quien puede registrar informacion (D-29).

  Gemelo de `suscripciones/permissions.py`. LA REGLA DE VERDAD VIVE EN EL
  SERVIDOR: esta funcion no protege nada y no puede, porque cualquiera abre las
  herramientas del navegador. Existe por una sola razon, la misma del bloque 7a:
  no ofrecer un boton que se va a rechazar, y decir el motivo antes de que la
  persona rellene un formulario para nada.

  LOS DOS MOTIVOS Y SU ORDEN tienen que coincidir con los del permiso. Si el
  servidor rechaza por el correo y la pantalla anuncia la suscripcion, la persona
  se va a arreglar lo que no era. Por eso el correo se mira primero aqui tambien.

  La accion la pone cada pantalla —«crear ni modificar cuentas», «registrar
  ventas»— porque es lo unico que cambia de una a otra; el resto de la frase y la
  eleccion del motivo se deciden en este archivo y no en seis.
*/

export const DESTINO_DEL_CORREO = "/perfil";
export const DESTINO_DE_LA_SUSCRIPCION = "/mi-suscripcion";

/*
  Devuelve el motivo por el que esta cuenta no puede registrar, o `null` si
  puede. Mientras la suscripcion no haya llegado se supone que si puede: esconder
  los botones un instante a quien si los tiene es peor que mostrarlos y que el
  backend rechace.
*/
export function motivoParaNoRegistrar(usuario, suscripcion, accion) {
  if (usuario && !usuario.correo_verificado) {
    return {
      clave: "correo",
      texto: `Mientras no confirmes tu correo puedes consultar, pero no ${accion}.`,
      enlace: { a: DESTINO_DEL_CORREO, etiqueta: "Revisar mi correo" },
    };
  }

  if (suscripcion && !suscripcion.puede_operar) {
    return {
      clave: "suscripcion",
      texto: `Tu suscripción no está vigente, así que puedes consultar, pero no ${accion}.`,
      enlace: { a: DESTINO_DE_LA_SUSCRIPCION, etiqueta: "Ver mi suscripción" },
    };
  }

  return null;
}
