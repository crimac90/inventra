/*
  Kardex de una referencia y ajuste de sus existencias (RF-INV-09 y RF-INV-06),
  apartado 8.6 del documento de diseno.

  El ajuste vive en esta pantalla y no en la lista de productos. Un ajuste es
  la respuesta a una diferencia, y la diferencia se ve en el historial: faltan
  tres botellas que nadie vendio, o aparecen dos que nadie registro. Desde la
  lista se escribiria a ciegas, mirando una cifra de existencias sin nada que
  la explique; aqui, quien lo escribe acaba de leer los movimientos que no
  cuadran, y el movimiento que genera aparece arriba al guardar.

  El kardex no se edita, tampoco para el administrador. Un historial que se
  puede reescribir no sirve para rendir cuentas: una cifra equivocada se
  corrige con otro movimiento que diga por que, no borrando el anterior.
*/

import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import Campo from "../componentes/Campo";
import Disposicion from "../componentes/Disposicion";
import { ErrorApi, mensajeDeError } from "../api/cliente";
import {
  ajustarExistencias,
  consultarKardex,
  consultarProducto,
} from "../api/inventario";
import { consultarMiSuscripcion } from "../api/suscripciones";
import { fechaHora, moneda } from "../formato";
import { plural } from "../texto";
import { motivoParaNoRegistrar } from "../sesion/permisos";
import { useSesion } from "../sesion/ContextoSesion";
import { useAviso } from "../aviso";

