/*
  Panel principal (punto 8.2 del documento tecnico de diseno).

  El prototipo muestra aqui cuatro indicadores: ventas de hoy, productos activos,
  stock bajo y utilidad del mes. Ninguno se puede mostrar todavia, porque sus
  datos vienen de los modulos de inventario y ventas, que aun no existen.

  La decision fue NO inventar esos numeros. Un panel con cifras fijas escritas a
  mano se ve bien en una demostracion y es mentira: en cuanto alguien pregunta de
  donde sale el dato, no hay respuesta. Asi que el panel muestra lo que el
  sistema sabe de verdad hoy —quien entro y cuantas cuentas tiene la licorera— y
  dice con claridad que falta. Cada modulo, al construirse, ira devolviendo su
  indicador a este sitio.
*/

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import Disposicion from "../componentes/Disposicion";
import { listarUsuarios } from "../api/seguridad";
import { useSesion } from "../sesion/ContextoSesion";

const ROLES = {
  administrador_licorera: "Administrador de licorera",
  vendedor: "Vendedor",
  administrador_inventra: "Administrador de INVENTRA",
};

const MODULOS_PENDIENTES = [
  ["Inventario", "Catálogo, entradas por lote, valoración PEPS y alertas de existencias"],
  ["Ventas", "Punto de venta, medios de pago, comprobante y cierre de caja"],
  ["Reportes", "Ventas por período, inventario valorizado, rotación y utilidad"],
  ["Sedes", "Varias sedes, inventario por sede y traslados de mercancía"],
];

export default function Panel() {
  const { usuario } = useSesion();
  const esAdministrador = usuario.rol === "administrador_licorera";

  const [conteo, setConteo] = useState(null);

  /*
    El conteo solo se pide si quien mira es administrador: un vendedor recibiría
    403 de esa dirección, y pedir algo que se sabe que va a fallar ensucia el
    registro del servidor sin ganar nada.
  */
  useEffect(() => {
    if (!esAdministrador) return;

    let vigente = true;
    listarUsuarios()
      .then((datos) => {
        if (!vigente) return;
        const lista = datos.results || [];
        setConteo({ total: lista.length, activos: lista.filter((u) => u.activo).length });
      })
      .catch(() => {
        if (vigente) setConteo(null);
      });

    return () => {
      vigente = false;
    };
  }, [esAdministrador]);

  return (
    <Disposicion titulo="Panel principal">
      <h1>Hola, {usuario.nombre_completo}</h1>
      <div className="hs">Este es el estado de tu licorera en INVENTRA.</div>

      {esAdministrador && (
        <div className="kpis">
          <div className="kpi">
            <div className="k">Usuarios activos</div>
            <div className="v">{conteo ? conteo.activos : "—"}</div>
            <div className="d">
              {conteo ? `${conteo.total} cuentas registradas` : "consultando…"}
            </div>
          </div>

          <div className="kpi">
            <div className="k">Tu rol</div>
            <div className="v" style={{ fontSize: "18px" }}>
              {ROLES[usuario.rol]}
            </div>
            <div className="d">acceso completo a la licorera</div>
          </div>
        </div>
      )}

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
          <Link className="btn btn-out btn-pequeno" to="/perfil">
            Editar mi perfil
          </Link>
          {esAdministrador && (
            <Link className="btn btn-out btn-pequeno" to="/usuarios">
              Gestionar usuarios
            </Link>
          )}
        </div>
      </div>

      <div className="tarjeta">
        <h2>Módulos en construcción</h2>
        <div className="hs">
          Los indicadores de ventas e inventario aparecerán aquí cuando su módulo esté
          terminado.
        </div>

        <dl className="datos">
          {MODULOS_PENDIENTES.map(([nombre, descripcion]) => (
            <div key={nombre} style={{ display: "contents" }}>
              <dt>{nombre}</dt>
              <dd style={{ color: "var(--muted)" }}>{descripcion}</dd>
            </div>
          ))}
        </dl>
      </div>
    </Disposicion>
  );
}
