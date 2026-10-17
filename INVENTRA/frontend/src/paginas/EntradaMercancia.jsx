/*
  Entrada de mercancia (RF-INV-05), apartado 8.5 del documento de diseno.

  Es el unico formulario del sistema con varias lineas, y por eso no se parece
  a los demas. Una compra llega con lo que diga la factura del proveedor: tres
  referencias o catorce, cada una con su cantidad y su costo. Registrarlas de
  una en una obligaria a repetir el proveedor y la fecha otras tantas veces y,
  peor, partiria en catorce entradas lo que fue una sola compra.

  El costo se pide aqui y no en el formulario de producto. El mismo aguardiente
  no cuesta lo mismo en marzo que en agosto, de modo que el costo no es del
  producto sino de cada lote que entra, y cada linea de esta pantalla nace como
  un lote con el suyo congelado.

  La lista de abajo no tiene editar ni borrar. Una entrada ya registrada movio
  existencias y dejo su rastro en el kardex; lo que corrige una entrada
  equivocada es un ajuste con su motivo (RF-INV-06).
*/

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import Campo from "../componentes/Campo";
import Disposicion from "../componentes/Disposicion";
import SelectorDeProducto from "../componentes/SelectorDeProducto";
import { ErrorApi, mensajeDeError } from "../api/cliente";
import { listarEntradas, registrarEntrada } from "../api/inventario";
import { consultarMiSuscripcion } from "../api/suscripciones";
import { fechaHora, moneda } from "../formato";
import { plural } from "../texto";
import { motivoParaNoRegistrar } from "../sesion/permisos";
import { useSesion } from "../sesion/ContextoSesion";
import { useAviso } from "../aviso";

/*
  Cada linea lleva una clave propia que no es su posicion en la lista. Con el
  indice como clave, quitar la primera linea haria que React reutilizara sus
  casillas para la segunda y lo escrito se correria hacia arriba.
*/
let siguienteClave = 1;

function lineaVacia() {
  return { clave: siguienteClave++, producto: null, cantidad: "", costo_unitario: "" };
}

