/*
  Recorrer una lista que no cabe en una pagina.

  El servidor responde de veinticinco en veinticinco y dice cuantos hay en
  total. Sin este control, una pantalla ensena las veinticinco primeras y se
  comporta como si no hubiera mas: un catalogo de cuarenta y cuatro referencias
  parece de veinticinco, y una venta de la semana pasada no se puede alcanzar
  por ningun camino.

  Vive en un componente propio porque lo necesitan el catalogo, el historial de
  ventas y las listas que vengan: la cuenta de cuantas paginas hay y el
  comportamiento de los dos botones son los mismos en todas.

  No se dibuja cuando todo cabe en una pagina. Un control que siempre dice
  «1 de 1» ocupa sitio para no informar de nada.

  Dice cuantos elementos hay, y no solo el numero de pagina. «26 a 50 de 142»
  contesta a la vez donde estoy y cuanto falta, que son las dos preguntas que
  lleva quien recorre una lista larga.
*/

const POR_PAGINA = 25;

export default function Paginacion({ total, pagina, onCambiar, nombre = "resultados" }) {
  const paginas = Math.ceil(total / POR_PAGINA);
  if (paginas <= 1) return null;

  const primero = (pagina - 1) * POR_PAGINA + 1;
  const ultimo = Math.min(pagina * POR_PAGINA, total);

  return (
    <div className="paginacion">
      <span className="cuenta">
        {primero} a {ultimo} de {total} {nombre}
      </span>
      <div className="acciones">
        <button
          className="btn btn-out btn-pequeno"
          type="button"
          onClick={() => onCambiar(pagina - 1)}
          disabled={pagina <= 1}
        >
          Anterior
        </button>
        <span className="cuenta">
          Página {pagina} de {paginas}
        </span>
        <button
          className="btn btn-out btn-pequeno"
          type="button"
          onClick={() => onCambiar(pagina + 1)}
          disabled={pagina >= paginas}
        >
          Siguiente
        </button>
      </div>
    </div>
  );
}
