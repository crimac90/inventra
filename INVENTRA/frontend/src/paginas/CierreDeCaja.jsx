/*
  Cierre de caja (RF-VEN-06), apartado 8.9 del documento de diseno.

  Compara lo que dice el sistema con lo que hay en el cajon. A la izquierda,
  lo vendido repartido por medio de pago; a la derecha, el efectivo contado y
  la diferencia que resulta.

  Solo se compara el efectivo. La transferencia y la tarjeta no pasan por el
  cajon, de modo que contarlas no diria nada: su control esta en el extracto.

  La jornada no es el dia del calendario y la pantalla lo dice en su cabecera,
  porque es la pregunta que se hace quien cierra a las dos de la madrugada. La
  jornada se la dice el servidor: aqui no se calcula ninguna fecha.

  SE PUEDE ABRIR UNA JORNADA ANTERIOR, y es por donde se llega desde el aviso
  del panel a una caja que cerro descuadrada hace dias. Una jornada cerrada no
  se vuelve a contar —el cajon ya se vacio—, de modo que alli lo unico que se
  puede escribir es la explicacion.

  Cerrar no bloquea nada ni se hace una sola vez. Mientras la jornada siga
  abierta el cierre se rehace —se actualiza el mismo registro, con los totales
  recalculados desde la primera venta—, que es la salida para quien conto
  antes de tiempo. Por eso el boton cambia de texto cuando ya hay cierre: decir
  «Cerrar el dia» sobre una caja cerrada haria temer un segundo cierre.

  La explicacion de la diferencia se escribe al cerrar o mas tarde, y despues
  solo la cambia quien administra. Es una nota y no una cifra: no mueve ningun
  total. Quien cierra suele ser quien vende, y si bastara con escribir
  cualquier cosa para apagar el aviso del panel, el faltante no llegaria nunca
  a quien tiene que juzgarlo.
*/

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import ApartadosDeVentas from "../componentes/ApartadosDeVentas";
import Campo from "../componentes/Campo";
import Disposicion from "../componentes/Disposicion";

import { mensajeDeError } from "../api/cliente";
import { consultarMiSuscripcion } from "../api/suscripciones";
import { cerrarJornada, consultarCierre, explicarDiferencia } from "../api/ventas";

import { useAviso } from "../aviso";
import { fecha, moneda } from "../formato";
import { motivoParaNoRegistrar } from "../sesion/permisos";
import { useSesion } from "../sesion/ContextoSesion";
import { plural } from "../texto";

