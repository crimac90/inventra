/*
  Buscador de una referencia del catalogo.

  No es una lista desplegable por dos razones, y cada una basta. El catalogo
  llega paginado de veinticinco en veinticinco, de modo que un desplegable
  mentiria en cuanto la licorera pase de esa cifra. Y un desplegable con
  seiscientas referencias obliga a recorrerlas con la rueda del raton para
  encontrar una que se sabe de memoria.

  Pregunta al servidor, que es quien sabe filtrar, y ofrece unas pocas
  coincidencias. Busca por nombre, categoria y codigo de barras: la misma
  busqueda de la lista de productos. Se maneja entero con el teclado: flechas
  para recorrer, Enter para elegir y Escape para descartar.

  Ofrece todas las referencias activas, tambien las que ahora mismo no se
  pueden vender —sin existencias o sin precio—. Quien usa el buscador pregunta
  si la referencia EXISTE; que se pueda vender es otra pregunta, y la contesta
  la pantalla que la recibe, con su aviso y diciendo que le falta. Apagar aqui
  unas y no otras daria dos comportamientos para el mismo caso.
*/

import { useEffect, useRef, useState } from "react";

import { listarProductos } from "../api/inventario";
import { useEspera } from "../espera";

/* Cuantas coincidencias se ofrecen. Mas no ayudan: obligan a volver a elegir. */
const MAXIMO = 6;

export default function SelectorDeProducto({ id, valor, onElegir, excluir = [], error }) {
  const [texto, setTexto] = useState("");
  const [encontrados, setEncontrados] = useState([]);
  const [buscando, setBuscando] = useState(false);
  const [resaltado, setResaltado] = useState(0);
  const cuadro = useRef(null);
  const buscado = useEspera(texto);

  useEffect(() => {
    // Con el cuadro vacio no se pide nada: la respuesta serian las primeras
    // veinticinco referencias por orden alfabetico, que no es lo que nadie
    // esta buscando.
    if (valor || buscado.trim() === "") {
      setEncontrados([]);
      return undefined;
    }

    let vigente = true;
    setBuscando(true);
    listarProductos({ buscar: buscado, estado: "activo" })
      .then((datos) => vigente && setEncontrados((datos.results || []).slice(0, MAXIMO)))
      // Un fallo de la busqueda no se anuncia: lo unico que puede hacer quien
      // mira es escribir otra cosa, y para eso ya esta el cuadro delante.
      .catch(() => vigente && setEncontrados([]))
      .finally(() => vigente && setBuscando(false));

    return () => {
      vigente = false;
    };
  }, [buscado, valor]);

  // Cada busqueda nueva empieza por la primera coincidencia.
  useEffect(() => setResaltado(0), [buscado]);

  if (valor) {
    return (
      <div className="field">
        <label htmlFor={id}>Producto</label>
        <div className="elegido" id={id}>
          <span>
            {valor.nombre}
            {valor.codigo_barras && <span className="hs"> · {valor.codigo_barras}</span>}
          </span>
          <button
            className="btn btn-out btn-pequeno"
            type="button"
            onClick={() => {
              onElegir(null);
              setTexto("");
            }}
          >
            Cambiar
          </button>
        </div>
      </div>
    );
  }

  const libres = encontrados.filter((p) => !excluir.includes(p.id));

  function elegir(producto) {
    onElegir(producto);
    setTexto("");
    /*
      El foco se queda donde estaba. En el punto de venta, elegir es agregar y
      lo siguiente es buscar otro producto: devolver el cursor al cuadro evita
      un clic por cada referencia de la venta. Donde el selector pasa a
      ensenar lo elegido, el cuadro ya no existe y esto no hace nada.
    */
    if (cuadro.current) cuadro.current.focus();
  }

  /*
    El teclado. Enter cancela el envio del formulario a proposito: dentro de
    una entrada de mercancia, pulsarlo para escoger una referencia enviaria la
    entrada entera a medio escribir.
  */
  function alPulsarTecla(evento) {
    if (libres.length === 0) {
      if (evento.key === "Escape") setTexto("");
      return;
    }
    if (evento.key === "ArrowDown") {
      evento.preventDefault();
      setResaltado((n) => (n + 1) % libres.length);
    } else if (evento.key === "ArrowUp") {
      evento.preventDefault();
      setResaltado((n) => (n - 1 + libres.length) % libres.length);
    } else if (evento.key === "Enter") {
      evento.preventDefault();
      elegir(libres[Math.min(resaltado, libres.length - 1)]);
    } else if (evento.key === "Escape") {
      setTexto("");
    }
  }

  return (
    <div className="field selector">
      <label htmlFor={id}>Producto</label>
      <input
        ref={cuadro}
        id={id}
        type="search"
        autoComplete="off"
        role="combobox"
        aria-expanded={libres.length > 0}
        aria-controls={`${id}-sugerencias`}
        placeholder="Escribe el nombre o el código de barras…"
        value={texto}
        aria-invalid={error ? "true" : undefined}
        onChange={(e) => setTexto(e.target.value)}
        onKeyDown={alPulsarTecla}
      />

      {buscado.trim() !== "" && (
        <div className="sugerencias" id={`${id}-sugerencias`} role="listbox">
          {buscando && libres.length === 0 && <div className="hs">Buscando…</div>}

          {!buscando && libres.length === 0 && (
            <div className="hs">
              {encontrados.length > 0
                ? "Esa referencia ya está en la entrada."
                : "Ninguna referencia activa coincide."}
            </div>
          )}

          {libres.map((producto, posicion) => (
            <button
              key={producto.id}
              type="button"
              role="option"
              aria-selected={posicion === resaltado}
              className={`sugerencia${posicion === resaltado ? " on" : ""}`}
              onMouseEnter={() => setResaltado(posicion)}
              onClick={() => elegir(producto)}
            >
              <span>{producto.nombre}</span>
              <span className="hs">{producto.categoria_nombre}</span>
            </button>
          ))}
        </div>
      )}

      {error && (
        <div className="msg err" role="alert">
          {error}
        </div>
      )}
    </div>
  );
}
