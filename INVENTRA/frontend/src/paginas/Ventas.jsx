/*
  Historial de ventas (RF-VEN-04 y RF-VEN-05), apartado 8.8 del documento de
  diseno.

  Reune la consulta de lo vendido y la unica correccion que el sistema admite
  sobre una venta. Entran los dos roles del negocio: quien vende necesita
  alcanzar una venta para volver a imprimir su comprobante, que es lo que pasa
  cuando el cliente rechaza la factura y la pide un minuto despues. Lo que el
  vendedor no ve es el filtro por vendedor, porque la lista de cuentas de la
  licorera sigue siendo del administrador.

  Si una venta admite anulacion lo dice el servidor en cada fila. La regla es
  que pertenezca a la jornada en curso, y la jornada empieza a las seis de la
  manana: escribir esa hora tambien aqui la dejaria en dos sitios que pueden
  dejar de coincidir.

  Los tres indicadores hablan del periodo filtrado y no de la pagina que se
  esta viendo. Llegan en la misma respuesta que las filas, de modo que no
  pueden contar cosas distintas.

  Al cambiar un filtro se vuelve a la primera pagina. Quedarse en la septima de
  una busqueda que ahora tiene dos ensena una tabla vacia sobre un total que
  dice que hay resultados.
*/

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import Campo from "../componentes/Campo";
import CampoSeleccion from "../componentes/CampoSeleccion";
import Comprobante from "../componentes/Comprobante";
import Disposicion from "../componentes/Disposicion";
import Modal from "../componentes/Modal";
import Paginacion from "../componentes/Paginacion";
import ApartadosDeVentas from "../componentes/ApartadosDeVentas";

import { mensajeDeError } from "../api/cliente";
import { consultarMiSuscripcion } from "../api/suscripciones";
import { listarUsuarios } from "../api/seguridad";
import {
  anularVenta, consultarMediosDePago, consultarVenta, listarVentas,
} from "../api/ventas";

import { useAviso } from "../aviso";
import { fechaHora, moneda } from "../formato";
import { motivoParaNoRegistrar } from "../sesion/permisos";
import { useSesion } from "../sesion/ContextoSesion";
import { plural } from "../texto";
import { useEspera } from "../espera";

const SIN_FILTRO = "";

