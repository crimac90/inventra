/*
  Panel de marca de las pantallas de acceso.

  Es el mismo bloque azul en el acceso, el registro y la recuperacion: cambia el
  titular, la frase y las tres vinetas, y el resto se repite. Por eso es un
  componente con parametros y no codigo copiado tres veces.

  Los textos vienen del prototipo y del manual de marca; no se inventan.
*/

import InterruptorTema from "./InterruptorTema";

export default function PanelMarca({ titular, frase, vinetas }) {
  return (
    <div className="marca">
      {/*
        El interruptor de modo vive aqui y no en cada pantalla porque este panel
        es el unico bloque que comparten las cuatro pantallas de acceso. Quien
        todavia no ha entrado tambien elige como quiere ver la aplicacion.
      */}
      <div className="marca-cabecera">
        <div className="logo logo-claro">
          <span className="mk" aria-hidden="true"></span> INVENTRA
        </div>
        <InterruptorTema className="interruptor-marca" soloIcono />
      </div>

      <div>
        <div className="tg">{titular}</div>
        <div className="sb">{frase}</div>

        <div className="feat">
          {vinetas.map((v) => (
            <div key={v.texto}>
              <b aria-hidden="true">{v.marca}</b>
              {v.texto}
            </div>
          ))}
        </div>
      </div>

      <div className="pie">&copy; 2026 INVENTRA</div>
    </div>
  );
}
