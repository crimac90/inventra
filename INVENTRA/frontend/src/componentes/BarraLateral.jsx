/*
  Barra lateral de navegacion.

  Los seis modulos son los del prototipo y del punto 8.2 del documento de diseno.
  Los que no se pueden usar aparecen apagados y no se pueden pulsar: mostrarlos
  deja ver el alcance del sistema, y apagarlos evita el enlace que no lleva a
  ninguna parte.

  El estado de cada modulo lo dice el servidor, no esta escrito aqui. Que un
  modulo este construido y que entre en el plan contratado son dos preguntas
  suyas (RF-SUS-04): a una licorera con plan Basico, Sedes no le llega nunca,
  porque multisede es del plan Pro, y anunciarlo como «Pronto» seria falso. De
  la interfaz es solo el orden, el icono y el texto. Mientras la respuesta no
  llega, los modulos sin direccion se pintan apagados y sin etiqueta.

  El operador de INVENTRA tiene su propio menu, armado de una lista aparte. No
  es un usuario con mas permisos sobre los seis modulos: es otro oficio, y
  ninguno de ellos es suyo.

  Los iconos van escritos aqui, en linea, por dos razones: son los mismos ocho
  del prototipo, sobre reticula de 24 pixeles, y al ser dibujos y no imagenes
  toman el color del texto que los rodea, de modo que el estado activo cambia
  icono y letra a la vez.
*/

import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";

import { consultarMisModulos } from "../api/suscripciones";
import InterruptorTema from "./InterruptorTema";

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
  plataforma: (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18" />
      <path d="M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3z" />
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
  { clave: "inventario", texto: "Inventario", ruta: "/inventario" },
  { clave: "ventas", texto: "Ventas", ruta: "/ventas" },
  { clave: "reportes", texto: "Reportes" },
  { clave: "sedes", texto: "Sedes" },
];

/*
  El menu del operador de INVENTRA es otro. No es que tenga mas permisos sobre
  los mismos seis modulos: es que ninguno de ellos es suyo. Inventario, Ventas o
  Sedes son de un negocio, y el no tiene negocio; lo que el administra son las
  licoreras y sus suscripciones. Por eso esta lista no sale del catalogo del
  servidor —no son modulos contratables, no dependen de ningun plan— y por eso
  no se le pregunta al servidor en que estado estan.
*/
const SECCIONES_PLATAFORMA = [
  { seccion: "plataforma", texto: "Plataforma", ruta: "/plataforma" },
];

// Lo que se escribe al lado del modulo que no se puede pulsar. El texto del
// servidor es una clave, no una etiqueta: traducirla es cosa de la interfaz.
const ETIQUETA = {
  pronto: { texto: "Pronto", titulo: "Todavía no está disponible." },
  plan: { texto: "Pro", titulo: "Disponible en el plan Pro." },
};

export default function BarraLateral({ esAdministrador, esPlataforma }) {
  const clase = ({ isActive }) => (isActive ? "nav on" : "nav");
  const [estados, setEstados] = useState({});

  useEffect(() => {
    // Al operador de la plataforma no se le consulta el catalogo: su menu no
    // depende de ningun plan, y pedirlo seria una llamada cuya respuesta se
    // descarta entera.
    if (esPlataforma) return undefined;

    let vigente = true;
    consultarMisModulos()
      .then(({ modulos }) => {
        if (!vigente) return;
        setEstados(Object.fromEntries(modulos.map((m) => [m.clave, m.estado])));
      })
      .catch(() => {});
    return () => {
      vigente = false;
    };
  }, [esPlataforma]);

  /*
    Las dos listas se recorren igual; lo unico que cambia es de donde salen. La
    del operador se normaliza a la misma forma para no duplicar el recorrido: no
    lleva estado, de modo que cae siempre en la rama del enlace.
  */
  const entradas = esPlataforma
    ? SECCIONES_PLATAFORMA.map((s) => ({ ...s, clave: s.seccion }))
    : MODULOS.filter((m) => !m.soloAdministrador || esAdministrador);

  return (
    <aside className="side">
      <div className="logo">
        <span className="mk" aria-hidden="true"></span> INVENTRA
      </div>

      <nav aria-label="Módulos">
        {entradas.map((modulo) => {
          const etiqueta = ETIQUETA[estados[modulo.clave]];
          if (modulo.ruta && !etiqueta) {
            return (
              <NavLink key={modulo.clave} to={modulo.ruta} className={clase}>
                {ICONOS[modulo.clave]} {modulo.texto}
              </NavLink>
            );
          }
          return (
            <span
              key={modulo.clave}
              className="nav pendiente"
              aria-disabled="true"
              title={etiqueta ? etiqueta.titulo : undefined}
            >
              {ICONOS[modulo.clave]} {modulo.texto}
              {etiqueta ? <span className="proximamente">{etiqueta.texto}</span> : null}
            </span>
          );
        })}
      </nav>

      <div className="grow"></div>

      <InterruptorTema />

      <NavLink to="/perfil" className={clase}>
        {ICONOS.perfil} Mi perfil
      </NavLink>
    </aside>
  );
}
