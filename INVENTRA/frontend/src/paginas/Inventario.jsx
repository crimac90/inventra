/*
  Catalogo de productos (RF-INV-01 a 04), apartados 8.3 y 8.4 del documento de
  diseno.

  Sigue el patron que estreno la gestion de usuarios —la lista vive en el estado
  y se vuelve a pedir despues de cada cambio, el mismo formulario crea y edita, y
  los textos de rechazo los escribe el servidor— con dos cosas propias de esta
  pantalla:

  1. El filtrado lo hace el SERVIDOR, no el navegador. Se le pasan el texto
     buscado y los filtros y devuelve lo que corresponde. Filtrar en el navegador
     obligaria a traerse el catalogo entero, y un catalogo entero de dos mil
     referencias no cabe en una pantalla ni conviene en una peticion.
  2. Lo que se escribe en el buscador espera un momento antes de salir. Sin esa
     espera, teclear «aguardiente» dispara once peticiones y la que contesta
     ultima no tiene por que ser la del texto completo.
*/

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import Campo from "../componentes/Campo";
import CampoSeleccion from "../componentes/CampoSeleccion";
import Disposicion from "../componentes/Disposicion";
import MargenesPorCategoria from "../componentes/MargenesPorCategoria";
import Modal from "../componentes/Modal";
import { ErrorApi, mensajeDeError } from "../api/cliente";
import {
  actualizarProducto,
  consultarCategorias,
  crearProducto,
  inactivarProducto,
  listarProductos,
  reactivarProducto,
} from "../api/inventario";
import { consultarMiSuscripcion } from "../api/suscripciones";
import { useEspera } from "../espera";
import { moneda } from "../formato";
import { plural } from "../texto";
import { motivoParaNoRegistrar } from "../sesion/permisos";
import { useSesion } from "../sesion/ContextoSesion";
import { useAviso } from "../aviso";

/* Las cinco del modelo de datos. Es una lista cerrada, no texto libre. */
const PRESENTACIONES = [
  { valor: "media", texto: "Media" },
  { valor: "botella", texto: "Botella" },
  { valor: "litro", texto: "Litro" },
  { valor: "garrafa", texto: "Garrafa" },
  { valor: "unidad", texto: "Unidad" },
];

/*
  Los dos filtros preguntan cosas distintas y se combinan: el estado de la
  referencia y el nivel de sus existencias (RF-INV-02). Cada uno nombra su
  dimension en las opciones, porque dos controles que dicen «Todos» se leen
  como el mismo puesto dos veces.
*/
const ESTADOS = [
  { valor: "activo", texto: "Solo activos" },
  { valor: "inactivo", texto: "Solo descontinuados" },
  { valor: "", texto: "Todos los estados" },
];

const NIVELES = [
  { valor: "", texto: "Todos" },
  { valor: "bajo", texto: "Existencias bajas" },
  { valor: "agotado", texto: "Agotados" },
];

const FORMULARIO_VACIO = {
  nombre: "",
  categoria: "",
  presentacion: "botella",
  codigo_barras: "",
  precio_venta: "",
  stock_minimo: "",
};

/* La espera del buscador, en milisegundos. */
const ESPERA = 300;

