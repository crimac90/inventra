/*
  Cabecera de las pantallas internas.

  Lleva la marca, la navegacion y el cierre de sesion. Se separa en un componente
  porque va a aparecer en todas las pantallas con sesion abierta; en el bloque
  SEG-4c se le sumara la barra lateral con los modulos.

  `NavLink` es como un enlace normal, pero sabe si la direccion actual es la suya
  y aplica la clase «activo». Asi el usuario ve siempre en que pantalla esta.
*/

import { NavLink } from "react-router-dom";

import { useSesion } from "../sesion/ContextoSesion";

export default function Cabecera() {
  const { salir } = useSesion();

  const clase = ({ isActive }) => (isActive ? "activo" : undefined);

  return (
    <header className="cabecera">
      <div className="logo">
        <span className="mk" aria-hidden="true"></span> INVENTRA
      </div>

      <nav>
        <NavLink to="/panel" className={clase}>
          Panel
        </NavLink>
        <NavLink to="/perfil" className={clase}>
          Mi perfil
        </NavLink>
      </nav>

      <button className="btn btn-out" type="button" onClick={salir}>
        Cerrar sesión
      </button>
    </header>
  );
}