export default function Ventas() {
  const { usuario: yo } = useSesion();
  const esAdministrador = yo.rol === "administrador_licorera";

  const [filtros, setFiltros] = useState({
    desde: SIN_FILTRO, hasta: SIN_FILTRO, vendedor: SIN_FILTRO, medio_pago: SIN_FILTRO,
  });
  const [escrito, setEscrito] = useState("");
  const buscado = useEspera(escrito);
  const [pagina, setPagina] = useState(1);

  const [ventas, setVentas] = useState([]);
  const [cuantas, setCuantas] = useState(0);
  const [cifras, setCifras] = useState(null);
  const [vendedores, setVendedores] = useState([]);
  const [medios, setMedios] = useState([]);

  const [abierta, setAbierta] = useState(null);
  const [porAnular, setPorAnular] = useState(null);
  const [motivoDeAnulacion, setMotivoDeAnulacion] = useState("");

  const [suscripcion, setSuscripcion] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [ocupado, setOcupado] = useState(false);
  const [aviso, setAviso] = useAviso();
  const primeraCarga = useRef(true);

  const impedimento = motivoParaNoRegistrar(yo, suscripcion, "anular ventas");

  const consulta = useMemo(
    () => ({ ...filtros, buscar: buscado, page: pagina }), [filtros, buscado, pagina]);

  const refrescar = useCallback(async () => {
    const datos = await listarVentas(consulta);
    setVentas(datos.results || []);
    setCuantas(datos.count || 0);
    setCifras(datos.resumen || null);
  }, [consulta]);

  useEffect(() => {
    let vigente = true;

    if (primeraCarga.current) {
      consultarMediosDePago().then((datos) => vigente && setMedios(datos)).catch(() => {});
      consultarMiSuscripcion().then((datos) => vigente && setSuscripcion(datos)).catch(() => {});
      /*
        La lista de cuentas es del administrador, de modo que a un vendedor ni
        se le pide: pedirla seria provocar un 403 cuya unica consecuencia seria
        dejar vacio un desplegable que el no deberia ver.
      */
      if (esAdministrador) {
        listarUsuarios().then((datos) => {
          if (vigente) setVendedores(datos.results || datos || []);
        }).catch(() => {});
      }
    }

    listarVentas(consulta)
      .then((datos) => {
        if (!vigente) return;
        setVentas(datos.results || []);
        setCuantas(datos.count || 0);
        setCifras(datos.resumen || null);
      })
      .catch((error) => {
        if (vigente) setAviso({ tipo: "err", texto: mensajeDeError(error) });
      })
      .finally(() => {
        if (!vigente) return;
        setCargando(false);
        primeraCarga.current = false;
      });

    return () => { vigente = false; };
  }, [consulta, esAdministrador, setAviso]);

  const cambiarFiltro = useCallback((clave, valor) => {
    setAviso(null);
    setPagina(1);
    setFiltros((actuales) => ({ ...actuales, [clave]: valor }));
  }, [setAviso]);

  const cambiarBusqueda = useCallback((valor) => {
    setAviso(null);
    setPagina(1);
    setEscrito(valor);
  }, [setAviso]);

  const abrir = useCallback(async (venta) => {
    setAviso(null);
    try {
      // La lista no trae las lineas: para el comprobante hay que pedir la
      // venta entera, que es justo lo que el historial evita hacer por cada
      // fila de la tabla.
      setAbierta(await consultarVenta(venta.id));
    } catch (error) {
      setAviso({ tipo: "err", texto: mensajeDeError(error) });
    }
  }, [setAviso]);

  const confirmarAnulacion = useCallback(async () => {
    if (!porAnular) return;
    setOcupado(true);
    try {
      const venta = await anularVenta(porAnular.id, motivoDeAnulacion);
      setPorAnular(null);
      setMotivoDeAnulacion("");
      await refrescar();
      setAviso({
        tipo: "ok",
        texto: `Venta #${venta.consecutivo} anulada. `
             + `${plural(venta.lineas.length, "referencia")} de vuelta en el inventario.`,
      });
    } catch (error) {
      /*
        La ventana se cierra aunque la anulacion falle. Dejarla abierta
        esconderia detras el aviso que explica el rechazo, y reintentar sin
        poder leer por que fallo no es reintentar.
      */
      setPorAnular(null);
      setAviso({ tipo: "err", texto: mensajeDeError(error) });
    } finally {
      setOcupado(false);
    }
  }, [porAnular, motivoDeAnulacion, refrescar, setAviso]);

  return (
    <Disposicion titulo="Ventas">
      <ApartadosDeVentas />

      <h1>Historial de ventas</h1>
      <p className="hs">
        Lo vendido, con sus filtros. Las ventas anuladas no desaparecen: se
        muestran marcadas y con su motivo.
      </p>

      {aviso && <div className={`aviso ${aviso.tipo}`} role="status">{aviso.texto}</div>}

      <div className="filtros">
        <input
          className="buscador"
          type="search"
          value={escrito}
          placeholder="Buscar por número de venta o producto…"
          aria-label="Buscar por número de venta o producto"
          onChange={(e) => cambiarBusqueda(e.target.value)}
        />
        {esAdministrador && (
          <CampoSeleccion
            id="vendedor"
            etiqueta="Vendedor"
            valor={filtros.vendedor}
            onChange={(valor) => cambiarFiltro("vendedor", valor)}
            opciones={[{ valor: SIN_FILTRO, texto: "Todos los vendedores" }].concat(
              vendedores.map((u) => ({ valor: String(u.id), texto: u.nombre_completo })))}
          />
        )}
        <CampoSeleccion
          id="medio"
          etiqueta="Medio de pago"
          valor={filtros.medio_pago}
          onChange={(valor) => cambiarFiltro("medio_pago", valor)}
          opciones={[{ valor: SIN_FILTRO, texto: "Todos los medios" }].concat(
            medios.map((m) => ({ valor: String(m.id), texto: m.nombre })))}
        />
        <Campo
          id="desde"
          etiqueta="Desde"
          tipo="date"
          requerido={false}
          valor={filtros.desde}
          onChange={(valor) => cambiarFiltro("desde", valor)}
        />
        <Campo
          id="hasta"
          etiqueta="Hasta"
          tipo="date"
          requerido={false}
          valor={filtros.hasta}
          onChange={(valor) => cambiarFiltro("hasta", valor)}
        />
      </div>

      {cifras && (
        <div className="kpis">
          <div className="kpi">
            <div className="k">Ventas del período</div>
            <div className="v">{moneda(Number(cifras.vendido))}</div>
            <div className="d">{plural(cifras.transacciones, "transacción", "transacciones")}</div>
          </div>
          <div className="kpi">
            <div className="k">Anuladas</div>
            <div className="v">{cifras.anuladas}</div>
            <div className="d">
              {moneda(Number(cifras.valor_anulado))} de vuelta en el inventario
            </div>
          </div>
          <div className="kpi">
            <div className="k">Venta promedio</div>
            <div className="v">{moneda(Number(cifras.promedio))}</div>
            <div className="d">en el período</div>
          </div>
        </div>
      )}

      <div className="tarjeta">
        {/*
          El control de paginas va arriba y abajo. Con veinticinco filas, el de
          abajo queda fuera de la pantalla, de modo que pasar de pagina costaba
          bajar primero.
        */}
        <Paginacion total={cuantas} pagina={pagina} nombre="ventas"
                    onCambiar={(numero) => { setAviso(null); setPagina(numero); }} />

        {cargando ? (
          <div className="vacio">Cargando…</div>
        ) : ventas.length === 0 ? (
          <div className="vacio">Ninguna venta coincide con lo que buscas.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Venta</th><th>Fecha</th><th>Vendedor</th><th>Medio</th>
                <th>Total</th><th>Estado</th><th></th>
              </tr>
            </thead>
            <tbody>
              {ventas.map((venta) => (
                <tr key={venta.id}>
                  <td>
                    #{venta.consecutivo}
                    {venta.observacion && <div className="hs">{venta.observacion}</div>}
                  </td>
                  <td>{fechaHora(venta.fecha)}</td>
                  <td>{venta.vendedor}</td>
                  <td>{venta.medio_pago_nombre}</td>
                  <td>{moneda(Number(venta.total))}</td>
                  <td>
                    {venta.estado === "anulada" ? (
                      <>
                        <span className="estado inactivo">Anulada</span>
                        <div className="hs">
                          {venta.motivo_anulacion}
                          {venta.anulada_por_nombre && ` · ${venta.anulada_por_nombre}`}
                        </div>
                      </>
                    ) : (
                      <span className="estado activo">Activa</span>
                    )}
                  </td>
                  <td className="acciones-fila">
                    <button className="btn btn-out btn-pequeno" type="button"
                            onClick={() => abrir(venta)}>
                      Ver
                    </button>
                    {venta.se_puede_anular && esAdministrador && (
                      <button
                        className="btn btn-out btn-pequeno"
                        type="button"
                        title={impedimento ? impedimento.texto : undefined}
                        disabled={impedimento !== null}
                        onClick={() => { setAviso(null); setMotivoDeAnulacion("");
                                         setPorAnular(venta); }}
                      >
                        Anular
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <Paginacion total={cuantas} pagina={pagina} nombre="ventas"
                    onCambiar={(numero) => { setAviso(null); setPagina(numero); }} />
      </div>

      {abierta && (
        <Comprobante venta={abierta} enVentana onCerrar={() => setAbierta(null)} />
      )}

      {porAnular && (
        <Modal
          titulo={`Anular la venta #${porAnular.consecutivo}`}
          mensaje={`Las unidades vuelven al inventario, cada una al lote del que salió. `
                 + `La venta no se borra: queda marcada como anulada, con su motivo y con `
                 + `quien la anuló.`}
          textoConfirmar="Anular venta"
          ocupado={ocupado}
          onConfirmar={confirmarAnulacion}
          onCancelar={() => setPorAnular(null)}
        >
          <Campo
            id="motivo"
            etiqueta="Motivo de la anulación"
            valor={motivoDeAnulacion}
            onChange={setMotivoDeAnulacion}
            marcador="El cliente devolvió la mercancía"
          />
        </Modal>
      )}
    </Disposicion>
  );
}
