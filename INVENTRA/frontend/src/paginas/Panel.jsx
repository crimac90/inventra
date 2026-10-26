/*
  Panel principal (punto 8.2 del documento tecnico de diseno).

  El prototipo muestra aqui cuatro indicadores: ventas de hoy, productos
  activos, existencias bajas y utilidad del mes. Los cuatro salen ya de datos
  reales.

  La regla fue no inventar numeros. Un panel con cifras fijas escritas a mano
  se ve bien en una demostracion y es mentira: en cuanto alguien pregunta de
  donde sale el dato, no hay respuesta. Cada modulo, al construirse, devolvio
  su indicador a este sitio, y los dos que faltaban llegaron con las ventas.

  LO VENDIDO SE CUENTA POR JORNADA Y NO POR DIA DEL CALENDARIO. A la una de la
  madrugada, «hoy» es la noche que sigue abierta; si el panel dijera otra cosa
  que el cierre de caja, las dos cifras serian correctas y distintas, que es
  peor que una equivocada.

  TRES AVISOS Y TRES SITIOS DISTINTOS, segun lo que pida cada uno. Lo que hay
  que reponer se ensena entero, porque un contador obliga a ir a buscar que
  referencias son (RF-INV-07). Las estancadas se cuentan y se enlazan, porque
  son el unico requisito de prioridad baja del inventario y darles el mismo
  sitio que a lo urgente empujaria hacia abajo lo que hay que mirar a diario
  (RF-INV-08). Y las cajas que cerraron descuadradas sin explicar se nombran
  una a una y no se van hasta que alguien escriba el porque.
*/

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import AvisoSuscripcion from "../componentes/AvisoSuscripcion";
import Disposicion from "../componentes/Disposicion";
import { consultarResumen } from "../api/inventario";
import { listarUsuarios } from "../api/seguridad";
import { consultarResumenDeVentas } from "../api/ventas";
import { fecha, moneda } from "../formato";
import { plural } from "../texto";
import { ETIQUETA_DE_ROL } from "../sesion/roles";
import { useSesion } from "../sesion/ContextoSesion";

// Cuantas referencias por reponer se nombran antes de remitir al catalogo. Una
// lista mas larga que esto deja de leerse y empieza a empujar hacia abajo todo
// lo demas del panel.
const MAXIMO_EN_LA_LISTA = 5;

const MODULOS_PENDIENTES = [
  ["Reportes", "Ventas por período, inventario valorizado, rotación y utilidad"],
  ["Sedes", "Varias sedes, inventario por sede y traslados de mercancía"],
];

export default function Panel() {
  const { usuario } = useSesion();
  const esAdministrador = usuario.rol === "administrador_licorera";

  const [conteo, setConteo] = useState(null);
  const [inventario, setInventario] = useState(null);
  const [ventas, setVentas] = useState(null);

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

  /*
    El resumen de ventas lo pide todo el mundo igual, y es el servidor quien
    decide que parte le toca a cada rol: al vendedor no le manda las jornadas
    descuadradas, porque no puede escribir la explicacion.
  */
  useEffect(() => {
    let vigente = true;
    consultarResumenDeVentas()
      .then((datos) => {
        if (vigente) setVentas(datos);
      })
      .catch(() => {
        if (vigente) setVentas(null);
      });

    return () => {
      vigente = false;
    };
  }, []);

  const porReponer = inventario ? inventario.existencias_bajas : [];
  const sinExplicar = ventas ? ventas.jornadas_sin_explicar : [];
  const sinCerrar = ventas ? ventas.jornadas_sin_cerrar || [] : [];

  return (
    <Disposicion titulo="Panel principal">
      <h1>Hola, {usuario.nombre_completo}</h1>
      <div className="hs">Este es el estado de tu licorera en INVENTRA.</div>

      <AvisoSuscripcion />

      <div className="kpis">
        <div className="kpi">
          <div className="k">Ventas de la jornada</div>
          <div className="v">
            {ventas ? moneda(Number(ventas.vendido_en_la_jornada)) : "—"}
          </div>
          <div className="d">
            {ventas
              ? plural(ventas.transacciones_de_la_jornada, "transacción", "transacciones")
              : "consultando…"}
          </div>
        </div>

        {/*
          La utilidad es del administrador y no de quien está en la caja. Lo
          vendido sí lo ve el vendedor —es el resultado de su turno—, pero
          cuánto gana el negocio con cada botella no es dato de mostrador.
        */}
        {esAdministrador && (
          <div className="kpi">
            <div className="k">Utilidad del mes</div>
            <div className="v">{ventas ? moneda(Number(ventas.utilidad_del_mes)) : "—"}</div>
            <div className="d">
              {ventas
                ? `sobre ${moneda(Number(ventas.vendido_en_el_mes))} vendidos`
                : "consultando…"}
            </div>
          </div>
        )}

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

        <div className="kpi">
          <div className="k">Sin rotación</div>
          <div className="v">{inventario ? inventario.sin_rotacion : "—"}</div>
          <div className="d">
            {!inventario ? (
              "consultando…"
            ) : inventario.sin_rotacion === 0 ? (
              "todo se mueve"
            ) : (
              /*
                El detalle no se lista aqui: se enlaza al catalogo con el
                filtro puesto, que es donde se actua sobre una referencia.
              */
              <Link className="link" to={`/inventario?rotacion=${inventario.dias_sin_rotacion}`}>
                sin venderse en {inventario.dias_sin_rotacion} días
              </Link>
            )}
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

      {sinCerrar.length > 0 && (
        <div className="tarjeta atencion">
          <h2>Jornadas sin cerrar</h2>
          <div className="hs">
            Noches con ventas en las que nadie contó la caja. El sistema no
            puede saber si faltó dinero: lo único que puede decir es que no se
            contó.
          </div>

          <dl className="datos">
            {sinCerrar.map((jornada) => (
              <div key={jornada.fecha} style={{ display: "contents" }}>
                <dt>
                  {fecha(jornada.fecha)}
                  <div className="hs">{jornada.sede_nombre}</div>
                </dt>
                <dd>
                  {plural(jornada.transacciones, "venta")} por{" "}
                  {moneda(Number(jornada.total))}{" "}
                  <Link className="link" to={`/ventas/cierre?jornada=${jornada.fecha}`}>
                    Cerrarla
                  </Link>
                </dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {sinExplicar.length > 0 && (
        <div className="tarjeta atencion">
          <h2>Cajas con diferencia sin explicar</h2>
          <div className="hs">
            Jornadas que cerraron descuadradas y en las que nadie ha escrito el
            porqué. El aviso se retira cuando se escribe, no cuando se lee.
          </div>

          <dl className="datos">
            {sinExplicar.map((jornada) => (
              <div key={jornada.id} style={{ display: "contents" }}>
                <dt>
                  {fecha(jornada.fecha)}
                  <div className="hs">{jornada.sede_nombre}</div>
                </dt>
                <dd>
                  <span className="estado agotado">
                    {Number(jornada.diferencia) < 0
                      ? `Faltan ${moneda(-Number(jornada.diferencia))}`
                      : `Sobran ${moneda(Number(jornada.diferencia))}`}
                  </span>{" "}
                  <Link className="link" to={`/ventas/cierre?jornada=${jornada.fecha}`}>
                    Explicar
                  </Link>
                </dd>
              </div>
            ))}
          </dl>
        </div>
      )}

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
          Lo que el sistema todavía no hace. Aparecerá aquí cuando cada módulo
          esté terminado.
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