export default function Kardex() {
  const { id } = useParams();
  const { usuario: yo } = useSesion();

  const [producto, setProducto] = useState(null);
  const [movimientos, setMovimientos] = useState([]);
  const [hayMas, setHayMas] = useState(false);
  const [pagina, setPagina] = useState(1);
  const [total, setTotal] = useState(0);

  const [cargando, setCargando] = useState(true);
  const [ocupado, setOcupado] = useState(false);
  const [aviso, setAviso] = useAviso();
  const [errores, setErrores] = useState({});
  const [suscripcion, setSuscripcion] = useState(null);

  const [cantidad, setCantidad] = useState("");
  const [motivoDelAjuste, setMotivoDelAjuste] = useState("");

  /*
    Vuelve a la primera pagina en vez de recargar la que se este mirando. Es
    deliberado: despues de un ajuste, el movimiento que interesa es el que
    acaba de nacer, y ese esta siempre arriba porque el kardex se lee del mas
    reciente al mas antiguo.
  */
  const refrescar = useCallback(async () => {
    const datos = await consultarKardex(id);
    setMovimientos(datos.results || []);
    setHayMas(Boolean(datos.next));
    setTotal(datos.count || 0);
    setPagina(1);
  }, [id]);

  useEffect(() => {
    let vigente = true;

    consultarMiSuscripcion()
      .then((datos) => vigente && setSuscripcion(datos))
      .catch(() => {});

    Promise.all([consultarProducto(id), consultarKardex(id)])
      .then(([referencia, kardex]) => {
        if (!vigente) return;
        setProducto(referencia);
        setMovimientos(kardex.results || []);
        setHayMas(Boolean(kardex.next));
        setTotal(kardex.count || 0);
      })
      .catch((error) => vigente && setAviso({ tipo: "err", texto: mensajeDeError(error) }))
      .finally(() => vigente && setCargando(false));

    return () => {
      vigente = false;
    };
  }, [id]);

  async function verMas() {
    setOcupado(true);
    try {
      const siguiente = pagina + 1;
      const datos = await consultarKardex(id, siguiente);
      // Se agregan al final y no reemplazan: lo ya leido sigue en pantalla,
      // que es como se recorre un historial hacia atras.
      setMovimientos((previos) => [...previos, ...(datos.results || [])]);
      setHayMas(Boolean(datos.next));
      setPagina(siguiente);
    } catch (error) {
      setAviso({ tipo: "err", texto: mensajeDeError(error) });
    } finally {
      setOcupado(false);
    }
  }

  async function ajustar(evento) {
    evento.preventDefault();

    /*
      La casilla vacia no se manda. Convertida a numero daria CERO, y el
      servidor respondia a ese cero con toda la razon: «el ajuste no cambia
      nada, la diferencia es cero», que es cierto para el dato que recibio y
      no para lo que hizo la persona, que fue no escribir nada.
    */
    if (cantidad.trim() === "") {
      setErrores({ cantidad: "Escribe la diferencia." });
      setAviso({ tipo: "err", texto: "Revisa los datos marcados." });
      return;
    }

    setOcupado(true);
    setErrores({});
    try {
      // La respuesta trae el producto con sus existencias ya recalculadas, de
      // modo que no hace falta volver a pedirlo.
      const actualizado = await ajustarExistencias(id, {
        cantidad: Number(cantidad),
        motivo: motivoDelAjuste,
      });
      setProducto(actualizado);
      setAviso({ tipo: "ok", texto: "Ajuste registrado." });
      setCantidad("");
      setMotivoDelAjuste("");
      await refrescar();
    } catch (error) {
      if (error instanceof ErrorApi && error.codigo === 400) {
        /*
          Un rechazo campo por campo no trae mensaje general, de modo que
          pedirselo devolvia el texto de ultimo recurso —«el servidor respondio
          algo que no se pudo interpretar»— encima de unos errores que se
          entendian perfectamente. Es el mismo texto que usa el catalogo.
        */
        setErrores(error.porCampo);
        setAviso({ tipo: "err", texto: "Revisa los datos marcados." });
      } else {
        setAviso({ tipo: "err", texto: mensajeDeError(error) });
      }
    } finally {
      setOcupado(false);
    }
  }

  const motivo = motivoParaNoRegistrar(yo, suscripcion, "ajustar existencias");
  const puedeAjustar = motivo === null;

  return (
    <Disposicion titulo="Kardex">
      <div className="barra-herramientas">
        <div>
          <Link className="volver" to="/inventario">← Volver al inventario</Link>
          <h1>{producto ? producto.nombre : "Kardex"}</h1>
          <div className="hs" style={{ margin: "6px 0 0" }}>
            {cargando
              ? "Cargando…"
              : `${plural(total, "movimiento registrado", "movimientos registrados")}.`}
          </div>
        </div>

        {producto && (
          <div className="existencias-ahora">
            <span className="hs">Existencias</span>
            <strong>{producto.existencias}</strong>
          </div>
        )}
      </div>

      {aviso && (
        <div
          className={`aviso ${aviso.tipo}`}
          role={aviso.tipo === "err" ? "alert" : "status"}
        >
          {aviso.texto}
        </div>
      )}

      {!cargando && motivo && motivo.avisar && (
        <div className="aviso err" role="status">
          {motivo.texto}{" "}
          {motivo.enlace && <Link to={motivo.enlace.a}>{motivo.enlace.etiqueta}</Link>}
        </div>
      )}

      {!cargando && puedeAjustar && producto && (
        <form className="tarjeta" onSubmit={ajustar} noValidate>
          <h2>Ajustar existencias</h2>
          <div className="hs">
            Escribe la diferencia, no la cantidad final: 3 si sobraron tres unidades
            en el conteo, −3 si faltaron.
          </div>

          <div className="rejilla-dos">
            <Campo
              id="cantidad"
              etiqueta="Diferencia"
              tipo="number"
              marcador="-2"
              valor={cantidad}
              onChange={setCantidad}
              error={errores.cantidad}
            />
            <Campo
              id="motivo"
              etiqueta="Motivo"
              marcador="Dos botellas rotas en bodega"
              valor={motivoDelAjuste}
              onChange={setMotivoDelAjuste}
              error={errores.motivo}
            />
          </div>

          <div className="acciones">
            <button className="btn btn-cta" type="submit" disabled={ocupado}>
              {ocupado ? "Registrando…" : "Registrar ajuste"}
            </button>
          </div>
        </form>
      )}

      <h2 className="subtitulo">Movimientos</h2>

      <div className="tabla-caja">
        {cargando ? (
          <div className="vacio">Cargando…</div>
        ) : movimientos.length === 0 ? (
          <div className="vacio">
            Esta referencia todavía no tiene movimientos. Registra una entrada de
            mercancía para empezar su historial.
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Movimiento</th>
                <th>Cantidad</th>
                <th>Costo unitario</th>
                <th>Saldo</th>
                <th>Registró</th>
              </tr>
            </thead>
            <tbody>
              {movimientos.map((movimiento) => (
                <tr key={movimiento.id}>
                  <td>{fechaHora(movimiento.fecha)}</td>
                  <td>
                    {movimiento.tipo_nombre}
                    {/*
                      Solo se cita el documento de la entrada. El ajuste no
                      tiene documento propio —el movimiento ES el documento— y
                      su identificador es el del producto, de modo que
                      escribirlo aqui pondria un numero que no lleva a ninguna
                      parte.
                    */}
                    {movimiento.documento_tipo === "entrada" && (
                      <span className="hs"> · Entrada #{movimiento.documento_id}</span>
                    )}
                    {movimiento.motivo && (
                      <div className="hs" style={{ fontSize: 12 }}>{movimiento.motivo}</div>
                    )}
                  </td>
                  <td className={movimiento.cantidad < 0 ? "cifra menos" : "cifra mas"}>
                    {movimiento.cantidad > 0 ? `+${movimiento.cantidad}` : movimiento.cantidad}
                  </td>
                  <td>{moneda(movimiento.costo_unitario)}</td>
                  <td className="cifra">{movimiento.saldo_resultante}</td>
                  <td>{movimiento.usuario_nombre || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {hayMas && (
        <div className="acciones">
          <button className="btn btn-out" type="button" onClick={verMas} disabled={ocupado}>
            {ocupado ? "Cargando…" : "Ver movimientos anteriores"}
          </button>
        </div>
      )}
    </Disposicion>
  );
}
