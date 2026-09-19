/*
  Panel principal.

  En este bloque cumple una funcion concreta: comprobar de punta a punta que la
  sesion funciona. Muestra los datos que devuelve la API para el usuario que
  entro. El panel completo —barra lateral, indicadores y accesos a los modulos,
  tal como esta en el punto 8.2 del documento de diseno— se construye en el
  bloque SEG-4c, reutilizando la cabecera y las tarjetas de este.
*/

import { Link } from "react-router-dom";

import Cabecera from "../componentes/Cabecera";
import { useSesion } from "../sesion/ContextoSesion";

const ROLES = {
  administrador_licorera: "Administrador de licorera",
  vendedor: "Vendedor",
  administrador_inventra: "Administrador de INVENTRA",
};

export default function Panel() {
  const { usuario } = useSesion();

  return (
    <div className="pagina">
      <Cabecera />

      <main className="contenido">
        <h1>Hola, {usuario.nombre_completo}</h1>
        <div className="hs">Sesión iniciada correctamente.</div>

        <div className="tarjeta">
          <h2>Tu cuenta</h2>
          <div className="hs">Datos con los que el sistema te identifica.</div>

          <dl className="datos">
            <dt>Correo</dt>
            <dd>{usuario.correo}</dd>

            <dt>Rol</dt>
            <dd>{ROLES[usuario.rol] || usuario.rol}</dd>

            <dt>Licorera</dt>
            <dd>{usuario.licorera_nombre || "Sin licorera asignada"}</dd>
          </dl>

          <div className="acciones">
            <Link className="btn btn-out" to="/perfil">
              Editar mi perfil
            </Link>
          </div>
        </div>
      </main>
    </div>
  );
}
