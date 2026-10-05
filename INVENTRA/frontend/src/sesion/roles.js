/*
  Lo que la interfaz sabe de los roles.

  Tres cosas que antes vivian repartidas: el nombre del rol que administra el
  servicio, cuales pertenecen a un negocio, y como se escribe cada uno para la
  persona. Esa ultima estaba DOS VECES, identica, en el panel y en el perfil.

  El archivo se llamaba `destino.js` y solo respondia donde empieza cada rol.
  Al aparecer la segunda pregunta sobre lo mismo se renombro: lo que agrupa a
  estas cuatro cosas es el rol, no el destino.

  La lista de usuarios NO usa `ETIQUETA_DE_ROL`: alli, dentro de una licorera,
  «Administrador» basta y decir «Administrador de licorera» en cada fila sobra.
  Son dos textos distintos a proposito, no una copia que se quedo atras.
*/

/* El rol que administra el servicio, no un negocio. */
export const ROL_DE_PLATAFORMA = "administrador_inventra";

/* Los roles que pertenecen a una licorera. */
export const ROLES_DE_NEGOCIO = ["administrador_licorera", "vendedor"];

/* Como se le escribe cada rol a la persona. */
export const ETIQUETA_DE_ROL = {
  administrador_licorera: "Administrador de licorera",
  vendedor: "Vendedor",
  administrador_inventra: "Administrador de INVENTRA",
};

/*
  Donde aterriza cada rol.

  Parece un detalle menor y no lo es: la respuesta hace falta en dos sitios
  —al entrar, y cuando alguien escribe a mano una direccion que no le toca— y
  escrita dos veces se desalinea a la primera.

  El operador de INVENTRA no tiene licorera. Mandarlo al panel principal, que
  resume «el estado de tu licorera», es ensenarle una pantalla vacia de algo que
  nunca va a tener; lo suyo es el listado de licoreras.
*/
export function destinoTrasEntrar(usuario) {
  return usuario && usuario.rol === ROL_DE_PLATAFORMA ? "/plataforma" : "/panel";
}
