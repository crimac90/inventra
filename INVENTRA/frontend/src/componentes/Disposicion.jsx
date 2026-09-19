/*
  Armazon de las pantallas internas.

  Reune la barra lateral, la barra superior y el area de contenido. Cada pantalla
  solo escribe lo suyo y lo envuelve en este componente, de modo que la
  navegacion y la cabecera se definen una vez y no se pueden desalinear entre
  pantallas.
*/

import BarraLateral from "./BarraLateral";
import Cabecera from "./Cabecera";
import { useSesion } from "../sesion/ContextoSesion";

export default function Disposicion({ titulo, children }) {
  const { usuario } = useSesion();
  const esAdministrador = usuario.rol === "administrador_licorera";

  return (
    <div className="app">
      <BarraLateral esAdministrador={esAdministrador} />

      <div className="main">
        <Cabecera titulo={titulo} />
        <main className="content">{children}</main>
      </div>
    </div>
  );
}
