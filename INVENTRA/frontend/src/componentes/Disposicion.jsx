/*
  Armazon de las pantallas internas.

  Reune la barra lateral, la barra superior y el area de contenido. Cada pantalla
  solo escribe lo suyo y lo envuelve en este componente, de modo que la
  navegacion y la cabecera se definen una vez y no se pueden desalinear entre
  pantallas.

  El rol se lee aqui y no dentro de la barra lateral porque es este componente
  el que conoce la sesion. La barra recibe dos respuestas ya tomadas —si quien
  mira administra un negocio y si administra la plataforma— y se limita a
  pintar: asi la decision de quien ve que esta en un solo sitio.
*/

import AvisoVerificacion from "./AvisoVerificacion";
import BarraLateral from "./BarraLateral";
import Cabecera from "./Cabecera";
import { ROL_DE_PLATAFORMA } from "../sesion/roles";
import { useSesion } from "../sesion/ContextoSesion";

export default function Disposicion({ titulo, children }) {
  const { usuario } = useSesion();
  const esAdministrador = usuario.rol === "administrador_licorera";
  const esPlataforma = usuario.rol === ROL_DE_PLATAFORMA;

  return (
    <div className="app">
      <BarraLateral esAdministrador={esAdministrador} esPlataforma={esPlataforma} />

      <div className="main">
        <Cabecera titulo={titulo} />
        <main className="content">
          <AvisoVerificacion />
          {children}
        </main>
      </div>
    </div>
  );
}
