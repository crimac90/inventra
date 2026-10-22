/*
  Los tres apartados del modulo de ventas.

  Ventas no es una pantalla sino tres —cobrar, consultar lo vendido y cerrar la
  caja—, y la barra lateral lleva una entrada por modulo. Sin esto, al historial
  y al cierre solo se llegaria escribiendo la direccion.

  Es un grupo propio y no botones repartidos por cada pantalla por la misma
  razon por la que el aviso o el formato de los importes viven en un sitio:
  son las mismas tres entradas en las tres pantallas, y repartidas acabarian
  nombrandose distinto o faltando en una.

  El inventario no lo necesita y por eso no lo lleva: alli las dos pantallas
  que cuelgan del catalogo se abren desde lo que se esta mirando —la entrada
  desde la lista, el kardex desde la referencia—, de modo que hay un camino
  natural. Aqui los tres apartados son hermanos y ninguno nace del otro.
*/

import { NavLink } from "react-router-dom";

const APARTADOS = [
  { ruta: "/ventas", texto: "Vender", exacta: true },
  { ruta: "/ventas/historial", texto: "Historial" },
  { ruta: "/ventas/cierre", texto: "Cierre de caja" },
];

export default function ApartadosDeVentas() {
  return (
    <nav className="apartados" aria-label="Apartados de ventas">
      {APARTADOS.map((apartado) => (
        <NavLink
          key={apartado.ruta}
          to={apartado.ruta}
          end={apartado.exacta}
          className={({ isActive }) => (isActive ? "apartado on" : "apartado")}
        >
          {apartado.texto}
        </NavLink>
      ))}
    </nav>
  );
}
