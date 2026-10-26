/*
  Punto de venta (RF-VEN-01 a 03), apartado 8.7 del documento de diseno.

  Es la pantalla que mas se usa del sistema y la unica que se juzga por lo
  rapida que es. Todo lo que hay aqui esta decidido por esa frase: se busca
  escribiendo y se elige con el teclado, elegir es agregar, la cantidad se
  escribe o se ajusta sin abrir nada, y el boton de cobrar lleva el importe
  para que nadie mire dos sitios antes de pulsar.

  El precio no se manda: se mandan producto y cantidad, y a cuanto se vende
  lo dice el catalogo en el servidor. Es la unica forma de que quien tiene la
  pantalla delante no pueda cobrar lo que quiera.

  Vender es del vendedor, de modo que esta pantalla invierte el reparto del
  resto del sistema: al preguntar si esta cuenta puede registrar se dice
  expresamente que la accion no es solo del administrador.

  Lo que no cabe no se agrega: el tope de cada linea son las existencias que
  trae el catalogo. No sustituye al servidor —otra caja puede haber vendido
  mientras tanto, y alli es donde la regla de verdad se cumple—, pero evita el
  caso que de verdad duele: armar una factura larga y descubrir al cobrar que
  de la tercera referencia no habia suficiente.
*/

import { useCallback, useEffect, useMemo, useState } from "react";

import ApartadosDeVentas from "../componentes/ApartadosDeVentas";
import Campo from "../componentes/Campo";
import Comprobante from "../componentes/Comprobante";
import Disposicion from "../componentes/Disposicion";
import SelectorDeProducto from "../componentes/SelectorDeProducto";
import { ErrorApi, mensajeDeError } from "../api/cliente";
import { cobrar, consultarMediosDePago } from "../api/ventas";
import { consultarMiSuscripcion } from "../api/suscripciones";
import { moneda } from "../formato";
import { pierdeDinero } from "../precios";
import { plural } from "../texto";
import { motivoParaNoRegistrar } from "../sesion/permisos";
import { useSesion } from "../sesion/ContextoSesion";
import { useAviso } from "../aviso";
import { guardarVenta, leerVenta, olvidarVenta } from "../venta_en_curso";

const EFECTIVO = "efectivo";