export default function CierreDeCaja() {
  const { usuario: yo } = useSesion();
  const esAdministrador = yo.rol === "administrador_licorera";

  const [parametros] = useSearchParams();
  const pedida = parametros.get("jornada");

  const [jornada, setJornada] = useState(null);
  const [contado, setContado] = useState("");
  const [observacion, setObservacion] = useState("");
  const [suscripcion, setSuscripcion] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [ocupado, setOcupado] = useState(false);
  const [aviso, setAviso] = useAviso();

  const impedimento = motivoParaNoRegistrar(yo, suscripcion, "cerrar la caja",
                                            { soloAdministrador: false });
  const puedeCerrar = impedimento === null;

  const traer = useCallback(async () => {
    const datos = await consultarCierre(pedida);
    setJornada(datos);
    /*
      Lo ya contado vuelve al campo. Quien abre la pantalla sobre una caja
      cerrada tiene que ver con que cifra se cerro: un campo en blanco sobre
      un cierre hecho parece que no se hubiera guardado.
    */
    if (datos.cierre) {
      setContado(String(datos.cierre.efectivo_contado));
      setObservacion(datos.cierre.observacion || "");
    }
    return datos;
  }, [pedida]);

  useEffect(() => {
    let vigente = true;

    consultarMiSuscripcion().then((datos) => vigente && setSuscripcion(datos)).catch(() => {});

    traer()
      .catch((error) => {
        if (vigente) setAviso({ tipo: "err", texto: mensajeDeError(error) });
      })
      .finally(() => { if (vigente) setCargando(false); });

    return () => { vigente = false; };
  }, [traer, setAviso]);

  const cerrado = jornada && jornada.cierre;
  const enCurso = jornada ? jornada.en_curso !== false : true;
  const efectivo = jornada ? Number(jornada.total_efectivo) : 0;
  const vendido = jornada
    ? Number(jornada.total_efectivo) + Number(jornada.total_transferencia)
      + Number(jornada.total_tarjeta)
    : 0;

  // La diferencia se calcula mientras se escribe, antes de guardar nada: es
  // justo el numero por el que se abre esta pantalla.
  const escrito = contado === "" ? null : Number(contado);
  const diferencia = escrito === null || Number.isNaN(escrito) ? null : escrito - efectivo;

  const guardar = useCallback(async () => {
    setOcupado(true);
    setAviso(null);
    try {
      await cerrarJornada({ efectivoContado: contado, observacion });
      await traer();
      setAviso({ tipo: "ok", texto: "La jornada quedó cerrada." });
    } catch (error) {
      setAviso({ tipo: "err", texto: mensajeDeError(error) });
    } finally {
      setOcupado(false);
    }
  }, [contado, observacion, traer, setAviso]);

  const guardarExplicacion = useCallback(async () => {
    setOcupado(true);
    setAviso(null);
    try {
      await explicarDiferencia(jornada.cierre.id, observacion);
      await traer();
      setAviso({ tipo: "ok", texto: "Explicación guardada." });
    } catch (error) {
      setAviso({ tipo: "err", texto: mensajeDeError(error) });
    } finally {
      setOcupado(false);
    }
  }, [jornada, observacion, traer, setAviso]);

  return (
    <Disposicion titulo="Cierre de caja">
      <ApartadosDeVentas />

      {cargando || !jornada ? (
        <div className="vacio">Cargando…</div>
      ) : (
        <>
          <div className="cabecera-jornada">
            <div>
              <h1>Jornada del {fecha(jornada.jornada)}</h1>
              <p className="hs">
                De las 06:00 de ese día a las 06:00 del siguiente ·{" "}
                {plural(jornada.transacciones, "transacción", "transacciones")} en esta sede.
              </p>
            </div>
            <div className="total-jornada">
              <div className="k">Total vendido</div>
              <b>{moneda(vendido)}</b>
            </div>
          </div>

          {aviso && <div className={`aviso ${aviso.tipo}`} role="status">{aviso.texto}</div>}

          <div className="rejilla-dos">
            <div className="tarjeta">
              <h2>Lo que dice el sistema</h2>
              <div className="tot"><span>Efectivo</span><b>{moneda(efectivo)}</b></div>
              <div className="tot">
                <span>Transferencia</span><b>{moneda(Number(jornada.total_transferencia))}</b>
              </div>
              <div className="tot">
                <span>Tarjeta</span><b>{moneda(Number(jornada.total_tarjeta))}</b>
              </div>
              <div className="tot total"><span>Total</span><span>{moneda(vendido)}</span></div>
            </div>

            <div className="tarjeta">
              <h2>Lo que hay en la caja</h2>
              <p className="hs">
                {enCurso
                  ? "Cuenta el efectivo y escríbelo. Solo se compara el efectivo: lo demás no pasa por el cajón."
                  : "Esta jornada ya terminó y su cajón se vació: no se vuelve a contar. Lo que sí se puede escribir es la explicación de la diferencia."}
              </p>

              {enCurso ? (
                <Campo
                  id="contado"
                  etiqueta="Efectivo contado"
                  tipo="number"
                  minimo={0}
                  valor={contado}
                  onChange={setContado}
                  marcador={String(efectivo)}
                />
              ) : (
                <div className="tot">
                  <span>Efectivo contado</span>
                  <b>{contado === "" ? "—" : moneda(Number(contado))}</b>
                </div>
              )}

              {diferencia !== null && (
                diferencia === 0 ? (
                  <div className="aviso ok" role="status">La caja cuadra.</div>
                ) : (
                  <div className="aviso advertencia" role="status">
                    {diferencia < 0
                      ? `Faltan ${moneda(-diferencia)} frente a lo que dice el sistema.`
                      : `Sobran ${moneda(diferencia)} frente a lo que dice el sistema.`}
                  </div>
                )
              )}

              <Campo
                id="observacion"
                etiqueta="Explicación de la diferencia"
                requerido={false}
                valor={observacion}
                onChange={setObservacion}
                marcador="Se pagó un domicilio con efectivo de la caja"
                ayuda={cerrado && !esAdministrador
                  ? "La jornada ya está cerrada: la explicación la corrige quien administra."
                  : undefined}
              />

              <div className="acciones">
                {cerrado && esAdministrador && (
                  <button className="btn btn-out" type="button" disabled={ocupado}
                          onClick={guardarExplicacion}>
                    Guardar la explicación
                  </button>
                )}
                {/*
                  Contar el cajón solo tiene sentido mientras la jornada siga
                  abierta. En una anterior el cajón ya se vació, de modo que el
                  botón no se apaga: no está.
                */}
                {enCurso && (
                  <button
                    className="btn btn-cta"
                    type="button"
                    title={impedimento ? impedimento.texto : undefined}
                    disabled={ocupado || !puedeCerrar || contado === ""}
                    onClick={guardar}
                  >
                    {ocupado ? "Guardando…" : cerrado ? "Rehacer el cierre" : "Cerrar el día"}
                  </button>
                )}
              </div>
            </div>
          </div>

          {cerrado && (
            <p className="hs">
              Cerrada por {jornada.cierre.usuario_nombre}. Mientras la jornada siga
              abierta el cierre se puede rehacer: los totales se recalculan enteros,
              desde la primera venta.
            </p>
          )}
        </>
      )}
    </Disposicion>
  );
}
