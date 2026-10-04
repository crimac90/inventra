/*
  Quien es cada rol y donde empieza.

  Parece un detalle menor y no lo es: la respuesta hace falta en dos sitios
  —al entrar, y cuando alguien escribe a mano una direccion que no le toca— y
  escrita dos veces se desalinea a la primera. Queda aqui, una vez.

  El operador de INVENTRA no tiene licorera. Mandarlo al panel principal, que
  resume «el estado de tu licorera», es ensenarle una pantalla vacia de algo que
  nunca va a tener; lo suyo es el listado de licoreras. Y al reves: las pantallas
  del negocio no son suyas, de modo que la separacion se declara en las dos
  direcciones y no solo en una.
*/

/* El rol que administra el servicio, no un negocio. */
export const ROL_DE_PLATAFORMA = "administrador_inventra";

/* Los roles que pertenecen a una licorera. */
export const ROLES_DE_NEGOCIO = ["administrador_licorera", "vendedor"];

export function destinoTrasEntrar(usuario) {
  return usuario && usuario.rol === ROL_DE_PLATAFORMA ? "/plataforma" : "/panel";
}
