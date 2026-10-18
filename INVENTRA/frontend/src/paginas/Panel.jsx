/*
  Panel principal (punto 8.2 del documento tecnico de diseno).

  El prototipo muestra aqui cuatro indicadores: ventas de hoy, productos
  activos, existencias bajas y utilidad del mes. Dos de ellos ya se pueden
  calcular con datos reales; los otros dos salen de las ventas y se anuncian
  como pendientes.

  La regla es no inventar numeros. Un panel con cifras fijas escritas a mano se
  ve bien en una demostracion y es mentira: en cuanto alguien pregunta de donde
  sale el dato, no hay respuesta. Cada modulo, al construirse, devuelve su
  indicador a este sitio.

  Aqui es ademas donde RF-INV-07 pide que viva la alerta de existencias bajas,
  y por eso la lista de lo que hay que reponer se ensena entera y no como un
  numero suelto: un contador obliga a ir a buscar que referencias son.
*/

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import AvisoSuscripcion from "../componentes/AvisoSuscripcion";
import Disposicion from "../componentes/Disposicion";
import { consultarResumen } from "../api/inventario";
import { listarUsuarios } from "../api/seguridad";
import { plural } from "../texto";
import { ETIQUETA_DE_ROL } from "../sesion/roles";
import { useSesion } from "../sesion/ContextoSesion";

// Cuantas referencias por reponer se nombran antes de remitir al catalogo. Una
// lista mas larga que esto deja de leerse y empieza a empujar hacia abajo todo
// lo demas del panel.
const MAXIMO_EN_LA_LISTA = 5;

const MODULOS_PENDIENTES = [
  ["Ventas", "Punto de venta, medios de pago, comprobante y cierre de caja"],
  ["Reportes", "Ventas por período, inventario valorizado, rotación y utilidad"],
  ["Sedes", "Varias sedes, inventario por sede y traslados de mercancía"],
];

export default function Panel() {
  const { usuario } = useSesion();
  const esAdministrador = usuario.rol === "administrador_licorera";

  const [conteo, setConteo] = useState(null);
  const [inventario, setInventario] = useState(null);

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

  /*
    El resumen del inventario lo pide todo el mundo, tambien el vendedor: es
    quien esta en el mostrador y el primero que nota que algo se acabo.
  */
  useEffect(() => {
    let vigente = true;
    consultarResumen()
      .then((datos) => {
        if (vigente) setInventario(datos);
      })
      .catch(() => {
        if (vigente) setInventario(null);
      });

    return () => {
      vigente = false;
    };
  }, []);

  const porReponer = inventario ? inventario.existencias_bajas : [];

  return (
    <Disposicion titulo="Panel principal">
      <h1>Hola, {usuario.nombre_completo}</h1>
      <div className="hs">Este es el estado de tu licorera en INVENTRA.</div>

      <AvisoSuscripcion />

      <div className="kpis">
        {esAdministrador && (
          <div className="kpi">
            <div className="k">Usuarios activos</div>
            <div className="v">{conteo ? conteo.activos : "—"}</div>
            <div className="d">
              {conteo ? plural(conteo.total, "cuenta registrada", "cuentas registradas") : "consultando…"}
            </div>
          </div>
        )}

        <div className="kpi">
          <div className="k">Referencias activas</div>
          <div className="v">{inventario ? inventario.productos_activos : "—"}</div>
          <div className="d">{inventario ? "en el catálogo" : "consultando…"}</div>
        </div>

        <div className="kpi">
          <div className="k">Existencias bajas</div>
          <div className="v">{inventario ? porReponer.length : "—"}</div>
          <div className="d">
            {inventario
              ? porReponer.length === 0
                ? "nada por reponer"
                : "igual o por debajo del mínimo"
              : "consultando…"}
          </div>
        </div>

        {esAdministrador && (
          <div className="kpi">
            <div className="k">Tu rol</div>
            <div className="v" style={{ fontSize: "18px" }}>
              {ETIQUETA_DE_ROL[usuario.rol]}
            </div>
            <div className="d">acceso completo a la licorera</div>
          </div>
        )}
      </div>

      {porReponer.length > 0 && (
        <div className="tarjeta">
          <h2>Por reponer</h2>
          <div className="hs">
            Referencias con existencias iguales o inferiores a su mínimo, de lo más
            urgente a lo menos.
          </div>

          <dl className="datos">
            {porReponer.slice(0, MAXIMO_EN_LA_LISTA).map((producto) => (
              <div key={producto.id} style={{ display: "contents" }}>
                <dt>{producto.nombre}</dt>
                <dd>
                  {producto.existencias === 0 ? (
                    <span className="estado agotado">Agotado</span>
                  ) : (
                    <span className="estado bajo">
                      {plural(producto.existencias, "unidad", "unidades")}
                    </span>
                  )}{" "}
                  <span style={{ color: "var(--muted)" }}>
                    mínimo {producto.stock_minimo}
                  </span>
                </dd>
              </div>
            ))}
          </dl>

          <div className="acciones">
            <Link className="btn btn-out btn-pequeno" to="/inventario?existencias=bajo">
              {porReponer.length > MAXIMO_EN_LA_LISTA
                ? `Ver las ${porReponer.length} en el catálogo`
                : "Ver en el catálogo"}
            </Link>
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
          <dd>{ETIQUETA_DE_ROL[usuario.rol] || usuario.rol}</dd>

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
          {esAdministrador && (
            <Link className="btn btn-out btn-pequeno" to="/mi-suscripcion">
              Mi suscripción
            </Link>
          )}
        </div>
      </div>

      <div className="tarjeta">
        <h2>Módulos en construcción</h2>
        <div className="hs">
          Los indicadores de ventas del día y utilidad del mes aparecerán aquí cuando
          su módulo esté terminado.
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
