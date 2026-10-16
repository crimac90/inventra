/*
  Lo que la interfaz sabe sobre quien puede registrar informacion.

  Gemelo de `suscripciones/permissions.py`. LA REGLA DE VERDAD VIVE EN EL
  SERVIDOR: esta funcion no protege nada y no puede, porque cualquiera abre las
  herramientas del navegador. Existe por una sola razon:
  no ofrecer un boton que se va a rechazar, y decir el motivo antes de que la
  persona rellene un formulario para nada.

  LOS TRES MOTIVOS Y SU ORDEN tienen que coincidir con los del permiso. Si el
  servidor rechaza por el correo y la pantalla anuncia la suscripcion, la persona
  se va a arreglar lo que no era. El servidor mira primero el rol, despues el
  correo y por ultimo la suscripcion, y aqui se mira igual.

  EL ROL FALTABA. Mientras las pantallas con escritura fueron solo las de
  usuarios, no hacia falta: esa pantalla entera es del administrador y la ruta
  la cierra antes. Inventario es de los dos roles, de modo que un vendedor veia
  los botones de crear, editar, descontinuar, registrar entradas y ajustar, y
  el servidor le respondia 403 en los cinco.

  La accion la pone cada pantalla —«crear ni modificar cuentas», «registrar
  ventas»— porque es lo unico que cambia de una a otra; el resto de la frase y la
  eleccion del motivo se deciden en este archivo y no en seis.

  NO TODOS LOS MOTIVOS SE ANUNCIAN, y `avisar` lo decide aqui. Se avisa de lo
  que la persona puede resolver: confirmar el correo, renovar el plan. Son
  estados pasajeros, tienen adonde ir y por eso llevan enlace. El rol no es un
  estado: es el reparto del trabajo, no cambia y no lleva a ninguna parte.
  Anunciarlo en cada visita seria avisar de algo que no ha ocurrido, porque los
  botones que explicaria tampoco estan. Esconderlos basta, igual que el menu
  lateral esconde «Usuarios» sin explicar nada.
*/

import { ROL_ADMINISTRADOR_LICORERA } from "./roles";

export const DESTINO_DEL_CORREO = "/perfil";
export const DESTINO_DE_LA_SUSCRIPCION = "/mi-suscripcion";

/*
  Devuelve el motivo por el que esta cuenta no puede registrar, o `null` si
  puede. Mientras la suscripcion no haya llegado se supone que si puede: esconder
  los botones un instante a quien si los tiene es peor que mostrarlos y que el
  backend rechace.
*/
export function motivoParaNoRegistrar(usuario, suscripcion, accion) {
  /*
    El vendedor no tiene adonde ir a arreglar esto, asi que este motivo no
    lleva enlace: no es un tramite pendiente, es el reparto del trabajo.
  */
  if (usuario && usuario.rol !== ROL_ADMINISTRADOR_LICORERA) {
    return {
      clave: "rol",
      avisar: false,
      texto: `Tu cuenta consulta la información del negocio, pero no ${accion}. Eso lo hace quien administra la licorera.`,
    };
  }

  if (usuario && !usuario.correo_verificado) {
    return {
      clave: "correo",
      avisar: true,
      texto: `Mientras no confirmes tu correo puedes consultar, pero no ${accion}.`,
      enlace: { a: DESTINO_DEL_CORREO, etiqueta: "Revisar mi correo" },
    };
  }

  if (suscripcion && !suscripcion.puede_operar) {
    return {
      clave: "suscripcion",
      avisar: true,
      texto: `Tu suscripción no está vigente, así que puedes consultar, pero no ${accion}.`,
      enlace: { a: DESTINO_DE_LA_SUSCRIPCION, etiqueta: "Ver mi suscripción" },
    };
  }

  return null;
}