export default function EntradaMercancia() {
  const { usuario: yo } = useSesion();

  const [lineas, setLineas] = useState([lineaVacia()]);
  const [proveedor, setProveedor] = useState("");
  const [observacion, setObservacion] = useState("");

  const [entradas, setEntradas] = useState([]);
  const [cargando, setCargando] = useState(true);
  const [ocupado, setOcupado] = useState(false);
  const [aviso, setAviso] = useAviso();
  const [errores, setErrores] = useState({});
  const [suscripcion, setSuscripcion] = useState(null);

  useEffect(() => {
    let vigente = true;

    consultarMiSuscripcion()
      .then((datos) => vigente && setSuscripcion(datos))
      .catch(() => {});

    listarEntradas()
      .then((datos) => vigente && setEntradas(datos.results || []))
      .catch((error) => vigente && setAviso({ tipo: "err", texto: mensajeDeError(error) }))
      .finally(() => vigente && setCargando(false));

    return () => {
      vigente = false;
    };
  }, []);

  function cambiarLinea(clave, campo, valor) {
    setLineas((previas) =>
      previas.map((l) => (l.clave === clave ? { ...l, [campo]: valor } : l)));
    setErrores((previos) => ({ ...previos, [clave]: undefined }));
  }

  function quitarLinea(clave) {
    setLineas((previas) => previas.filter((l) => l.clave !== clave));
  }

  /*
    Solo cuentan las lineas completas. Una linea a medias no suma cero: suma
    nada, y mostrarla como cero haria creer que el total esta hecho cuando
    todavia falta escribir un costo.
  */
  const completas = lineas.filter(
    (l) => l.producto && l.cantidad !== "" && l.costo_unitario !== "");

  const total = completas.reduce(
    (suma, l) => suma + Number(l.cantidad) * Number(l.costo_unitario), 0);

  const unidades = completas.reduce((suma, l) => suma + Number(l.cantidad), 0);

  async function enviar(evento) {
    evento.preventDefault();

    if (completas.length === 0) {
      setAviso({ tipo: "err", texto: "Agrega al menos una línea completa." });
      return;
    }

    setOcupado(true);
    setErrores({});
    try {
      const entrada = await registrarEntrada({
        proveedor,
        observacion,
        lineas: completas.map((l) => ({
          producto: l.producto.id,
          cantidad: Number(l.cantidad),
          costo_unitario: l.costo_unitario,
        })),
      });

      setAviso({
        tipo: "ok",
        texto: `Entrada registrada: ${plural(entrada.lotes.length, "lote", "lotes")} por ${moneda(total)}.`,
      });
      setLineas([lineaVacia()]);
      setProveedor("");
      setObservacion("");

      const datos = await listarEntradas();
      setEntradas(datos.results || []);
    } catch (error) {
      repartirError(error);
    } finally {
      setOcupado(false);
    }
  }

  /*
    El rechazo de una linea tiene que aparecer en esa linea y no arriba del
    todo: con catorce referencias en pantalla, «la cantidad debe ser mayor que
    cero» sin decir cual obliga a revisarlas todas. El servidor manda los
    errores de las lineas en una lista alineada por posicion, y aqui se traduce
    esa posicion a la clave de la linea que la ocupa.
  */
  function repartirError(error) {
    if (!(error instanceof ErrorApi) || error.codigo !== 400) {
      setAviso({ tipo: "err", texto: mensajeDeError(error) });
      return;
    }

    const porLinea = {};
    const crudos = error.datos && error.datos.lineas;

    if (Array.isArray(crudos)) {
      crudos.forEach((fallo, posicion) => {
        const linea = completas[posicion];
        if (!linea || !fallo) return;
        const textos = typeof fallo === "string"
          ? [fallo]
          : Object.values(fallo).flat();
        if (textos.length > 0) porLinea[linea.clave] = textos.join(" ");
      });
    }

    setErrores(porLinea);
    setAviso({
      tipo: "err",
      texto: Object.keys(porLinea).length > 0
        ? "Revisa las líneas marcadas."
        : mensajeDeError(error),
    });
  }

  const motivo = motivoParaNoRegistrar(yo, suscripcion, "registrar entradas de mercancía");
  const puedeRegistrar = motivo === null;

  return (
    <Disposicion titulo="Entrada de mercancía">
      <div className="barra-herramientas">
        <div>
          <Link className="volver" to="/inventario">← Volver al inventario</Link>
          <h1>Entrada de mercancía</h1>
          <div className="hs" style={{ margin: "6px 0 0" }}>
            Cada línea entra como un lote con su propio costo.
          </div>
        </div>
      </div>

      {motivo && motivo.avisar && (
        <div className="aviso err" role="status">
          {motivo.texto}{" "}
          {motivo.enlace && <Link to={motivo.enlace.a}>{motivo.enlace.etiqueta}</Link>}
        </div>
      )}

      {aviso && (
        <div
          className={`aviso ${aviso.tipo}`}
          role={aviso.tipo === "err" ? "alert" : "status"}
        >
          {aviso.texto}
        </div>
      )}

      {puedeRegistrar && (
        <form className="tarjeta" onSubmit={enviar} noValidate>
          <h2>Nueva entrada</h2>
          <div className="hs">Registra la mercancía que acaba de llegar.</div>

          <div className="rejilla-dos">
            <Campo
              id="proveedor"
              etiqueta="Proveedor"
              marcador="Distribuidora La 70"
              requerido={false}
              valor={proveedor}
              onChange={setProveedor}
            />
            <Campo
              id="observacion"
              etiqueta="Observación"
              marcador="Factura 4521"
              requerido={false}
              valor={observacion}
              onChange={setObservacion}
            />
          </div>

          <h3 className="subtitulo">Productos recibidos</h3>

          {lineas.map((linea, posicion) => (
            <div className="linea" key={linea.clave}>
              <SelectorDeProducto
                id={`producto-${linea.clave}`}
                valor={linea.producto}
                excluir={lineas
                  .filter((otra) => otra.clave !== linea.clave && otra.producto)
                  .map((otra) => otra.producto.id)}
                onElegir={(producto) => cambiarLinea(linea.clave, "producto", producto)}
                error={errores[linea.clave]}
              />

              <Campo
                id={`cantidad-${linea.clave}`}
                etiqueta="Cantidad"
                tipo="number"
                marcador="24"
                minimo="1"
                requerido={false}
                valor={linea.cantidad}
                onChange={(v) => cambiarLinea(linea.clave, "cantidad", v)}
              />

              <Campo
                id={`costo-${linea.clave}`}
                etiqueta="Costo unitario"
                tipo="number"
                marcador="0"
                minimo="0"
                requerido={false}
                valor={linea.costo_unitario}
                onChange={(v) => cambiarLinea(linea.clave, "costo_unitario", v)}
              />

              <div className="subtotal">
                <span className="hs">Subtotal</span>
                <strong>
                  {linea.cantidad && linea.costo_unitario
                    ? moneda(Number(linea.cantidad) * Number(linea.costo_unitario))
                    : "—"}
                </strong>
              </div>

              {/* La unica linea no se puede quitar: un formulario sin ninguna
                  obliga a pulsar «Agregar» para volver al punto de partida. */}
              <button
                className="btn btn-out btn-pequeno quitar"
                type="button"
                onClick={() => quitarLinea(linea.clave)}
                disabled={lineas.length === 1}
                aria-label={`Quitar la línea ${posicion + 1}`}
              >
                Quitar
              </button>
            </div>
          ))}

          <button
            className="btn btn-out"
            type="button"
            onClick={() => setLineas((previas) => [...previas, lineaVacia()])}
          >
            Agregar otra línea
          </button>

          <div className="resumen">
            <span>
              {plural(completas.length, "línea completa", "líneas completas")} ·{" "}
              {plural(unidades, "unidad", "unidades")}
            </span>
            <strong>Total de la compra: {moneda(total)}</strong>
          </div>

          <div className="acciones">
            <button className="btn btn-cta" type="submit" disabled={ocupado}>
              {ocupado ? "Registrando…" : "Registrar entrada"}
            </button>
          </div>
        </form>
      )}

      <h2 className="subtitulo">Entradas registradas</h2>

      <div className="tabla-caja">
        {cargando ? (
          <div className="vacio">Cargando…</div>
        ) : entradas.length === 0 ? (
          <div className="vacio">Todavía no se ha registrado ninguna entrada.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Proveedor</th>
                <th>Productos</th>
                <th>Registró</th>
                <th>Costo total</th>
              </tr>
            </thead>
            <tbody>
              {entradas.map((entrada) => (
                <tr key={entrada.id}>
                  <td>{fechaHora(entrada.fecha)}</td>
                  <td>
                    {entrada.proveedor || "—"}
                    {entrada.observacion && (
                      <div className="hs" style={{ fontSize: 12 }}>{entrada.observacion}</div>
                    )}
                  </td>
                  <td>
                    {entrada.lotes.map((lote) => (
                      <div key={lote.id}>
                        {lote.producto_nombre}
                        <span className="hs"> × {lote.cantidad_inicial}</span>
                      </div>
                    ))}
                  </td>
                  <td>{entrada.usuario_nombre}</td>
                  <td>
                    {moneda(entrada.lotes.reduce(
                      (suma, lote) => suma + lote.cantidad_inicial * Number(lote.costo_unitario),
                      0))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </Disposicion>
  );
}