export default function PuntoDeVenta() {
  const { usuario: yo } = useSesion();

  const [medios, setMedios] = useState([]);
  const [medio, setMedio] = useState(null);
  // La venta a medio hacer se recupera del navegador: salir a mirar el
  // inventario no puede costar diez referencias ya preguntadas al cliente.
  const [lineas, setLineas] = useState(() => leerVenta(yo));
  const [recibido, setRecibido] = useState("");
  // La nota con la que el negocio reconoce una venta de mesa.
  const [nota, setNota] = useState("");
  const [suscripcion, setSuscripcion] = useState(null);
  const [comprobante, setComprobante] = useState(null);
  const [aviso, setAviso] = useAviso();
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => { guardarVenta(yo, lineas); }, [yo, lineas]);

  useEffect(() => {
    consultarMediosDePago()
      .then((datos) => {
        setMedios(datos);
        setMedio(datos.find((m) => m.nombre === EFECTIVO) || datos[0] || null);
      })
      .catch(() => setAviso({ tipo: "err", texto: "No se pudieron cargar los medios de pago." }));

    consultarMiSuscripcion().then(setSuscripcion).catch(() => setSuscripcion(null));
  }, [setAviso]);

  const motivo = motivoParaNoRegistrar(yo, suscripcion, "registrar ventas",
                                       { soloAdministrador: false });
  const puedeVender = motivo === null;

  const total = useMemo(
    () => lineas.reduce((suma, l) => suma + l.precio * l.cantidad, 0),
    [lineas]);

  const enEfectivo = medio !== null && medio.nombre === EFECTIVO;
  const entregado = recibido === "" ? null : Number(recibido);
  const cambio = entregado === null || Number.isNaN(entregado) ? null : entregado - total;

  /*
    Con efectivo no se cobra a ciegas: hasta que no se escribe cuanto entrego el
    cliente, el boton esta apagado. Dejarlo encendido con el campo vacio haria
    inutil apagarlo cuando el dinero no alcanza, porque bastaria no escribir
    nada. Para el pago exacto esta el boton «Justo», que es un clic.
  */
  const faltaContarElDinero = enEfectivo && (cambio === null || cambio < 0);

  // Al tocar el carrito se retira el aviso anterior: puede estar hablando de
  // una linea que ya no existe.
  const limpiar = useCallback(() => setAviso(null), [setAviso]);

  const agregar = useCallback((producto) => {
    if (!producto) return;
    limpiar();
    setComprobante(null);

    /*
      Las dos razones por las que una referencia no se puede vender ahora mismo
      se responden igual: se deja elegir, no se agrega y la pantalla dice por
      que. Son el mismo caso para quien atiende —«esto no se puede vender»— y
      darles dos comportamientos obligaria a aprenderse cual es cual.
    */
    if (producto.tiene_precio === false || !(Number(producto.precio_venta) > 0)) {
      setAviso({
        tipo: "err",
        texto: `«${producto.nombre}» todavía no tiene precio de venta: `
             + "se le pone al registrar la entrada de mercancía.",
      });
      return;
    }

    const hay = Number(producto.existencias) || 0;
    if (hay <= 0) {
      setAviso({ tipo: "err",
                 texto: `«${producto.nombre}» está agotado: no hay unidades que vender.` });
      return;
    }

    setLineas((actuales) => {
      // Pulsar dos veces el mismo producto es «dos unidades», no dos
      // renglones. El servidor tambien lo junta, pero si la pantalla no lo
      // hiciera se verian dos lineas iguales hasta cobrar.
      const yaEsta = actuales.find((l) => l.id === producto.id);
      if (yaEsta) {
        return actuales.map((l) => (l.id === producto.id
          ? { ...l, cantidad: Math.min(l.cantidad + 1, l.hay) } : l));
      }
      return [...actuales, {
        id: producto.id,
        nombre: producto.nombre,
        precio: Number(producto.precio_venta),
        hay,
        cantidad: 1,
        // Se resuelve al agregar, con lo que el catálogo acaba de traer, y
        // no al pintar: la línea guardada en el navegador sobrevive a salir
        // de la pantalla y allí ya no hay producto del que preguntarlo.
        bajoElCosto: pierdeDinero(producto),
      }];
    });
  }, [limpiar, setAviso]);

  function ponerCantidad(id, cuanto) {
    limpiar();
    setLineas((actuales) => actuales.map((l) => {
      if (l.id !== id) return l;
      const pedida = Math.max(1, Math.min(cuanto, l.hay));
      return { ...l, cantidad: pedida };
    }));
  }

  function escribirCantidad(id, texto) {
    // Mientras se escribe se admite el campo vacio; al salir vuelve a uno.
    const numero = parseInt(texto, 10);
    if (texto === "" || Number.isNaN(numero)) return;
    ponerCantidad(id, numero);
  }

  function quitar(id) {
    limpiar();
    setLineas((actuales) => actuales.filter((l) => l.id !== id));
  }

  function vaciar() {
    limpiar();
    setLineas([]);
    setRecibido("");
    setComprobante(null);
  }

  async function cobrarVenta() {
    if (!lineas.length || !medio) return;
    setOcupado(true);
    setAviso(null);
    try {
      const venta = await cobrar({
        medioPagoId: medio.id,
        montoRecibido: enEfectivo ? recibido : null,
        observacion: nota,
        lineas: lineas.map((l) => ({ producto_id: l.id, cantidad: l.cantidad })),
      });
      setComprobante(venta);
      setLineas([]);
      olvidarVenta(yo);
      setRecibido("");
      setNota("");
      setAviso({ tipo: "ok", texto: `Venta #${venta.consecutivo} registrada.` });
    } catch (error) {
      setAviso({
        tipo: "err",
        texto: error instanceof ErrorApi
          ? mensajeDeError(error, "No se pudo registrar la venta.")
          : "No se pudo registrar la venta.",
      });
    } finally {
      setOcupado(false);
    }
  }

  return (
    <Disposicion titulo="Punto de venta">
      <ApartadosDeVentas />

      <h1>Punto de venta</h1>
      <div className="hs">
        Busca el producto, ajusta la cantidad y cobra. El precio lo pone el catálogo.
      </div>

      {aviso && (
        <div className={`aviso ${aviso.tipo}`} role="status">{aviso.texto}</div>
      )}

      {motivo && motivo.avisar && (
        <div className="aviso advertencia" role="status">{motivo.texto}</div>
      )}

      <div className="venta">
        <div className="tarjeta">
          <h2>Productos</h2>
          <SelectorDeProducto id="buscar-producto" valor={null} onElegir={agregar} />
          <div className="hs" style={{ fontSize: 13 }}>
            Escribe el nombre o el código y elige con las flechas y Enter. El producto
            se agrega con una unidad; la cantidad se ajusta en la lista.
          </div>
        </div>

        <div className="tarjeta">
          <h2>Venta actual</h2>

          {lineas.length === 0 ? (
            <div className="vacio">Todavía no has agregado nada.</div>
          ) : (
            <>
              {lineas.map((linea) => (
                <div className="renglon" key={linea.id}>
                  <div>
                    <div className="nombre">{linea.nombre}</div>
                    <div className="cantidad">
                      <button type="button"
                              onClick={() => ponerCantidad(linea.id, linea.cantidad - 1)}
                              disabled={linea.cantidad <= 1}
                              aria-label={`Quitar una unidad de ${linea.nombre}`}>−</button>
                      <input
                        type="number"
                        min="1"
                        max={linea.hay}
                        value={linea.cantidad}
                        onChange={(e) => escribirCantidad(linea.id, e.target.value)}
                        onWheel={(e) => e.currentTarget.blur()}
                        aria-label={`Unidades de ${linea.nombre}`}
                      />
                      <button type="button"
                              onClick={() => ponerCantidad(linea.id, linea.cantidad + 1)}
                              disabled={linea.cantidad >= linea.hay}
                              aria-label={`Agregar una unidad de ${linea.nombre}`}>+</button>
                      <span className="hs" style={{ fontSize: 12 }}>× {moneda(linea.precio)}</span>
                      <button type="button" className="quitar" onClick={() => quitar(linea.id)}
                              aria-label={`Quitar ${linea.nombre} de la venta`}>×</button>
                    </div>
                    {linea.cantidad >= linea.hay && (
                      <div className="tope">
                        Es todo lo que hay: {plural(linea.hay, "unidad", "unidades")}.
                      </div>
                    )}
                    {/*
                      Avisa y no impide cobrar: una liquidación o un favor a
                      un cliente son decisiones del negocio. Lo que no puede
                      pasar es que se tomen sin saberlo.
                    */}
                    {linea.bajoElCosto && (
                      <div className="tope">
                        Se está vendiendo por debajo de lo que costó.
                      </div>
                    )}
                  </div>
                  <div className="importe">{moneda(linea.precio * linea.cantidad)}</div>
                </div>
              ))}

              <div className="total">
                <span>Total</span>
                <span>{moneda(total)}</span>
              </div>

              <Campo
                id="nota"
                etiqueta="Nota"
                requerido={false}
                valor={nota}
                onChange={setNota}
                marcador="Mesa 1, pedido 3"
                ayuda="Opcional. Sale en el comprobante y el historial la encuentra."
              />

              <div className="medios">
                {medios.map((cada) => (
                  <button
                    key={cada.id}
                    type="button"
                    className={`medio ${medio && medio.id === cada.id ? "on" : ""}`}
                    onClick={() => { setMedio(cada); setRecibido(""); limpiar(); }}
                  >
                    {cada.nombre}
                  </button>
                ))}
              </div>

              {enEfectivo && (
                <>
                  <div className="recibe">
                    <Campo
                      id="recibido"
                      etiqueta="Recibe"
                      tipo="number"
                      minimo={0}
                      requerido={false}
                      valor={recibido}
                      onChange={setRecibido}
                    />
                    <button className="btn btn-out btn-pequeno" type="button"
                            onClick={() => setRecibido(String(total))}>
                      Justo
                    </button>
                  </div>
                  {cambio !== null && (
                    cambio < 0 ? (
                      <div className="aviso advertencia" role="status">
                        Faltan {moneda(-cambio)} para completar el total.
                      </div>
                    ) : (
                      <div className="cambio"><span>Cambio</span><span>{moneda(cambio)}</span></div>
                    )
                  )}
                </>
              )}

              <div className="acciones">
                <button className="btn btn-out" type="button" onClick={vaciar}
                        disabled={ocupado}>
                  Vaciar
                </button>
                <button
                  className="btn btn-cta"
                  type="button"
                  onClick={cobrarVenta}
                  disabled={ocupado || !puedeVender || !medio || faltaContarElDinero}
                >
                  {ocupado ? "Cobrando…" : `Cobrar ${moneda(total)}`}
                </button>
              </div>
            </>
          )}
        </div>
      </div>

      {comprobante && (
        <Comprobante venta={comprobante} onCerrar={() => { setComprobante(null); limpiar(); }} />
      )}
    </Disposicion>
  );
}

