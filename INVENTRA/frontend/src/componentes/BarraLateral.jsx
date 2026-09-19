/*
  Barra lateral de navegacion.

  Los seis modulos son los del prototipo y del punto 8.2 del documento de diseno.
  Los que todavia no se han construido aparecen apagados y no se pueden pulsar:
  mostrarlos deja ver el alcance del sistema, y apagarlos evita el enlace que no
  lleva a ninguna parte. A medida que se construya cada modulo se le quita la
  marca de pendiente y se le pone su direccion.

  Los iconos van escritos aqui, en linea, por dos razones: son los mismos ocho
  del prototipo, sobre reticula de 24 pixeles, y al ser dibujos y no imagenes
  toman el color del texto que los rodea, de modo que el estado activo cambia
  icono y letra a la vez.
*/

import { NavLink } from "react-router-dom";

const ICONOS = {
  panel: (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </svg>
  ),
  inventario: (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M3 7l9-4 9 4-9 4-9-4z" />
      <path d="M3 7v10l9 4 9-4V7" />
    </svg>
  ),
  ventas: (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="9" cy="20" r="1.5" />
      <circle cx="18" cy="20" r="1.5" />
      <path d="M2 3h3l2.4 12h11l1.6-8H6" />
    </svg>
  ),
  reportes: (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />
    </svg>
  ),
  sedes: (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M3 21V9l9-6 9 6v12z" />
      <path d="M9 21v-6h6v6" />
    </svg>
  ),
  usuarios: (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="9" cy="8" r="3.5" />
      <path d="M2 20c0-3.3 3.1-6 7-6s7 2.7 7 6" />
      <path d="M17 8.5a3 3 0 0 1 0 5" />
      <path d="M19 20c0-2.4-1-4.4-2.6-5.5" />
    </svg>
  ),
  perfil: (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 13a7.6 7.6 0 0 0 0-2l2-1.5-2-3.5-2.3 1a7.6 7.6 0 0 0-1.7-1L14.9 2H9.1l-.5 3a7.6 7.6 0 0 0-1.7 1l-2.3-1-2 3.5L4.6 11a7.6 7.6 0 0 0 0 2l-2 1.5 2 3.5 2.3-1a7.6 7.6 0 0 0 1.7 1l.5 3h5.8l.5-3a7.6 7.6 0 0 0 1.7-1l2.3 1 2-3.5z" />
    </svg>
  ),
};

/*
  `soloAdministrador` marca las entradas que un vendedor no debe ver. Ocultarlas
  es cortesia, no seguridad: aunque alguien escribiera la direccion a mano, el
  backend responderia 403 igualmente. Ese es el orden correcto de las dos capas.
*/
const MODULOS = [
  { clave: "panel", texto: "Panel", ruta: "/panel" },
  { clave: "usuarios", texto: "Usuarios", ruta: "/usuarios", soloAdministrador: true },
  { clave: "inventario", texto: "Inventario", pendiente: true },
  { clave: "ventas", texto: "Ventas", pendiente: true },
  { clave: "reportes", texto: "Reportes", pendiente: true },
  { clave: "sedes", texto: "Sedes", pendiente: true },
];

export default function BarraLateral({ esAdministrador }) {
  const clase = ({ isActive }) => (isActive ? "nav on" : "nav");

  return (
    <aside className="side">
      <div className="logo">
        <span className="mk" aria-hidden="true"></span> INVENTRA
      </div>

      <nav aria-label="Módulos">
        {MODULOS.filter((m) => !m.soloAdministrador || esAdministrador).map((modulo) =>
          modulo.pendiente ? (
            <span key={modulo.clave} className="nav pendiente" aria-disabled="true">
              {ICONOS[modulo.clave]} {modulo.texto}
              <span className="proximamente">Próximamente</span>
            </span>
          ) : (
            <NavLink key={modulo.clave} to={modulo.ruta} className={clase}>
              {ICONOS[modulo.clave]} {modulo.texto}
            </NavLink>
          ),
        )}
      </nav>

      <div className="grow"></div>

      <NavLink to="/perfil" className={clase}>
        {ICONOS.perfil} Mi perfil
      </NavLink>
    </aside>
  );
}
