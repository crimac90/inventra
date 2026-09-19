/*
  Barra superior de las pantallas internas.

  Lleva el titulo de la pantalla en la que esta el usuario, el nombre de su
  licorera y su avatar con las iniciales, tal como en el prototipo. El cierre de
  sesion vive aqui porque tiene que estar a la vista desde cualquier pantalla
  (RF-SEG-03: «desde cualquier pantalla»).
*/

import { useSesion } from "../sesion/ContextoSesion";

/* Dos iniciales a partir del nombre: «Ana Gómez Restrepo» → «AG». */
function iniciales(nombre) {
  return (nombre || "")
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0] || "")
    .join("")
    .toUpperCase();
}

export default function Cabecera({ titulo }) {
  const { usuario, salir } = useSesion();

  return (
    <header className="tb">
      <div className="h">{titulo}</div>

      <div className="r">
        {usuario.licorera_nombre && <span className="pill">{usuario.licorera_nombre}</span>}

        <span className="avatar" title={usuario.nombre_completo} aria-hidden="true">
          {iniciales(usuario.nombre_completo)}
        </span>

        <button className="btn btn-out btn-pequeno" type="button" onClick={salir}>
          Cerrar sesión
        </button>
      </div>
    </header>
  );
}