export default function Inventario() {
  const { usuario: yo } = useSesion();

  const [productos, setProductos] = useState([]);
  const [categorias, setCategorias] = useState([]);
  const [cargando, setCargando] = useState(true);
  const [aviso, setAviso] = useAviso();
  const [ocupado, setOcupado] = useState(false);
  const [suscripcion, setSuscripcion] = useState(null);

  // Cuando vale null no hay formulario abierto. Con un objeto vacio se esta
  // creando; con un producto dentro, editandolo.
  const [editando, setEditando] = useState(null);

  // Cuando lleva un producto dentro, la ventana de confirmacion esta abierta.
  const [porDescontinuar, setPorDescontinuar] = useState(null);

  // Cuando es cierto, la ventana de margenes esta abierta (RF-INV-11).
  const [ajustandoMargenes, setAjustandoMargenes] = useState(false);

  // Lo que la persona escribe y lo que de verdad se le pide al servidor son
  // dos cosas distintas: entre una y otra hay una espera, que ahora vive en
  // `useEspera` porque el selector de producto de la entrada necesita la misma.
  const [texto, setTexto] = useState("");
  // El filtro de existencias puede venir puesto desde la direccion, porque el
  // panel enlaza aqui con las referencias por reponer ya seleccionadas. Si la
  // pantalla ignorara el parametro, ese enlace abriria el catalogo entero y
  // habria que volver a filtrar a mano lo que el panel acababa de senalar.
  const [parametros] = useSearchParams();
  const nivelInicial = parametros.get("existencias");
  const [filtros, setFiltros] = useState({
    existencias: NIVELES.some((n) => n.valor === nivelInicial) ? nivelInicial : "",
    estado: "activo",
  });
  const buscado = useEspera(texto, ESPERA);

  const primeraCarga = useRef(true);

  /*
    Los filtros que se pulsan y el texto que reposa se juntan en un solo objeto,
    que es lo que viaja. Se memoriza para que no nazca uno nuevo en cada pintado:
    de lo contrario el efecto que pide la lista se dispararia sin parar.
  */
  const consulta = useMemo(
    () => ({ ...filtros, buscar: buscado }), [filtros, buscado]);

  const refrescar = useCallback(async () => {
    const datos = await listarProductos(consulta);
    setProductos(datos.results || []);
  }, [consulta]);

  useEffect(() => {
    let vigente = true;

    /*
      La suscripcion se consulta aparte y con su propio `catch`: un fallo suyo
      no puede dejar la pantalla sin catalogo. Si no se sabe, se supone que si
      puede registrar y el servidor rechaza si no, que es donde la regla esta
      de verdad.
    */
    if (primeraCarga.current) {
      consultarMiSuscripcion()
        .then((datos) => vigente && setSuscripcion(datos))
        .catch(() => {});
      /*
        Este fallo SI se anuncia, al reves que el de la suscripcion. Sin
        suscripcion la pantalla sigue sirviendo; sin categorias no se puede
        registrar nada, y un desplegable vacio que no explica por que lo esta
        hace parecer rota una pantalla que funciona.
      */
      consultarCategorias()
        .then((datos) => vigente && setCategorias(datos))
        .catch((error) => {
          if (vigente) setAviso({ tipo: "err", texto: mensajeDeError(error) });
        });
    }

    listarProductos(consulta)
      .then((datos) => {
        if (!vigente) return;
        setProductos(datos.results || []);
      })
      .catch((error) => {
        if (vigente) setAviso({ tipo: "err", texto: mensajeDeError(error) });
      })
      .finally(() => {
        if (!vigente) return;
        setCargando(false);
        primeraCarga.current = false;
      });

    return () => {
      vigente = false;
    };
  }, [consulta]);

  /*
    Abrir o cerrar el formulario pasa siempre por aqui, y de paso retira el
    aviso anterior. Un aviso informa del resultado de la ultima accion; si
    sobrevive a la siguiente, deja de ser verdad: «Producto actualizado» seguia
    en pantalla mientras se registraba otro distinto.
  */
  function abrirFormulario(producto) {
    setAviso(null);
    setEditando(producto);
  }

  async function guardar(datos) {
    setOcupado(true);
    try {
      if (editando.id) {
        await actualizarProducto(editando.id, datos);
        setAviso({ tipo: "ok", texto: "Producto actualizado." });
      } else {
        await crearProducto(datos);
        setAviso({ tipo: "ok", texto: "Producto registrado." });
      }
      await refrescar();
      setEditando(null);
      return {};
    } catch (error) {
      if (error instanceof ErrorApi && error.codigo === 400) {
        setAviso({ tipo: "err", texto: "Revisa los datos marcados." });
        return error.porCampo;
      }
      setAviso({ tipo: "err", texto: mensajeDeError(error) });
      return {};
    } finally {
      setOcupado(false);
    }
  }

  /*
    Descontinuar se confirma antes, como inactivar una cuenta en la pantalla de
    usuarios. Es la misma clase de accion: cambia lo que el negocio puede
    vender y se dispara con un clic en una fila, donde errar de linea es facil.
  */
  async function confirmarDescontinuar() {
    const producto = porDescontinuar;
    setOcupado(true);
    try {
      await inactivarProducto(producto.id);
      setAviso({ tipo: "ok", texto: `«${producto.nombre}» quedó descontinuado.` });
      await refrescar();
    } catch (error) {
      setAviso({ tipo: "err", texto: mensajeDeError(error) });
    } finally {
      /*
        La ventana se cierra tambien cuando la operacion falla. Dejandola
        abierta para reintentar, el aviso del rechazo queda DETRAS de ella y la
        persona no ve por que no paso nada.
      */
      setPorDescontinuar(null);
      setOcupado(false);
    }
  }

  /*
    Reactivar no se confirma: devuelve la referencia al catalogo, que es lo
    contrario de una perdida, y deshacerlo cuesta un clic.
  */
  async function reactivar(producto) {
    setOcupado(true);
    try {
      await reactivarProducto(producto.id);
      setAviso({ tipo: "ok", texto: `«${producto.nombre}» vuelve al catálogo.` });
      await refrescar();
    } catch (error) {
      setAviso({ tipo: "err", texto: mensajeDeError(error) });
    } finally {
      setOcupado(false);
    }
  }

  const motivo = motivoParaNoRegistrar(yo, suscripcion, "registrar ni modificar productos");
  const puedeRegistrar = motivo === null;
  const hayFiltro = buscado || filtros.existencias || filtros.estado !== "activo";

  return (
    <Disposicion titulo="Inventario">
      <div className="barra-herramientas">
        <div>
          <h1>Inventario</h1>
          <div className="hs" style={{ margin: "6px 0 0" }}>
            {plural(productos.length, "referencia", "referencias")} en la lista.
          </div>
        </div>

        {/*
          La entrada de mercancia no se agrega a la barra lateral: ese menu es el
          mapa de los seis modulos del documento de diseno, y una pantalla de un
          modulo colada entre ellos haria leer el inventario como dos cosas. Se
          llega desde aqui, que es donde se esta cuando llega una compra.
        */}
        {!editando && !cargando && (
          <div className="acciones-cabecera">
            {/*
              El acceso a las entradas lo ve todo el mundo: alli el vendedor
              consulta las ya registradas, igual que consulta el kardex, y el
              formulario de registrar es lo unico que esa pantalla le esconde.
            */}
            <Link className="btn btn-out" to="/inventario/entradas">
              Entrada de mercancía
            </Link>
            {puedeRegistrar && (
              <button
                className="btn btn-out"
                type="button"
                onClick={() => setAjustandoMargenes(true)}
              >
                Márgenes
              </button>
            )}
            {puedeRegistrar && (
              <button
                className="btn btn-cta"
                type="button"
                onClick={() => abrirFormulario({})}
              >
                Nuevo producto
              </button>
            )}
          </div>
        )}
      </div>

      {!cargando && motivo && motivo.avisar && (
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

      {/*
        La `key` no es decorativa: ata el formulario al producto que edita. Sin
        ella, pulsar «Editar» en otra fila con el formulario abierto cambia el
        destino del guardado y NO lo que se ve, porque React reutiliza el mismo
        formulario y su estado interno se copio del producto anterior. El
        resultado era guardar los datos de una referencia encima de otra.
      */}
      {editando && (
        <Formulario
          key={editando.id || "nuevo"}
          inicial={editando}
          categorias={categorias}
          ocupado={ocupado}
          onGuardar={guardar}
          onCancelar={() => abrirFormulario(null)}
        />
      )}

      <div className="filtros">
        <input
          className="buscador"
          type="search"
          aria-label="Buscar en el catálogo"
          placeholder="Buscar por nombre, categoría o código…"
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
        />

        <span className="etiqueta-filtro">Existencias</span>

        <div className="chips">
          {NIVELES.map((nivel) => (
            <button
              key={nivel.valor || "todos"}
              type="button"
              className={`chip${filtros.existencias === nivel.valor ? " on" : ""}`}
              onClick={() =>
                setFiltros((previos) => ({ ...previos, existencias: nivel.valor }))
              }
            >
              {nivel.texto}
            </button>
          ))}
        </div>

        {/*
          El estado va en un desplegable y no en mas botones: son tres opciones
          que casi nunca se tocan —lo normal es mirar el catalogo activo— y
          sumarlas a la fila de filtros rapidos restaria peso a los que si se
          usan a diario.
        */}
        <select
          className="buscador"
          style={{ flex: "0 0 auto" }}
          aria-label="Estado del producto"
          value={filtros.estado}
          onChange={(e) =>
            setFiltros((previos) => ({ ...previos, estado: e.target.value }))
          }
        >
          {ESTADOS.map((estado) => (
            <option key={estado.valor || "todos"} value={estado.valor}>
              {estado.texto}
            </option>
          ))}
        </select>
      </div>

      <div className="tabla-caja">
        {cargando ? (
          <div className="vacio">Cargando…</div>
        ) : productos.length === 0 ? (
          <div className="vacio">
            {hayFiltro
              ? "Ningún producto coincide con lo que buscas."
              : "Todavía no hay productos registrados."}
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Producto</th>
                <th>Categoría</th>
                <th>Precio de venta</th>
                <th>Existencias</th>
                <th>Estado</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {productos.map((fila) => (
                <tr key={fila.id}>
                  <td>
                    {fila.nombre}
                    {fila.codigo_barras && (
                      <div className="hs" style={{ fontSize: 12 }}>{fila.codigo_barras}</div>
                    )}
                  </td>
                  <td><span className="tag">{fila.categoria_nombre}</span></td>
                  <td>{moneda(fila.precio_venta)}</td>
                  <td>{fila.existencias}</td>
                  <td>
                    <EtiquetaDeEstado producto={fila} />
                  </td>
                  <td className="acciones-fila">
                    {/*
                      El kardex lo ve todo el mundo, tambien quien no puede
                      registrar: consultar el historial no cambia nada.
                    */}
                    <Link
                      className="btn btn-out btn-pequeno"
                      to={`/inventario/productos/${fila.id}/kardex`}
                    >
                      Movimientos
                    </Link>
                    {puedeRegistrar && (
                      <button
                        className="btn btn-out btn-pequeno"
                        type="button"
                        onClick={() => abrirFormulario(fila)}
                        disabled={ocupado}
                      >
                        Editar
                      </button>
                    )}
                    {puedeRegistrar && fila.activo && (
                      <button
                        className="btn btn-out btn-pequeno"
                        type="button"
                        onClick={() => setPorDescontinuar(fila)}
                        disabled={ocupado}
                      >
                        Descontinuar
                      </button>
                    )}
                    {puedeRegistrar && !fila.activo && (
                      <button
                        className="btn btn-out btn-pequeno"
                        type="button"
                        onClick={() => reactivar(fila)}
                        disabled={ocupado}
                      >
                        Reactivar
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {ajustandoMargenes && (
        <MargenesPorCategoria
          categorias={categorias}
          onCerrar={() => setAjustandoMargenes(false)}
          onGuardado={async (guardadas) => {
            setCategorias(guardadas);
            setAjustandoMargenes(false);
            setAviso({ tipo: "ok", texto: "Márgenes guardados." });
            // El precio sugerido de cada producto lo calcula el servidor con
            // estos margenes, de modo que la lista queda atrasada hasta que se
            // vuelve a pedir.
            await refrescar();
          }}
        />
      )}

      {porDescontinuar && (
        <Modal
          titulo="Descontinuar producto"
          mensaje={`«${porDescontinuar.nombre}» dejará de ofrecerse en el punto de venta. Sus existencias y su kardex se conservan, y la referencia se puede reactivar después.`}
          textoConfirmar="Descontinuar"
          ocupado={ocupado}
          onConfirmar={confirmarDescontinuar}
          onCancelar={() => setPorDescontinuar(null)}
        />
      )}
    </Disposicion>
  );
}

/*
  De un producto descontinuado lo que importa es que lo esta: sus existencias ya
  no se van a vender, asi que anunciar que estan bajas seria pedir que se repongan.
*/
function EtiquetaDeEstado({ producto }) {
  if (!producto.activo) return <span className="estado inactivo">Descontinuado</span>;
  if (producto.existencias === 0) return <span className="estado agotado">Agotado</span>;
  if (producto.existencias <= producto.stock_minimo) {
    return <span className="estado bajo">Existencias bajas</span>;
  }
  return <span className="estado disponible">Disponible</span>;
}

/* --- El formulario, el mismo para crear y para editar (apartado 8.4) ----- */

function Formulario({ inicial, categorias, ocupado, onGuardar, onCancelar }) {
  const [datos, setDatos] = useState({
    ...FORMULARIO_VACIO,
    ...inicial,
    categoria: inicial.categoria || "",
    codigo_barras: inicial.codigo_barras || "",
    precio_venta: inicial.precio_venta || "",
    stock_minimo: inicial.stock_minimo ?? "",
  });
  const [errores, setErrores] = useState({});

  const editando = Boolean(inicial.id);

  /*
    La propuesta de precio (RF-INV-11). Solo aparece con una compra detras: sin
    costo no hay nada sobre lo que aplicar un margen, de modo que un producto
    recien registrado no la tiene hasta su primera entrada.

    Se esconde si se cambia la categoria en el formulario, porque el numero que
    propone el servidor se calculo con el margen de la categoria ANTERIOR y
    anunciarlo con el nombre de la nueva seria mentir.
  */
  const numero = (valor) => (valor == null ? null : Number(valor));
  const promedio = numero(inicial.costo_promedio);
  const ultimo = numero(inicial.costo_ultima_compra);
  const minimo = numero(inicial.costo_minimo);
  const maximo = numero(inicial.costo_maximo);
  const sugerido = numero(inicial.precio_sugerido);
  const lotes = inicial.lotes_en_existencia || [];
  const unidades = lotes.reduce((suma, lote) => suma + lote.unidades, 0);

  // Con existencias manda lo que costo lo que hay; sin ellas, lo unico que se
  // sabe es la ultima compra, y la pantalla lo dice en vez de disimularlo.
  const base = promedio !== null ? promedio : ultimo;
  const suCategoria = categorias.find((c) => String(c.id) === String(inicial.categoria));
  const mismaCategoria = String(datos.categoria) === String(inicial.categoria || "");
  const hayPropuesta = base !== null && sugerido !== null && mismaCategoria && suCategoria;

  /*
    Dos avisos distintos, y ninguno bloquea: el precio lo decide el negocio.

    El primero es una perdida real: por debajo del promedio, vender todas las
    existencias deja menos dinero del que costaron. El segundo es lo que un
    promedio esconde: con lotes muy distintos, un precio que gana sobre el
    conjunto puede no cubrir el costo de algunas unidades, y el margen solo se
    cumple si se venden todas.
  */
  const precio = Number(datos.precio_venta);
  const hayPrecio = String(datos.precio_venta).trim() !== "" && precio > 0;
  const bajoElCosto = base !== null && hayPrecio && precio < base;
  const unidadesPorEncima = hayPrecio
    ? lotes
        .filter((lote) => Number(lote.costo_unitario) > precio)
        .reduce((suma, lote) => suma + lote.unidades, 0)
    : 0;

  function cambiar(campo, valor) {
    setDatos((previos) => ({ ...previos, [campo]: valor }));
    setErrores((previos) => ({ ...previos, [campo]: undefined }));
  }

  async function enviar(evento) {
    evento.preventDefault();
    setErrores(await onGuardar(datos));
  }

  return (
    <form className="tarjeta" onSubmit={enviar} noValidate>
      <h2>{editando ? "Editar producto" : "Nuevo producto"}</h2>
      <div className="hs">Completa la información del producto.</div>

      {/*
        Un desplegable vacio no explica nada: quien lo ve supone que la pantalla
        esta rota. Si no hay categorias, se dice y se bloquea el guardado, que
        de todas formas el servidor rechazaria.
      */}
      {categorias.length === 0 && (
        <div className="aviso advertencia" role="status">
          Tu licorera no tiene categorías registradas, así que todavía no se pueden
          registrar productos. Comunícate con INVENTRA para que las habilite.
        </div>
      )}

      <Campo
        id="nombre"
        etiqueta="Nombre del producto"
        marcador="Aguardiente Antioqueño 750 ml"
        valor={datos.nombre}
        onChange={(v) => cambiar("nombre", v)}
        error={errores.nombre}
      />

      <div className="rejilla-dos">
        <CampoSeleccion
          id="categoria"
          etiqueta="Categoría"
          valor={String(datos.categoria)}
          onChange={(v) => cambiar("categoria", v)}
          opciones={[
            { valor: "", texto: "Elige una categoría" },
            ...categorias.map((c) => ({ valor: String(c.id), texto: c.nombre })),
          ]}
          error={errores.categoria}
        />

        <CampoSeleccion
          id="presentacion"
          etiqueta="Presentación"
          valor={datos.presentacion}
          onChange={(v) => cambiar("presentacion", v)}
          opciones={PRESENTACIONES}
          error={errores.presentacion}
        />

        <Campo
          id="precio_venta"
          etiqueta="Precio de venta"
          tipo="number"
          marcador="0"
          minimo="0"
          valor={String(datos.precio_venta)}
          onChange={(v) => cambiar("precio_venta", v)}
          error={errores.precio_venta}
        />

        <Campo
          id="stock_minimo"
          etiqueta="Existencias mínimas (alerta)"
          tipo="number"
          marcador="5"
          minimo="0"
          valor={String(datos.stock_minimo)}
          onChange={(v) => cambiar("stock_minimo", v)}
          error={errores.stock_minimo}
        />
      </div>

      {hayPropuesta && (
        <div className="propuesta">
          <span>
            {promedio !== null ? (
              <>
                {plural(unidades, "unidad", "unidades")} en existencia, a{" "}
                <strong>{moneda(promedio)}</strong> cada una en promedio
                {minimo !== null && maximo !== null && minimo !== maximo && (
                  <> (lotes entre {moneda(minimo)} y {moneda(maximo)})</>
                )}
              </>
            ) : (
              <>Sin existencias; última compra a <strong>{moneda(ultimo)}</strong></>
            )}
            {" · "}margen de {suCategoria.nombre}:{" "}
            <strong>{suCategoria.margen_sugerido}%</strong> · precio sugerido{" "}
            <strong>{moneda(sugerido)}</strong>
          </span>
          <button
            className="btn btn-out btn-pequeno"
            type="button"
            onClick={() => cambiar("precio_venta", String(sugerido))}
          >
            Usar el sugerido
          </button>
        </div>
      )}

      {bajoElCosto && (
        <div className="aviso advertencia" role="status">
          Ese precio queda por debajo de {moneda(base)}, que es lo que costó cada
          unidad {promedio !== null ? "en promedio" : "en la última compra"}. Se puede
          guardar —una liquidación es una decisión del negocio—, pero vender a ese
          precio deja menos dinero del que costó la mercancía.
        </div>
      )}

      {!bajoElCosto && unidadesPorEncima > 0 && (
        <div className="aviso advertencia" role="status">
          {plural(unidadesPorEncima, "unidad costó", "unidades costaron")} más que ese
          precio, hasta {moneda(maximo)}. El promedio reparte esa diferencia entre
          todas, así que el margen solo se cumple si se venden todas.
        </div>
      )}

      {/*
        Se dice en el formulario y no solo en el manual: un campo que falta se
        lee como un olvido si nadie explica por que no esta.
      */}
      <div className="hs" style={{ marginTop: -8 }}>
        Las existencias y el costo no se capturan aquí: entran con cada lote de
        mercancía, y cada lote conserva el suyo.
      </div>

      <Campo
        id="codigo_barras"
        etiqueta="Código de barras"
        marcador="7701234567890"
        requerido={false}
        valor={datos.codigo_barras}
        onChange={(v) => cambiar("codigo_barras", v)}
        error={errores.codigo_barras}
      />

      <div className="acciones">
        <button className="btn btn-out" type="button" onClick={onCancelar} disabled={ocupado}>
          Cancelar
        </button>
        <button
          className="btn btn-cta"
          type="submit"
          disabled={ocupado || categorias.length === 0}
        >
          {ocupado ? "Guardando…" : "Guardar producto"}
        </button>
      </div>
    </form>
  );
}
