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

import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import Campo from "../componentes/Campo";
import CampoSeleccion from "../componentes/CampoSeleccion";
import Disposicion from "../componentes/Disposicion";
import { ErrorApi, mensajeDeError } from "../api/cliente";
import {
  actualizarProducto,
  consultarCategorias,
  crearProducto,
  inactivarProducto,
  listarProductos,
} from "../api/inventario";
import { consultarMiSuscripcion } from "../api/suscripciones";
import { moneda } from "../formato";
import { plural } from "../texto";
import { motivoParaNoRegistrar } from "../sesion/permisos";
import { useSesion } from "../sesion/ContextoSesion";

/* Las cinco del modelo de datos. Es una lista cerrada, no texto libre. */
const PRESENTACIONES = [
  { valor: "media", texto: "Media" },
  { valor: "botella", texto: "Botella" },
  { valor: "litro", texto: "Litro" },
  { valor: "garrafa", texto: "Garrafa" },
  { valor: "unidad", texto: "Unidad" },
];

const ESTADOS = [
  { valor: "activo", texto: "Solo activos" },
  { valor: "inactivo", texto: "Solo descontinuados" },
  { valor: "", texto: "Todos" },
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
  const [aviso, setAviso] = useState(null);
  const [ocupado, setOcupado] = useState(false);
  const [suscripcion, setSuscripcion] = useState(null);

  // Cuando vale null no hay formulario abierto. Con un objeto vacio se esta
  // creando; con un producto dentro, editandolo.
  const [editando, setEditando] = useState(null);

  // Lo que la persona escribe y lo que de verdad se le pide al servidor son
  // dos cosas distintas: entre una y otra hay una espera.
  const [texto, setTexto] = useState("");
  const [filtros, setFiltros] = useState({ buscar: "", existencias: "", estado: "activo" });

  const primeraCarga = useRef(true);

  useEffect(() => {
    const temporizador = setTimeout(
      () => setFiltros((previos) => ({ ...previos, buscar: texto })), ESPERA);
    return () => clearTimeout(temporizador);
  }, [texto]);

  const refrescar = useCallback(async () => {
    const datos = await listarProductos(filtros);
    setProductos(datos.results || []);
  }, [filtros]);

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
        Este fallo NO se traga. La primera version lo ignoraba en silencio,
        copiando el `catch` vacio de la suscripcion, y eso escondio un defecto
        real: una licorera sin categorias mostraba un desplegable vacio sin
        decir por que, y el formulario parecia roto sin motivo. La suscripcion
        se puede ignorar porque sin ella la pantalla sigue sirviendo; sin
        categorias no se puede registrar nada.
      */
      consultarCategorias()
        .then((datos) => vigente && setCategorias(datos))
        .catch((error) => {
          if (vigente) setAviso({ tipo: "err", texto: mensajeDeError(error) });
        });
    }

    listarProductos(filtros)
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
  }, [filtros]);

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

  async function descontinuar(producto) {
    setOcupado(true);
    try {
      await inactivarProducto(producto.id);
      setAviso({ tipo: "ok", texto: `«${producto.nombre}» quedó descontinuado.` });
      await refrescar();
    } catch (error) {
      setAviso({ tipo: "err", texto: mensajeDeError(error) });
    } finally {
      setOcupado(false);
    }
  }

  const motivo = motivoParaNoRegistrar(yo, suscripcion, "registrar ni modificar productos");
  const puedeRegistrar = motivo === null;
  const hayFiltro = filtros.buscar || filtros.existencias || filtros.estado !== "activo";

  return (
    <Disposicion titulo="Inventario">
      <div className="barra-herramientas">
        <div>
          <h1>Inventario</h1>
          <div className="hs" style={{ margin: "6px 0 0" }}>
            {plural(productos.length, "referencia", "referencias")} en la lista.
          </div>
        </div>

        {!editando && !cargando && puedeRegistrar && (
          <button className="btn btn-cta" type="button" onClick={() => setEditando({})}>
            Nuevo producto
          </button>
        )}
      </div>

      {!cargando && motivo && (
        <div className="aviso err" role="status">
          {motivo.texto} <Link to={motivo.enlace.a}>{motivo.enlace.etiqueta}</Link>
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

      {editando && (
        <Formulario
          inicial={editando}
          categorias={categorias}
          ocupado={ocupado}
          onGuardar={guardar}
          onCancelar={() => setEditando(null)}
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
                    {puedeRegistrar && (
                      <button
                        className="btn btn-out btn-pequeno"
                        type="button"
                        onClick={() => setEditando(fila)}
                        disabled={ocupado}
                      >
                        Editar
                      </button>
                    )}
                    {puedeRegistrar && fila.activo && (
                      <button
                        className="btn btn-out btn-pequeno"
                        type="button"
                        onClick={() => descontinuar(fila)}
                        disabled={ocupado}
                      >
                        Descontinuar
                      </button>
                    )}
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
          valor={String(datos.precio_venta)}
          onChange={(v) => cambiar("precio_venta", v)}
          error={errores.precio_venta}
        />

        <Campo
          id="stock_minimo"
          etiqueta="Existencias mínimas (alerta)"
          tipo="number"
          marcador="5"
          valor={String(datos.stock_minimo)}
          onChange={(v) => cambiar("stock_minimo", v)}
          error={errores.stock_minimo}
        />
      </div>

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
